from __future__ import annotations

"""CAN FD（ISO 11898-1:2015，ISO FD）：控制欄、位元率切換、stuff count、固定填充位與 CRC-17／21。

未經外部驗證：合成器與解碼器出自同一份規格理解，閉環測不出共同誤解。"""
from scope_tool.web.i3c_ccc import reason
from scope_tool.web.can_fields import Reader, Stop, field

DLC_LEN = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]
POLY = {17: 0x3685B, 21: 0x302899}  # 含最高次項


def gray_sbc(n_stuff: int) -> list[int]:
    """stuff count（mod 8）的 Gray 碼 3 位＋偶同位。"""
    g = (n_stuff % 8) ^ ((n_stuff % 8) >> 1)
    b = [(g >> 2) & 1, (g >> 1) & 1, g & 1]
    return b + [b[0] ^ b[1] ^ b[2]]


def crc_fd(bits, n: int) -> int:
    """CRC-17／21：初值最高位為 1（ISO），輸入為含動態填充位的 SOF..DATA ＋ SBC 4 位。"""
    mask, crc = (1 << n) - 1, 1 << (n - 1)
    for b in bits:
        top = ((crc >> (n - 1)) ^ b) & 1
        crc = (crc << 1) & mask
        if top:
            crc ^= POLY[n] & mask
    return crc


def read(rd: Reader, grab, add, f: dict, ext: bool, tail: list, Td: float, spd: float) -> tuple[int, int, bool]:
    """FDF=1 之後讀到 CRC 末位；回傳 (收到的 CRC, 算出的 CRC, BRS)。呼叫端接著讀 CRC delimiter。"""
    Tn, spn = rd.T, rd.sp
    res = tail[-1] if ext else grab(1)[0]
    brs = grab(1)[0]
    if brs[2]:  # 在 BRS 取樣點切換：本位長 = sp_n·Tn + (1 − sp_d)·Td
        rd.rebase(brs[1] + (1 - spd) * Td, Td, spd)
    esi = grab(1)[0]
    tt = Td if brs[2] else Tn
    bits = tail + ([] if ext else [res]) + [brs, esi]
    add('ctrl', bits, label=f'FDF=1 BRS={brs[2]} ESI={esi[2]}')
    if res[2]:
        raise Stop('form', res[0])
    dlc = grab(4)
    dv = field('dlc', dlc, tt)['value']
    add('dlc', dlc, tt)
    f['label'] += f' FD DLC {dv}'
    for _ in range(DLC_LEN[dv]):
        add('data', grab(8), tt)
    stuffed: list[int] = []  # 線上位元（動態填充位 = 前一位反相）
    for _, v in rd.wire:
        stuffed.append(1 - stuffed[-1] if v == 2 else v)
    n_stuff, rd.stuffing = sum(v == 2 for _, v in rd.wire), False
    prev, n = stuffed[-1], 17 if DLC_LEN[dv] <= 16 else 21
    read_bits = []
    for i in range(0, 4 + n, 4):  # 每組（≤4 位）前面一個固定填充位
        st, sm, v = rd.raw()
        if v == prev:
            raise Stop('form', st)
        rd.wire.append((sm, 2))
        prev = v
        for _ in range(min(4, 4 + n - i)):
            st, sm, v = rd.raw()
            rd.wire.append((sm, v))
            read_bits.append((st, sm, v))
            prev = v
    sbc, crcb = read_bits[:4], read_bits[4:]
    ok = [v for *_, v in sbc] == gray_sbc(n_stuff)
    add('sbc', sbc, tt, ok=ok, label=f'stuff {n_stuff}')
    if not ok:
        reason(f, 'stuff_count', 'error')
    calc = crc_fd(stuffed + [v for *_, v in sbc], n)
    got = field('crc', crcb, tt)['value']
    add('crc', crcb, tt, ok=got == calc, label=f'calc 0x{calc:0{(n + 3) // 4}X}')
    return got, calc, bool(brs[2])


if __name__ == '__main__':
    def bits_of(data: bytes) -> list[int]:
        return [(x >> i) & 1 for x in data for i in range(7, -1, -1)]
    assert [gray_sbc(i)[:3] for i in range(8)] == [[0, 0, 0], [0, 0, 1], [0, 1, 1], [0, 1, 0], [1, 1, 0], [1, 1, 1], [1, 0, 1], [1, 0, 0]]
    assert gray_sbc(8) == gray_sbc(0) == [0, 0, 0, 0] and gray_sbc(1)[3] == 1 and gray_sbc(2)[3] == 0
    assert crc_fd([], 17) == 1 << 16 and crc_fd([], 21) == 1 << 20
    print('web.can_fd self-check OK')
