from __future__ import annotations

"""HDR-DDR 合成波形、獨立真值及變異自檢；未經外部驗證。"""
import sys
from scope_tool.web import i3c_hdr
from scope_tool.web.i3c_synth import Bus
from scope_tool.web.i3c_vectors import run

# 手寫逐位真值：寫入 cmd 0x1210、data 0x1234，CRC5＝0x05。
TRUTH = '01' '0001001000010000' '11' '10' '0001001000110100' '00' '01' '1100' '00101'


def independent_parity(value: int) -> tuple[int, int]:
    digits = f'{value:016b}'
    return sum(map(int, digits[::2])) % 2, 1 ^ (sum(map(int, digits[1::2])) % 2)


def independent_crc(payloads: list[int], initial: int = 31, pres: list[int] | None = None) -> int:
    stream = ''.join((f'{pres[i]:02b}' if pres is not None else '') + f'{v:016b}'
                     for i, v in enumerate(payloads))
    dividend = (initial << len(stream)) ^ (int(stream or '0', 2) << 5)
    for bit in range(len(stream) + 4, 4, -1):
        if dividend & (1 << bit):
            dividend ^= 0x25 << (bit - 5)
    return dividend


def encoded(pre: int, value: int) -> str:
    p1, p0 = independent_parity(value)
    return f'{pre:02b}{value:016b}{p1}{p0}'


def inspect(words: list[tuple[int, int]], values: list[tuple[str, int]], reasons: list[str],
            bits: str | None = None, addr: int | None = 8, rw: int | None = 0) -> dict:
    r = run(Bus().hdr_ddr(words, bits=bits))
    f = next(x for x in r['frames'] if x['kind'] == 'hdr')
    assert (f['addr'], f['rw']) == (addr, rw), f
    assert [(x['kind'], x['value']) for x in f['fields']] == values, f
    assert f['reasons'] == reasons, f
    if 'hdr_parity' in reasons or 'hdr_crc' in reasons or ('hdr_preamble' in reasons and any(x['kind'] == 'hdr_crc' for x in f['fields'])):
        assert any(not x['ok'] for x in f['fields']), f
    return r


def vectors() -> None:
    cmd, data = 0x1210, 0x1234
    assert independent_parity(cmd) == (1, 1) and independent_parity(data) == (0, 0)
    assert independent_crc([cmd, data]) == 5
    words = [(1, cmd), (2, data)]
    fields = [('hdr_cmd', cmd), ('hdr_data', data), ('hdr_crc', 5)]
    bus = Bus().hdr_ddr(words)
    t_rise = bus.truth[-1][4]
    start = next(i for i, x in enumerate(bus.trans) if x[1:] == ('scl', 0) and x[0] > t_rise)
    level = [v for _, line, v in bus.trans[:start] if line == 'sda'][-1]
    emitted = ''
    for _, line, value in bus.trans[start:]:
        if line == 'sda':
            level = value
        else:
            emitted += str(level)
    assert emitted.startswith(TRUTH), emitted
    r = inspect(words, fields, [])
    f = r['frames'][1]
    sampled = ''.join(str(int(v)) for t, v in zip(r['bits_t'], r['bits_v']) if f['t0'] < t < f['t1'])
    assert sampled.startswith(TRUTH), (sampled, TRUTH)
    assert TRUTH == encoded(1, cmd) + encoded(2, data) + '01110000101'
    multi = [(1, cmd), (2, data), (3, 0xABCD)]
    vals = [('hdr_cmd', cmd), ('hdr_data', data), ('hdr_data', 0xABCD),
            ('hdr_crc', independent_crc([cmd, data, 0xABCD]))]
    inspect(multi, vals, [])
    read = 0x9210
    inspect([(1, read), (2, data)], [('hdr_cmd', read), ('hdr_data', data),
            ('hdr_crc', independent_crc([read, data]))], [], rw=1)
    inspect([(1, cmd), (3, data)], fields[:2], ['hdr_nack'])
    inspect([(1, cmd), (2, data), (2, 0xABCD)], vals[:3], [])
    raw = TRUTH + '00'
    flip = lambda s, i: s[:i] + str(1 - int(s[i])) + s[i + 1:]
    inspect(words, fields, ['hdr_parity'], bits=flip(raw, 19))
    inspect(words, fields[:2] + [('hdr_crc', 4)], ['hdr_crc'], bits=flip(raw, 50))
    inspect(words, fields, ['hdr_preamble'], bits=flip(raw, 42))
    inspect(words, [], ['hdr_preamble'], bits='10' + raw[2:], addr=None, rw=None)
    inspect(words, fields[:1], ['hdr_preamble'], bits=raw[:20] + '00' + raw[22:])
    inspect(words, fields[:1], ['truncated'], bits=raw[:27])
    f = run(Bus().hdr(mode=1))['frames'][1]
    assert not f['fields'] and '未解碼' in f['label']


def mutations() -> None:
    parity, crc, words = i3c_hdr.parity, i3c_hdr.crc5, i3c_hdr.words
    variants = [
        ('P0 未反相', 'parity', lambda v: (parity(v)[0], parity(v)[1] ^ 1)),
        ('CRC 初值為零', 'crc5', lambda values: independent_crc(values, initial=0)),
        ('CRC 含前導碼', 'crc5', lambda values: independent_crc(values, pres=[1] + [2] * (len(values) - 1))),
        ('僅取上升沿', 'words', lambda f, bits: words(f, bits[1::2])),
    ]
    for name, attr, replacement in variants:
        original = getattr(i3c_hdr, attr)
        setattr(i3c_hdr, attr, replacement)
        try:
            try:
                vectors()
            except AssertionError:
                print(f'變異 {name}：已偵測')
            else:
                raise AssertionError(f'未偵測變異：{name}')
        finally:
            setattr(i3c_hdr, attr, original)


if __name__ == '__main__':
    vectors()
    if '--mutations' in sys.argv:
        mutations()
    print('web.i3c_hdr_check self-check OK')
