from __future__ import annotations

"""Classical CAN 2.0A／B 離線解碼：尋框、逐位取樣、去填充、CRC-15、錯誤／過載旗標。# 待真機驗證。"""
import numpy as np
from scope_tool.web.logic import Edges
from scope_tool.web.i3c_fields import frame
from scope_tool.web.i3c_ccc import reason
from scope_tool.web.can_fields import Bus, Reader, Stop, crc15, field
from scope_tool.web import can_fd

ROLES = {'can': True, 'canl': False}
BASE = 'can'
DIFF = {'canl': 'can'}
ADDR_TABLE = False
REQUIRE_EDGES = False
FLAG_MIN, IDLE_MIN, IFS_BITS = 5.75, 10.75, 1.75  # 以 T 為單位；各留 0.25 T 容差（旗標 6 T、idle 11 T、intermission 前 2 位）


def options(options: dict, channels: dict) -> dict:
    if not isinstance(options, dict) or set(options) - {'bitrate', 'sample_point', 'dominant_high', 'data_bitrate', 'data_sample_point'}:
        raise ValueError('CAN 參數不合法')
    o = dict(bitrate=500000, sample_point=75, dominant_high=True, data_bitrate=None, data_sample_point=75)
    o.update(options)
    num = ['bitrate', 'sample_point', 'data_sample_point'] + (['data_bitrate'] if o['data_bitrate'] is not None else [])
    ok = (all(not isinstance(o[k], bool) and isinstance(o[k], (int, float)) and np.isfinite(o[k]) for k in num)
          and o['bitrate'] > 0 and 50 <= o['sample_point'] <= 95 and 50 <= o['data_sample_point'] <= 95
          and (o['data_bitrate'] is None or o['data_bitrate'] > 0) and type(o['dominant_high']) is bool)
    if not ok:
        raise ValueError('CAN 需 bitrate>0、sample_point 50–95、布林 dominant_high，data_bitrate 選填且 >0')
    return o


def _hunt(b: Bus, t: float, mode: str, first: bool) -> tuple[tuple[float, float] | None, tuple | None]:
    """從 t 起找下一個 SOF 或旗標。mode: idle＝需 ≥11 T 隱性；inter＝剛結束一框，處於 intermission。

    回傳 (擷取起點的 partial 區段, ('sof'|'flag', 區間索引, 起點, 起點在擷取前?))。
    """
    T, n = b.T, len(b.ds)
    i = int(np.searchsorted(b.de, t + (.25 * T if mode == 'inter' else 0), 'right'))
    prev, g0, g1 = float(b.de[i - 1]) if i else t, None, None  # 隱性起點＝上一段顯性結束（t 之前已持續的隱性段也算）
    part = lambda: (g0, g1) if first and g0 is not None else None  # noqa: E731
    while i < n:
        s, e = float(b.ds[i]), float(b.de[i])
        cs = max(s, t)
        if e - cs < .5 * T and not b.dopen[i]:  # 毛刺：不算活動
            i += 1
            continue
        if e - cs >= FLAG_MIN * T:  # 框外 ≥6 T 顯性＝旗標（獨立入口，不看 idle）
            return part(), ('flag', i, cs, first and not b.dreal[i] and s <= t)
        if mode == 'inter':  # intermission 第 1、2 位顯性＝過載旗標；之後的邊沿即 SOF
            return None, ('flag', i, cs, False) if cs < t + IFS_BITS * T else ('sof', i)
        if b.dreal[i] and s - prev >= IDLE_MIN * T:
            return part(), ('sof', i)
        g0 = cs if g0 is None else g0
        g1 = prev = e
        i += 1
    return part(), None


def _flag(b: Bus, i: int, cs: float, cut: bool) -> tuple[dict, str, float]:
    """旗標 frame：t1＝顯性段結束後 8 T 隱性（被打斷則止於打斷處並標 form）。"""
    T, e = b.T, float(b.de[i])
    f = frame(cs, 'error_flag')
    reason(f, 'error_flag', 'error')
    if cut:
        reason(f, 'truncated', 'warn')
    nxt = float(b.ds[i + 1]) if i + 1 < len(b.ds) else np.inf
    if b.dopen[i]:
        f['t1'] = e
        reason(f, 'truncated', 'warn')
        return f, 'done', e
    if nxt < e + 7.75 * T:
        f['t1'] = nxt
        reason(f, 'form', 'error')
    elif e + 8 * T > b.end:
        f['t1'] = b.end
        reason(f, 'truncated', 'warn')
    else:
        f['t1'] = e + 8 * T
    return f, 'idle', e


def _decode(b: Bus, ts: float, fd: tuple[float, float] | None = None) -> tuple[dict, list, str, float]:
    """解一框，回傳 (frame, 線上位元, 下一步 mode, 下一步起點)。"""
    T = b.T
    rd = Reader(b, ts)
    f = frame(ts, 'partial')
    raw: list[int] = []
    mode, t_next = 'idle', ts

    def grab(n: int) -> list:
        bits = rd.take(n)
        raw.extend(v for *_, v in bits)
        return bits

    def add(kind: str, bits: list, tt: float | None = None, **kw: object) -> None:
        f['fields'].append(field(kind, bits, tt or T, **kw))

    try:
        grab(1)  # SOF（呼叫端已確認是真邊沿；取樣為隱性只會是毛刺）
        ida, b2 = grab(11), grab(2)
        ext = b2[1][2] == 1
        if ext:
            idb = grab(18)
            rtr_b, rr = grab(1), grab(2)
            ids, tail, rtr, fdf = ida + idb, rtr_b + rr, rtr_b[0][2], rr[0][2]
        else:
            r0 = grab(1)
            ids, tail, rtr, fdf = ida, b2 + r0, b2[0][2], r0[0][2]
        ident = field('id', ids, T)['value']
        f.update(addr=ident, label=f'EXT 0x{ident:07X}' if ext else f'STD 0x{ident:03X}')
        add('id', ids)
        f['kind'] = 'fd' if fdf else 'remote' if rtr else 'data'
        if fdf and fd is None:  # 未填 data_bitrate：只標示不解，略過這一框
            add('ctrl', tail, label='FDF=1')
            f['label'] = 'CAN FD（未解碼）'
            reason(f, 'fd_unsupported', 'warn')
            f['t1'] = tail[-1][0] + T
            return f, rd.wire, 'idle', f['t1']
        if fdf:
            got, calc, brs = can_fd.read(rd, grab, add, f, ext, tail, *fd)
        else:
            add('ctrl', tail, label=('RTR=%d r1=%d r0=%d' if ext else 'RTR=%d IDE=%d r0=%d') % tuple(v for *_, v in tail))
            dlc = grab(4)
            dv = field('dlc', dlc, T)['value']
            add('dlc', dlc)
            if not ext:
                f['label'] += f' DLC {dv}'
            for _ in range(0 if rtr else min(dv, 8)):
                add('data', grab(8))
            calc = crc15(raw)
            crcb = rd.take(15)
            got = field('crc', crcb, T)['value']
            add('crc', crcb, ok=got == calc, label=f'calc 0x{calc:04X}')
            rd.flush()
        st, sm, v = rd.raw()  # CRC delimiter
        if v == 0:
            raise Stop('form', st)
        if fdf and brs:  # CRC delimiter 位長 = sp_d·Td + (1 − sp_n)·Tn，之後回標稱位元時間
            rd.rebase(sm + (1 - b.sp) * T, T, b.sp)
        st, sm, v = rd.raw()  # ACK slot：單取樣欄位
        if fdf and v == 0:  # ponytail: FD 接收器容許 ACK 為 2 位 dominant；CRC delimiter 2 位 recessive 與「無 ACK」難分，不處理
            ack2 = rd.raw()
            if ack2[2] == 0:
                ack2 = rd.raw()
            st, sm, v, delim = st, sm, 0, ack2
        else:
            delim = None
        f['ack'] = v == 0
        f['fields'].append(dict(t0=sm, t1=sm, kind='ack', addr=None, value=v, nbits=1, ninth=None,
                                ninth_kind=None, ok=True, label=''))
        if v:
            reason(f, 'no_ack', 'warn')
        st, sm, v = delim or rd.raw()  # ACK delimiter
        if v == 0:
            raise Stop('form', st)
        if got != calc:  # CRC 錯誤旗標在 ACK delimiter 之後才開始，照常取到這裡為止
            reason(f, 'crc', 'error')
            f['t1'] = t_next = rd.edge_time()
        else:
            eof = []
            for k in range(7):
                st, sm, v = rd.raw()
                if v == 0 and k < 6:  # EOF 第 7 位顯性只標不判
                    raise Stop('form', st)
                eof.append((st, sm, v))
            add('eof', eof)
            f['t1'] = t_next = rd.edge_time()
            mode = 'inter'
    except Stop as s:
        f['t1'] = t_next = s.t
        if s.code == 'truncated':
            mode = 'done'
            reason(f, 'truncated', 'warn')
            for x in f['fields']:  # 欄位不可超出擷取終點
                x['t1'] = min(x['t1'], s.t)
        else:
            reason(f, s.code, 'error')
    if rd.timing:
        reason(f, 'timing', 'warn')
    return f, rd.wire, mode, t_next


def run(edges: dict[str, Edges], *, t1: float | None = None, max_frames: int = 100_000,
        max_fields: int = 100_000, **opts: object) -> dict:
    o = options(opts, edges)
    if any(type(v) is not int or v < 1 for v in (max_frames, max_fields)):
        raise ValueError('事件上限須為正整數')
    e = edges['can']
    T = 1 / o['bitrate']
    end = float(t1) if t1 is not None else float(e.time[-1]) + 12 * T
    if e.truncated:
        end = min(end, float(e.time[-1]))
    b = Bus(e, end, T, o['sample_point'] / 100, o['dominant_high'])
    warnings = ['取樣不足（每位元少於 8 點）'] if 0 < e.min_run < 8 else []
    items, t, mode, first, count, halted = [], float(e.time[0]), 'idle', True, 0, False
    while t < end and mode != 'done':
        part, item = _hunt(b, t, mode, first)
        found = []
        if part:
            f = frame(part[0], 'partial')
            f['t1'] = part[1]
            f['label'] = '擷取起點在訊框中間'
            reason(f, 'truncated', 'warn')
            found.append((f, []))
        first = False
        if item is None:
            mode = 'done'
        elif item[0] == 'flag':
            f, mode, t = _flag(b, *item[1:])
            found.append((f, []))
        else:
            i = item[1]
            if float(b.de[i]) - float(b.ds[i]) < .75 * T and not b.dopen[i]:  # SOF 取樣點仍是隱性＝毛刺
                t, mode = float(b.de[i]), 'idle'
                continue
            fd = (1 / o['data_bitrate'], o['data_sample_point'] / 100) if o['data_bitrate'] else None
            f, w, mode, t = _decode(b, float(b.ds[i]), fd)
            found.append((f, w))
        for f, w in found:
            if len(items) >= max_frames or count + len(f['fields']) > max_fields:
                end, halted, mode = f['t0'], True, 'done'
                break
            f['i'] = len(items)
            count += len(f['fields'])
            items.append((f, w))
    bits = sorted(x for f, w in items for x in w)
    if e.truncated or halted:
        warnings.append(f'事件或邊沿超過上限，只解到 t={end:.12g}')
    frames = [f for f, _ in items]
    return dict(frames=frames, bits_t=np.array([x[0] for x in bits]),
                bits_v=np.array([x[1] for x in bits], dtype=np.int8), addresses=[], warnings=warnings,
                truncated=e.truncated or halted or any('truncated' in f['reasons'] for f in frames), t1=end)


if __name__ == '__main__':
    from scope_tool.web.logic import prepare
    T, PTS = 2e-6, 20
    H1 = '000100100011000001100001001000110100011011010110111'  # 研究文件 CAN §11.1：stuffed SOF..CRC（51 位）

    def wave(bitstr: str, lead: int = 14, tail: int = 14):
        s = '1' * lead + bitstr + '1' * tail
        v = np.repeat([0. if c == '1' else 2. for c in s], PTS)
        return np.arange(len(v)) * T / PTS, v

    def decode(bitstr: str, **kw):
        t, v = wave(bitstr, **kw)
        ed, _, end, err = prepare(t, {'can': v}, {'can': [.5, 1.5]}, require_edges=False)
        assert err is None
        return run(ed, t1=end, bitrate=500000)

    full = H1 + '1' + '0' + '1' + '1111111' + '111'
    r = decode(full)
    f = r['frames'][0]
    assert len(r['frames']) == 1 and f['kind'] == 'data' and f['addr'] == 0x123 and f['status'] == 'ok' and f['ack'] is True, f
    assert f['label'] == 'STD 0x123 DLC 2' and [x['value'] for x in f['fields'] if x['kind'] == 'data'] == [0x12, 0x34]
    assert [x['value'] for x in f['fields'] if x['kind'] == 'crc'] == [0x36B7] and r['bits_v'].tolist().count(2) == 1
    two = decode(full + full)  # 背靠背：EOF 後 3 位 intermission 即下一個 SOF
    assert [x['addr'] for x in two['frames']] == [0x123, 0x123] and two['frames'][0]['t1'] <= two['frames'][1]['t0']
    cut = decode(H1[:40], tail=0)
    assert cut['frames'][0]['reasons'] == ['truncated'] and cut['truncated']
    bad = decode(H1[:20] + '1' * 6 + H1[26:])  # 破壞填充：第 6 個相同位
    assert 'stuff' in bad['frames'][0]['reasons'] or bad['frames'][0]['status'] == 'error'
    flag = decode('0' * 6 + '1' * 8)
    assert flag['frames'][0]['kind'] == 'error_flag'
    print('web.can_decode self-check OK')
