from __future__ import annotations

"""I3C HDR-DDR 字組解碼（Command／Data／CRC）：SCL 每個邊沿取一位 SDA。

未經外部驗證：P1／P0、CRC5 範圍與 CRC 字組後段僅依 MIPI I3C Basic v1.1.1 §5.2.2 的理解。"""
import numpy as np
from scope_tool.web.logic import Edges, levels_at
from scope_tool.web.i3c_fields import field
from scope_tool.web.i3c_ccc import reason

TOKEN = 0xC


def parity(payload: int) -> tuple[int, int]:
    """(P1, P0)：P1＝奇數位元（D15,D13…D1）互斥或；P0＝偶數位元（D14…D0）互斥或再反相。"""
    bits = [(payload >> i) & 1 for i in range(15, -1, -1)]
    p1 = p0 = 0
    for i, b in enumerate(bits):
        if i % 2 == 0:
            p1 ^= b
        else:
            p0 ^= b
    return p1, p0 ^ 1


def crc5(payloads: list[int]) -> int:
    """x⁵+x²+1，初值 0x1F，MSB 先；輸入只含 Command／Data 的 16 位 payload（不含 preamble）。"""
    crc = 0x1F
    for p in payloads:
        for i in range(15, -1, -1):
            top = ((crc >> 4) ^ (p >> i)) & 1
            crc = (crc << 1) & 0x1F
            if top:
                crc ^= 0x05
    return crc


def _val(bits: list) -> int:
    v = 0
    for _, b in bits:
        v = (v << 1) | b
    return v


def words(f: dict, bits: list[tuple[float, int]]) -> None:
    """把 (時間, 位元) 序列切成字組並寫入 frame f。"""
    pos, payloads, first_data = 0, [], True

    def take(n: int) -> list | None:
        nonlocal pos
        if pos + n > len(bits):
            return None
        pos += n
        return bits[pos - n:pos]

    while pos < len(bits):
        pre = take(2)
        if pre is None or bits[pos - 2][1] < 0:
            break
        p = _val(pre)
        if not payloads and p != 1:  # 第一個字組必為 Command（preamble 01）
            reason(f, 'hdr_preamble', 'error')
            return
        if p == 1 and payloads:  # CRC 字組：Token4 | CRC5
            tok, c = take(4), take(5)
            if tok is None or c is None:
                break
            ct = field(c, 'hdr_crc')
            ok = _val(tok) == TOKEN
            ct['ok'] = ok and ct['value'] == crc5(payloads)
            ct['label'] = f"token 0x{_val(tok):X}"
            f['fields'].append(ct)
            if not ok:
                reason(f, 'hdr_preamble', 'error')
            elif not ct['ok']:
                reason(f, 'hdr_crc', 'error')
            return
        if p == 0:
            reason(f, 'hdr_preamble', 'error')
            return
        body, par = take(16), take(2)
        if body is None or par is None:
            break
        v = _val(body)
        kind = 'hdr_data' if payloads else 'hdr_cmd'
        x = field(body, kind)
        x['ok'] = (_val(par) >> 1, _val(par) & 1) == parity(v)
        if kind == 'hdr_cmd':
            f.update(rw=v >> 15, addr=(v >> 1) & 0x7F)
            x['label'] = f"{'R' if v >> 15 else 'W'} cmd 0x{(v >> 8) & 0x7F:02X} @0x{(v >> 1) & 0x7F:02X}"
        f['fields'].append(x)
        if not x['ok']:
            reason(f, 'hdr_parity', 'error')
        payloads.append(v)
        if kind == 'hdr_data':
            if first_data and p == 3:  # 第一個 Data 的 preamble 11＝NACK
                reason(f, 'hdr_nack', 'warn')
                return
            if not first_data and p == 2:  # 後續 Data 的 preamble 10＝中止
                return
            first_data = False
    reason(f, 'truncated', 'warn')


def apply(res: dict, scl: Edges, sda: Edges) -> dict:
    """對 decode() 結果中 HDR-DDR 區段（label 以 'HDR-DDR' 起頭）解字組。"""
    bt, bv = [res['bits_t']], [res['bits_v']]
    for f in res['frames']:
        if f['kind'] != 'hdr' or not f['label'].startswith('HDR-DDR'):
            continue
        m = (scl.time > f['t0']) & (scl.time < f['t1']) & ~scl.resync & (scl.value >= 0)
        ts = scl.time[m]
        if len(ts) == 0:
            continue
        v = levels_at(sda, ts, res['t1'])
        f['label'] = 'HDR-DDR 區段'
        words(f, [(float(t), int(b)) for t, b in zip(ts, v)])
        bt.append(ts)
        bv.append(v.astype(np.int8))
    if len(bt) > 1:  # 位元序列合併後依時間排序
        t, v = np.concatenate(bt), np.concatenate(bv)
        order = np.argsort(t, kind='stable')
        res['bits_t'], res['bits_v'] = t[order], v[order]
    return res


if __name__ == '__main__':
    assert parity(0x0000) == (0, 1) and parity(0x8000) == (1, 1) and parity(0x0001) == (0, 0)
    assert crc5([]) == 0x1F
    f = dict(fields=[], reasons=[], status='ok', rw=None, addr=None)
    words(f, [(0., 0), (1., 1)])
    assert f['reasons'] == ['truncated']
    print('web.i3c_hdr self-check OK')
