from __future__ import annotations

"""Classical CAN 符號、位元填充及類比波形合成。"""
from pathlib import Path
from scope_tool.web import synth


def bits(value: int, width: int) -> list[int]:
    return [(value >> i) & 1 for i in range(width - 1, -1, -1)]


def crc15(data: list[int]) -> int:
    reg = 0
    for bit in data:
        top = ((reg >> 14) & 1) ^ bit
        reg = ((reg << 1) ^ (0x4599 if top else 0)) & 0x7fff
    return reg


def can_frame(id: int, data: bytes | list[int], ext: bool = False, rtr: bool = False,
              dlc: int | None = None, ack: bool = True, crc: int | None = None,
              stuff_break: int | None = None) -> list[int]:
    """回傳 SOF 至 EOF；stuff_break 指定第幾個填充位改成相同位。"""
    if not 0 <= id < (1 << (29 if ext else 11)):
        raise ValueError('CAN ID 超出範圍')
    data = list(data)
    dlc = len(data) if dlc is None else dlc
    if not 0 <= dlc <= 15 or any(not 0 <= x <= 255 for x in data):
        raise ValueError('CAN 資料或 DLC 超出範圍')
    if not rtr and len(data) != min(dlc, 8):
        raise ValueError('資料長度須符合 DLC')
    raw = [0] + (bits(id >> 18, 11) + [1, 1] + bits(id & 0x3ffff, 18) + [int(rtr), 0, 0]
                 if ext else bits(id, 11) + [int(rtr), 0, 0])
    raw += bits(dlc, 4) + ([] if rtr else [b for byte in data for b in bits(byte, 8)])
    raw += bits(crc15(raw) if crc is None else crc, 15)
    out: list[int] = []
    last, run, count = -1, 0, 0
    for bit in raw:
        out.append(bit)
        run = run + 1 if bit == last else 1
        last = bit
        if run == 5:
            count += 1
            out.append(bit if stuff_break == count else 1 - bit)
            last, run = 1 - bit, 1
    return out + [1, 0 if ack else 1, 1] + [1] * 7


def can_bus(frames: list[list[int]], bitrate: float = 500000,
            gaps: int | list[int] = 3, slow: float = 0) -> dict:
    """gaps 以位元時間計算；前置 idle 固定 11 位。"""
    if bitrate <= 0 or slow <= -1:
        raise ValueError('位元率不合法')
    period = (1 + slow) / bitrate
    stream = [1] * 11
    for i, frame in enumerate(frames):
        stream.extend(frame)
        stream.extend([1] * (gaps[i] if isinstance(gaps, list) else gaps))
    stream.extend([1] * 11)
    trans = [(0., 'can', 1)]
    for i, bit in enumerate(stream):
        if bit != trans[-1][2]:
            trans.append((i * period, 'can', bit))
    return dict(trans=trans, end=len(stream) * period)


def render(bus: dict, *, fs: float = 500000 * 32, differential: bool = False,
           offset: float = 0, noise: float = 0) -> tuple:
    """線上 0 是顯性；差動線與 CANH 的高電壓代表顯性。"""
    if differential:
        trans = [(t, lane, v) for t, _, v in bus['trans'] for lane in ('canh', 'canl')]
        levels = {'canh': (3.5 + offset, 2.5 + offset), 'canl': (1.5 + offset, 2.5 + offset)}
        return synth.render(trans, fs, lines=('canh', 'canl'), levels=levels, noise=noise, end=bus['end'])
    return synth.render(bus['trans'], fs, lines=('can',), levels={'can': (2 + offset, offset)},
                        noise=noise, end=bus['end'])


def fixture(path: Path) -> dict:
    frames = [can_frame(0x123, [0x12, 0x34]), can_frame(0x123, [0x12, 0x34], ack=False),
              can_frame(0x1abcdef, [0xa5], ext=True), can_frame(0x123, [], rtr=True, dlc=4)]
    synth.write_csv(path, render(can_bus(frames), differential=True))
    return dict(channels={'can': 'CHAN1', 'canl': 'CHAN2'}, options={'bitrate': 500000},
                expect_kinds=['data', 'remote'])




FD_LENGTHS = list(range(9)) + [12, 16, 20, 24, 32, 48, 64]


def fd_crc(data: list[int], width: int) -> int:
    """ISO CAN FD CRC；輸入包含動態填充與 SBC。"""
    if width not in (17, 21):
        raise ValueError('CRC 寬度不合法')
    reg, poly = 1 << (width - 1), 0x3685b if width == 17 else 0x302899
    for bit in data:
        top = ((reg >> (width - 1)) & 1) ^ bit
        reg = ((reg << 1) ^ (poly if top else 0)) & ((1 << width) - 1)
    return reg


def fd_frame(id: int, data: bytes | list[int], *, dlc: int, brs: bool = False,
             ext: bool = False, esi: bool = False, ack: bool = True) -> dict:
    """回傳線上位元與速率切換位置。"""
    data = list(data)
    if not 0 <= id < (1 << (29 if ext else 11)) or not 0 <= dlc <= 15:
        raise ValueError('CAN FD ID 或 DLC 超出範圍')
    if len(data) != FD_LENGTHS[dlc] or any(not 0 <= x <= 255 for x in data):
        raise ValueError('CAN FD 資料長度或內容不合法')
    header = (bits(id >> 18, 11) + [1, 1] + bits(id & 0x3ffff, 18) + [0, 1, 0]
              if ext else bits(id, 11) + [0, 0, 1, 0])
    raw = [0] + header + [int(brs), int(esi)] + bits(dlc, 4)
    brs_raw = len(header) + 1
    raw += [b for byte in data for b in bits(byte, 8)]
    wire: list[int] = []
    last, run, count, brs_index = -1, 0, 0, 0
    for i, bit in enumerate(raw):
        if i == brs_raw:
            brs_index = len(wire)
        wire.append(bit)
        run = run + 1 if bit == last else 1
        last = bit
        if run == 5 and i + 1 < len(raw):
            wire.append(1 - bit)
            last, run, count = 1 - bit, 1, count + 1
    gray = (count % 8) ^ ((count % 8) >> 1)
    sbc = bits(gray, 3) + [gray.bit_count() % 2]
    width = 17 if len(data) <= 16 else 21
    crc = fd_crc(wire + sbc, width)
    groups = sbc + bits(crc, width)
    fsb_indices = []
    for i in range(0, len(groups), 4):
        fsb_indices.append(len(wire))
        wire.append(1 - wire[-1])
        wire.extend(groups[i:i + 4])
    delimiter = len(wire)
    wire += [1, 0 if ack else 1, 1] + [1] * 7
    return dict(bits=wire, brs=brs_index if brs else None, delimiter=delimiter,
                fsb=fsb_indices, stuff_count=count, sbc=sbc, crc=crc)


def fd_bus(frames: list[dict | list[int]], *, bitrate: float = 500000,
           data_bitrate: float = 2000000, sample_point: float = .75,
           data_sample_point: float = .75, gap: int = 3) -> dict:
    """合成混排波形；BRS 與 CRC delimiter 的切換發生於取樣點。"""
    if min(bitrate, data_bitrate) <= 0 or not (0 < sample_point < 1 and 0 < data_sample_point < 1):
        raise ValueError('CAN FD 時序不合法')
    tn, td = 1 / bitrate, 1 / data_bitrate
    trans, time, level = [(0., 'can', 1)], 11 * tn, 1
    for frame in frames:
        seq = frame['bits'] if isinstance(frame, dict) else frame
        brs = frame['brs'] if isinstance(frame, dict) else None
        delimiter = frame['delimiter'] if isinstance(frame, dict) else None
        for i, bit in enumerate(seq):
            if bit != level:
                trans.append((time, 'can', bit))
                level = bit
            duration = tn
            if brs is not None:
                if i == brs:
                    duration = sample_point * tn + (1 - data_sample_point) * td
                elif brs < i < delimiter:
                    duration = td
                elif i == delimiter:
                    duration = data_sample_point * td + (1 - sample_point) * tn
            time += duration
        time += gap * tn
        if level != 1:
            trans.append((time - gap * tn, 'can', 1))
            level = 1
    return dict(trans=trans, end=time + 11 * tn)


if __name__ == '__main__':
    h1 = '000100100011000001100001001000110100011011010110111'
    assert ''.join(map(str, can_frame(0x123, [0x12, 0x34])[:-10])) == h1
    assert crc15([int(b) for c in b'123456789' for b in f'{c:08b}']) == 0x059e
    assert crc15([int(x) for x in '00000110101011111100110111101111000000110100101']) == 0xd9
    assert len(can_frame(0x1abcdef, [0xa5], ext=True)[:-10]) == 66
    f = fd_frame(0x123, [0xa5], dlc=1)
    assert f['crc'] == 0x7ab9 and len(f['fsb']) == 6
    print('web.can_synth self-check OK')
