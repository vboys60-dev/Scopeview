from __future__ import annotations

"""USB PD 手寫參考、向量與介面驗收。"""
from pathlib import Path
import sys
import tempfile
import types
import zlib
from time import perf_counter
import numpy as np
from scope_tool.web import logic, usbpd_decode as dec, usbpd_synth as syn
from scope_tool.web.usbpd_fields import ORDERED

# 41 01 2D 5C BC DF：低 nibble 先；每個 5b 字面值再由右至左送出。
NIBBLES = '1 4 1 0 D 2 C 5 C B F D'
CODES = ('11000', '11000', '11000', '10001', '01001', '01010', '01001', '11110',
         '11011', '10100', '11010', '01011', '11010', '10111', '11101', '11011', '01101')
# 前導碼與 5b 在線上的逐位順序；BMC 每位起點翻轉，1 的中點再翻轉。
WIRE = '0001100011000111000110010010101001001111110110010101011110100101111101101111101110110'
BMC_RUNS = '2112112112112112112112112112112112112112112112112112112112112112112112112112112112112112112112112221111222111122211111122211112211221121121122112211111111111121111221121121121111111121122112111111111121111211111111112111111211112'


def decode(wave: dict, rate: float | None = None, **limits: int) -> dict:
    t, v = syn.render(wave)
    ed, _, end, err = logic.prepare(t, {'cc': v}, {'cc': None}, require_edges=True)
    assert err is None, err
    return dec.run(ed, t1=end, bitrate=rate, **limits)


def invariants(r: dict) -> None:
    assert np.all(np.diff(r['bits_t']) > 0)
    prev = -np.inf
    for i, f in enumerate(r['frames']):
        assert f['i'] == i and prev <= f['t0'] <= f['t1'] <= r['t1']
        prev = f['t1']
        for x in f['fields']:
            assert f['t0'] <= x['t0'] <= x['t1'] <= f['t1']


def references() -> None:
    assert zlib.crc32(bytes.fromhex('41 01')) == 0xdfbc5c2d
    assert zlib.crc32(bytes.fromhex('41 01 2d 5c bc df')) == 0x2144df1c
    assert ''.join(s[::-1] for s in CODES) == WIRE
    # 手寫 5b 與 BMC 直接渲染，不經合成器。
    assert BMC_RUNS == ''.join('11' if bit == '1' else '2' for bit in '01' * 32 + WIRE)
    values = []; level = 0
    for run in BMC_RUNS:
        level ^= 1; values.extend([level] * (16 * int(run)))
    values += [level ^ 1] * 64
    t = np.arange(len(values) + 64) / 9600000
    v = np.r_[np.zeros(64), np.asarray(values)]
    ed, _, end, err = logic.prepare(t, {'cc': v}, {'cc': [.3, .7]}, require_edges=True)
    assert err is None
    r = dec.run(ed, t1=end); invariants(r)
    f = r['frames'][0]
    assert f['label'] == 'SOP GoodCRC' and f['status'] == 'ok', f
    assert [x['value'] for x in f['fields'] if x['kind'] == 'crc'] == [0xdfbc5c2d]


def vectors() -> None:
    for rate in (270000, 300000, 330000):
        for h, objs, name in ((0x0141, (), 'GoodCRC'), (0x1141, (0x12345678,), 'Source_Capabilities'),
                              (0x7141, tuple(range(7)), 'Source_Capabilities'),
                              (0x1142, (0x87654321,), 'Request'), (0x0143, (), 'Accept'),
                              (0x0146, (), 'PS_RDY')):
            r = decode(syn.bus([syn.packet(syn.symbols(h, objs))], bitrate=rate)); invariants(r)
            f = r['frames'][0]
            assert f['status'] == 'ok' and name in f['label'], f
            assert [x['value'] for x in f['fields'] if x['kind'] == 'obj'] == list(objs)
    t, v = syn.render(syn.bus([syn.packet(syn.symbols(0x0141))], bitrate=330000))
    ed, _, end, err = logic.prepare(t, {'cc': v}, {'cc': None}, require_edges=True)
    assert err is None
    e = ed['cc']; times = e.time[(e.value >= 0) & ~e.resync]
    _, _, measured = dec._packet(times, end, None)
    assert abs(measured * 330000 - 1) < .025
    for sop in ("SOP'", 'Hard Reset', 'Cable Reset'):
        codes = list(next(k for k, v in ORDERED.items() if v == sop)) if 'Reset' in sop else syn.symbols(0x0141, sop=sop)
        f = decode(syn.bus([syn.packet(codes)]))['frames'][0]
        assert sop in f['label'] and f['status'] == 'ok', f
    for codes, expected in ((syn.symbols(0x0141, crc=0), 'crc'),
                            (syn.symbols(0x0141, eop=False), 'bad_eop')):
        assert expected in decode(syn.bus([syn.packet(codes)]))['frames'][0]['reasons']
    codes = syn.symbols(0x0141); codes[5] = 0
    assert 'invalid_5b' in decode(syn.bus([syn.packet(codes)]))['frames'][0]['reasons']
    p = syn.packet(syn.symbols(0x0141))
    r = decode(syn.bus([p, p], gap=4)); invariants(r)
    assert len(r['frames']) == 2
    assert decode(syn.bus([p, p]), max_frames=1)['truncated']
    assert decode(syn.bus([p, p]), max_fields=4)['truncated']
    cut = decode(syn.bus([p[50:], p]))
    assert cut['frames'][0]['kind'] == 'partial' and cut['frames'][1]['label'] == 'SOP GoodCRC'
    assert 'bad_eop' in decode(syn.bus([p[:110]]))['frames'][0]['reasons']


def api_and_performance() -> None:
    from scope_tool.web.analysis_api import Analysis
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'pd.csv'; spec = syn.fixture(path)
        api = Analysis(); api.open_waveform(str(path))
        summary = api.decode('usbpd', spec['channels'], {'cc': None}, spec['options'])
        assert summary['ok'], summary
        fs = api.decode_frames(summary['decode_id'])['frames']
        assert 1 < len(fs) < 2000 and set(spec['expect_kinds']) <= {f['kind'] for f in fs}
    n = 10000000; t = np.arange(n) / 12000000; v = np.zeros(n)
    _, sample = syn.render(syn.bus([syn.packet(syn.symbols(0x0141))]))
    v[:len(sample)] = sample
    start = perf_counter()
    ed, _, end, err = logic.prepare(t, {'cc': v}, {'cc': None}, require_edges=True)
    assert err is None and dec.run(ed, t1=end)['frames'][0]['status'] == 'ok'
    elapsed = perf_counter()-start
    assert elapsed <= 15, elapsed
    print(f'10M 點：{elapsed:.3f} 秒')


def mutations() -> None:
    global dec
    source = Path(dec.__file__).read_text(); original = dec
    changes = [('5b 位元順序', 'bits[pos+j] << j', 'bits[pos+j] << (4-j)'),
               ('nibble 順序', 'nibbles[j] | (nibbles[j+1] << 4)', '(nibbles[j] << 4) | nibbles[j+1]'),
               ('CRC 位元組順序', "int.from_bytes(raw[offset:needed], 'little')", "int.from_bytes(raw[offset:needed], 'big')"),
               ('BMC 門檻', '.75 * ui', '.5 * ui'),
               ('UI 跟隨', 'ui = .9 * ui + .1 * duration', 'ui = 1 / 300000')]
    for name, before, after in changes:
        assert before in source
        m = types.ModuleType('scope_tool.web._usbpd_mutation')
        exec(compile(source.replace(before, after), '<USB PD 變異>', 'exec'), m.__dict__)
        dec = m
        try:
            vectors()
        except (AssertionError, IndexError, ValueError, StopIteration):
            print(f'變異已抓到：{name}')
        else:
            raise AssertionError(f'變異漏網：{name}')
        finally:
            dec = original


if __name__ == '__main__':
    references(); vectors(); api_and_performance()
    if '--mutations' in sys.argv: mutations()
    print('web.usbpd_check self-check OK')
