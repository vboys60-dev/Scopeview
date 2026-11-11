from __future__ import annotations

"""USB PD 符號與 BMC 合成；待實機驗證。"""
from pathlib import Path
import zlib
from scope_tool.web import synth
from scope_tool.web.usbpd_fields import DATA_CODES, ORDERED, EOP


def symbols(header: int, objects: tuple[int, ...] = (), sop: str = 'SOP',
            crc: int | None = None, eop: bool = True) -> list[int]:
    payload = header.to_bytes(2, 'little') + b''.join(x.to_bytes(4, 'little') for x in objects)
    checksum = zlib.crc32(payload) if crc is None else crc
    raw = payload + checksum.to_bytes(4, 'little')
    ordered = next(k for k, v in ORDERED.items() if v == sop)
    return list(ordered) + [DATA_CODES[n] for b in raw for n in (b & 15, b >> 4)] + ([EOP] if eop else [])


def packet(codes: list[int], preamble: int = 64) -> list[int]:
    return [i % 2 for i in range(preamble)] + [(c >> i) & 1 for c in codes for i in range(5)]


def bus(packets: list[list[int]], bitrate: float = 300000, gap: int = 8) -> dict:
    if bitrate <= 0 or gap < 4:
        raise ValueError('位元率或封包間隔不合法')
    trans = [(0., 'cc', 0)]
    level, t, ui = 0, 8 / bitrate, 1 / bitrate
    for bits in packets:
        for bit in bits:
            level ^= 1
            trans.append((t, 'cc', level))
            if bit:
                level ^= 1
                trans.append((t + ui / 2, 'cc', level))
            t += ui
        level ^= 1
        trans.append((t, 'cc', level))
        t += gap * ui
    return dict(trans=trans, end=t)


def render(wave: dict, fs: float = 12000000) -> tuple:
    return synth.render(wave['trans'], fs, lines=('cc',), noise=0, end=wave['end'])


def fixture(path: Path) -> dict:
    packets = [packet(symbols(0x0141)), packet(symbols(0x1141, (0x12345678,))),
               packet(symbols(0x1142, (0x87654321,)))]
    synth.write_csv(path, render(bus(packets)))
    return dict(channels={'cc': 'CHAN1'}, options={}, expect_kinds=['control', 'data'])


if __name__ == '__main__':
    assert zlib.crc32(bytes.fromhex('41 01')) == 0xdfbc5c2d
    assert len(packet(symbols(0x0141))) == 149
    print('web.usbpd_synth self-check OK')
