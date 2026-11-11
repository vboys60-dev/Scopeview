from __future__ import annotations

"""CAN 手寫參考、序列表 CRC 與解碼閉環驗收。"""
import csv
from pathlib import Path
import sys
import types
import tempfile
import platform
from time import perf_counter
import numpy as np
from scope_tool.web import logic, can_decode as dec
from scope_tool.web.can_synth import bits, can_bus, can_frame, crc15, render

H1 = '000100100011000001100001001000110100011011010110111'
H2 = '00000110101011111100110111101111000000110100101'
CSV = Path('X6000A-解碼/CAN/x6000can.csv')


def independent_crc(data: list[int]) -> int:
    """以多項式長除法計算，不使用合成器或解碼器的 CRC。"""
    value = int(''.join(map(str, data)) + '0' * 15, 2)
    poly = (1 << 15) | 0x4599
    while value.bit_length() > 15:
        value ^= poly << (value.bit_length() - 16)
    return value


def rows() -> list[tuple]:
    with CSV.open(encoding='utf-8-sig', newline='') as stream:
        return [(int(r['ID'], 16), len(r['ID']) > 3, r['Type'] == 'RMT', int(r['DLC']),
                 bytes.fromhex(r['Data']), int(r['CRC'], 16)) for r in csv.DictReader(stream) if r['CRC']]


def payload(id: int, ext: bool, rtr: bool, dlc: int, data: bytes) -> list[int]:
    header = (bits(id >> 18, 11) + [1, 1] + bits(id & 0x3ffff, 18) + [int(rtr), 0, 0]
              if ext else bits(id, 11) + [int(rtr), 0, 0])
    return [0] + header + bits(dlc, 4) + ([] if rtr else [v for byte in data for v in bits(byte, 8)])


def decode(bus: dict, *, fs: float = 16000000, offset: float = 0, **limits: int) -> dict:
    t, h, l = render(bus, fs=fs, differential=True, offset=offset)
    edges, _, end, error = logic.prepare(t, {'can': h-l}, {'can': None}, require_edges=True,
                                         max_edges=limits.pop('max_edges', 10000000))
    assert error is None, error
    return dec.run(edges, t1=end, max_frames=limits.get('max_frames', 100000),
                          max_fields=limits.get('max_fields', 100000), bitrate=500000,
                          sample_point=75, dominant_high=True)


def invariants(result: dict) -> None:
    assert np.all(np.diff(result['bits_t']) > 0)
    previous = -np.inf
    for i, frame in enumerate(result['frames']):
        assert frame['i'] == i and previous <= frame['t0'] <= frame['t1'] <= result['t1']
        previous = frame['t1']
        for field in frame['fields']:
            assert frame['t0'] <= field['t0'] <= field['t1'] <= frame['t1']


def verify(result: dict, id: int, dlc: int, data: bytes, expected_crc: int, kind: str = 'data',
           crc_ok: bool = True) -> None:
    invariants(result)
    f = next(f for f in result['frames'] if f['kind'] == kind)
    assert f['addr'] == id
    fields = f['fields']
    assert next(x['value'] for x in fields if x['kind'] == 'dlc') == dlc
    assert [x['value'] for x in fields if x['kind'] == 'data'] == list(data)
    c = next(x for x in fields if x['kind'] == 'crc')
    assert c['value'] == expected_crc and c['ok'] == crc_ok


def references() -> None:
    assert independent_crc([int(x) for x in H2]) == 0xd9
    assert independent_crc([int(b) for c in b'123456789' for b in f'{c:08b}']) == 0x059e
    assert ''.join(map(str, can_frame(0x123, [0x12, 0x34])[:-10])) == H1
    entries = rows()
    matches = sum(independent_crc(payload(i, e, r, d, b)) == c for i, e, r, d, b, c in entries)
    assert len(entries) == 209 and matches >= 208, (len(entries), matches)
    bad = [(i, c, independent_crc(payload(i, e, r, d, b))) for i, e, r, d, b, c in entries if independent_crc(payload(i, e, r, d, b)) != c]
    assert len(bad) == 1 and bad[0][0] == 0x0296a95d, bad
    print(f'獨立 CRC 與序列表：{matches}/{len(entries)}；0x0296A95D 不吻合 {bad[0][1]:04X}/{bad[0][2]:04X}')


def vectors() -> None:
    cases = [(0x123, False, False, 2, bytes([0x12, 0x34]), 0x36b7),
             (0x1abcdef, True, False, 1, bytes([0xa5]), 0xd9),
             (0x123, False, True, 4, b'', 0x4352),
             (0x123, False, False, 0, b'', None),
             (0x123, False, False, 9, bytes(range(8)), None)]
    for i, ext, rtr, dlc, data, crc in cases:
        expected = crc if crc is not None else independent_crc(payload(i, ext, rtr, dlc, data))
        b = can_bus([can_frame(i, data, ext=ext, rtr=rtr, dlc=dlc)])
        verify(decode(b), i, dlc, data, expected, 'remote' if rtr else 'data')
    ext_result = decode(can_bus([can_frame(0x1abcdef, [0xa5], ext=True)]))
    assert ext_result['frames'][0]['label'] == 'EXT 0x1ABCDEF'
    assert list(ext_result['bits_v']).count(2) == 4
    for slow in (0.01, 0.05):
        r = decode(can_bus([can_frame(0x123, [0x12, 0x34])], slow=slow))
        verify(r, 0x123, 2, b'\x12\x34', 0x36b7)
        if slow == .05:
            assert any('timing' in f['reasons'] for f in r['frames'])
    b = can_bus([can_frame(0x123, [0x12, 0x34], ack=False)])
    assert any('no_ack' in f['reasons'] for f in decode(b)['frames'])
    b = can_bus([can_frame(0x123, [0x12, 0x34])] * 2)
    assert len([f for f in decode(b)['frames'] if f['kind'] == 'data']) == 2
    verify(decode(b, offset=2), 0x123, 2, b'\x12\x34', 0x36b7)
    print('基本向量、慢速、共模偏移與背靠背：OK')


def closed_loop() -> None:
    for i, ext, rtr, dlc, data, crc in rows():
        b = can_bus([can_frame(i, data, ext=ext, rtr=rtr, dlc=dlc, crc=crc)])
        valid = independent_crc(payload(i, ext, rtr, dlc, data)) == crc
        verify(decode(b), i, dlc, data, crc, 'remote' if rtr else 'data', valid)
    print('序列表 209 列合成閉環：OK')



def wire(stream: list[int], *, points: int = 32, nan_bit: int | None = None) -> dict:
    """以手寫線上位元直接產生波形，不經 CAN 合成器。"""
    t = np.arange(len(stream) * points) * (2e-6 / points)
    v = np.repeat([2. if b == 0 else 0. for b in stream], points)
    if nan_bit is not None:
        v[nan_bit * points:(nan_bit + 1) * points] = np.nan
    edges, _, end, err = logic.prepare(t, {'can': v}, {'can': [.5, 1.5]}, require_edges=False)
    assert err is None, err
    result = dec.run(edges, t1=end, bitrate=500000)
    invariants(result)
    return result


def scenarios() -> None:
    one = [int(c) for c in H1] + [1, 0, 1] + [1] * 7
    prefix, tail = [1] * 11, [1] * 14
    r = wire(prefix + one + tail)
    f = r['frames'][0]
    verify(r, 0x123, 2, b'\x12\x34', 0x36b7)
    assert f['label'] == 'STD 0x123 DLC 2' and f['ack'] and f['status'] == 'ok'
    assert list(r['bits_v']).count(2) == 1
    assert next(x for x in f['fields'] if x['kind'] == 'eof')['value'] == 127
    r = wire(prefix + one + tail, points=4)
    verify(r, 0x123, 2, b'\x12\x34', 0x36b7)
    assert any('取樣不足' in w for w in r['warnings'])
    r = wire(prefix + one[:19] + [0] * 6 + one[25:] + tail)
    assert 'stuff' in r['frames'][0]['reasons'] and abs(r['frames'][0]['t1'] - 35 * 2e-6) < 2e-7
    assert not any(f['kind'] == 'data' and f['status'] == 'ok' for f in r['frames'])
    r = wire(one[20:] + [1] * 11 + one + tail)
    assert r['frames'][0]['kind'] == 'partial' and r['frames'][0]['reasons'] == ['truncated']
    assert r['frames'][-1]['kind'] == 'data' and r['frames'][-1]['addr'] == 0x123
    r = wire(prefix + one[:40])
    assert r['frames'][0]['reasons'] == ['truncated'] and not any(x['kind'] == 'crc' for x in r['frames'][0]['fields'])
    r = wire(prefix + one, nan_bit=20)
    assert 'unknown_bit' in r['frames'][0]['reasons']
    assert abs(r['frames'][0]['t1'] - 20 * 2e-6) < 2e-7
    r = wire(prefix + one[:-1] + [0] + [1] * 3 + one + tail)
    assert [f['addr'] for f in r['frames']] == [0x123, 0x123]
    r = wire(prefix + one + [0] * 6 + [1] * 11 + one + tail)
    assert [f['kind'] for f in r['frames']] == ['data', 'error_flag', 'data']
    flag = r['frames'][1]
    assert flag['status'] == 'error' and 'error_flag' in flag['reasons']
    assert abs((flag['t1'] - flag['t0']) / 2e-6 - 14) < .1
    r = wire([0] * 6 + [1] * 11 + one + tail)
    assert [f['kind'] for f in r['frames']] == ['error_flag', 'data']
    assert r['frames'][0]['t0'] == 0 and 'truncated' in r['frames'][0]['reasons']
    r = wire([1] * 3 + [0] * 6 + [1] * 11 + one + tail)
    assert [f['kind'] for f in r['frames']] == ['error_flag', 'data']
    r = wire([1] * 3 + [0] * 4 + [1] * 11 + one + tail)
    assert not any(f['kind'] == 'error_flag' for f in r['frames'])
    assert [f['kind'] for f in r['frames']] == ['partial', 'data']
    r = wire([1] * 3 + [0] * 6 + [1] * 4 + [0] * 6 + tail)
    assert 'form' in r['frames'][0]['reasons']
    bad = can_frame(0x123, [0x92, 0x34], crc=0x36b7)
    r = wire(prefix + bad[:-7] + [0] * 6 + [1] * 11 + one + tail)
    f, flag = r['frames'][:2]
    crc_field = next(x for x in f['fields'] if x['kind'] == 'crc')
    assert 'crc' in f['reasons'] and crc_field['ok'] is False and crc_field['value'] == 0x36b7
    assert [x['value'] for x in f['fields'] if x['kind'] == 'data'] == [0x92, 0x34]
    assert not any(x['kind'] == 'eof' for x in f['fields']) and abs(f['t1'] - flag['t0']) < 2e-7
    broken = can_frame(0x123, [0x12, 0x34], stuff_break=1)
    idx = next(i for i in range(5, len(broken)) if len(set(broken[i-5:i+1])) == 1)
    r = wire(prefix + broken[:idx] + [0] * 6 + [1] * 11 + one + tail)
    assert 'stuff' in r['frames'][0]['reasons'] and r['frames'][1]['kind'] == 'error_flag'
    assert abs(r['frames'][0]['t1'] - r['frames'][1]['t0']) < 2e-7
    assert abs(r['frames'][0]['t1'] - (11 + idx) * 2e-6) < 2e-7
    r = wire(prefix + one[:-10] + [0] * 6 + [1] * 11 + one + tail)
    assert 'form' in r['frames'][0]['reasons'] and r['frames'][1]['kind'] == 'error_flag'
    assert abs(r['frames'][0]['t1'] - r['frames'][1]['t0']) < 2e-7
    fd = one.copy()
    fd[14] = 1
    r = wire(prefix + fd + [1] * 11 + one + tail)
    assert r['frames'][0]['kind'] == 'fd' and r['frames'][0]['reasons'] == ['fd_unsupported']
    assert [x['kind'] for x in r['frames'][0]['fields']] == ['id', 'ctrl']
    assert r['frames'][-1]['addr'] == 0x123 and r['frames'][-1]['kind'] == 'data'
    # ponytail: 尖峰短於半位元且避開取樣點，確認不影響重新對齊。
    stream = prefix + one + tail
    t = np.arange(len(stream) * 32) * (2e-6 / 32)
    v = np.repeat([2. if bit == 0 else 0. for bit in stream], 32)
    v[(11 + 3) * 32 + 2:(11 + 3) * 32 + 10] = 2.
    ed, _, end, err = logic.prepare(t, {'can': v}, {'can': [.5, 1.5]}, require_edges=False)
    assert err is None
    verify(dec.run(ed, t1=end, bitrate=500000), 0x123, 2, b'\x12\x34', 0x36b7)
    print('手寫位元、旗標、錯誤、截斷及混排：OK')


def limits_and_api() -> None:
    from scope_tool.web.analysis_api import Analysis
    from scope_tool.web.can_synth import fixture
    b = can_bus([can_frame(0x123, [0x12, 0x34])] * 3)
    full = decode(b)
    for key, value in [('max_frames', 1), ('max_fields', len(full['frames'][0]['fields'])), ('max_edges', 12)]:
        r = decode(b, **{key: value})
        invariants(r)
        assert r['truncated'] and any('只解到 t=' in w for w in r['warnings'])
        assert all(t < r['t1'] for t in r['bits_t'])
        if key != 'max_edges':
            assert abs(r['t1'] - full['frames'][1]['t0']) < 1e-12
    t = np.arange(100) * 1e-7
    for v in (np.zeros(100), np.full(100, 2.)):
        ed, _, end, err = logic.prepare(t, {'can': v}, {'can': [.5, 1.5]}, require_edges=False)
        assert err is None
        invariants(dec.run(ed, t1=end, bitrate=500000))
        assert 'CAN 無有限高低平台' in logic.prepare(t, {'can': v}, {'can': None}, require_edges=False)[3]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'can.csv'
        spec = fixture(path)
        api = Analysis()
        api.open_waveform(str(path))
        summary = api.decode('can', spec['channels'], {'can': None}, spec['options'])
        assert summary['ok'], summary
        frames = api.decode_frames(summary['decode_id'])['frames']
        assert {'data', 'remote'} <= {f['kind'] for f in frames}
    print('上限、固定電位及 Analysis 實際檔案：OK')


def performance() -> None:
    n = 10_000_000
    t = np.arange(n) / 16000000
    h, l = np.full(n, 2.5), np.full(n, 2.5)
    _, a, b = render(can_bus([can_frame(0x123, [0x12, 0x34])]), differential=True)
    h[:len(a)], l[:len(b)] = a, b
    start = perf_counter()
    edges, _, end, err = logic.prepare(t, {'can': h-l}, {'can': None}, require_edges=False)
    assert err is None
    r = dec.run(edges, t1=end, bitrate=500000)
    elapsed = perf_counter() - start
    verify(r, 0x123, 2, b'\x12\x34', 0x36b7)
    print(f'效能 10M×2：{elapsed:.3f} s；{platform.platform()}；{platform.machine()}')
    assert elapsed <= 15


def mutations() -> None:
    global dec
    from scope_tool.web import can_fields
    original = dec
    ds, fs = Path(dec.__file__).read_text(), Path(can_fields.__file__).read_text()
    changes = [
        ('填充門檻', 'fields', 'self.rl == 5', 'self.rl == 6', scenarios),
        ('CRC 多項式', 'fields', 'POLY = 0x4599', 'POLY = 0x4598', scenarios),
        ('重新對齊', 'fields', 'self.sync += (r - n) * T', 'self.sync += 0 * T', vectors),
        ('DLC 截斷', 'decode', 'min(dv, 8)', 'dv', vectors),
        ('框尾 idle', 'decode', "mode = 'inter'", "mode = 'idle'", scenarios),
    ]
    for name, target, before, after, check in changes:
        source = fs if target == 'fields' else ds
        assert before in source, name
        fieldmod = types.ModuleType('scope_tool.web._can_fields_mutation')
        exec(compile(source.replace(before, after) if target == 'fields' else fs, '<CAN 欄位變異>', 'exec'), fieldmod.__dict__)
        module = types.ModuleType('scope_tool.web._can_decode_mutation')
        source = ds.replace(before, after) if target == 'decode' else ds
        source = source.replace('from scope_tool.web.can_fields import Bus, Reader, Stop, crc15, field',
                                'Bus, Reader, Stop, crc15, field = _fields.Bus, _fields.Reader, _fields.Stop, _fields.crc15, _fields.field')
        module.__dict__['_fields'] = fieldmod
        exec(compile(source, '<CAN 解碼變異>', 'exec'), module.__dict__)
        dec = module
        try:
            check()
        except (AssertionError, StopIteration, IndexError):
            print(f'變異已抓到：{name}')
        else:
            raise AssertionError(f'變異漏網：{name}')
        finally:
            dec = original


if __name__ == '__main__':
    references()
    vectors()
    scenarios()
    closed_loop()
    limits_and_api()
    performance()
    if '--mutations' in sys.argv:
        mutations()
    print('web.can_check self-check OK')
