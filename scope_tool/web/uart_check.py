from __future__ import annotations

"""UART 合成、手寫真值、不變量、資源界線與五項變異驗收。"""
from pathlib import Path
from time import perf_counter
import platform
import sys
import types
import numpy as np
from scope_tool.web import uart_decode as dec
from scope_tool.web.logic import to_edges
from scope_tool.web.uart_synth import uart_line, edge, render
from scope_tool.web.uart_vectors import vectors, raw


def fields(r: dict) -> list:
    return [x for f in r['frames'] for x in f['fields']]


def invariants(r: dict) -> None:
    assert np.all(np.diff(r['bits_t']) > 0)
    assert set(r['bits_v']) <= {-1, 0, 1}
    previous = -np.inf
    allowed = {'framing', 'parity', 'short_stop', 'break', 'truncated', 'unsynced', 'unknown_bit'}
    for i, f in enumerate(r['frames']):
        assert f['i'] == i and previous <= f['t0'] <= f['t1'] <= r['t1']
        previous = f['t1']
        assert set(f['reasons']) <= allowed
        for x in f['fields']:
            assert f['t0'] <= x['t0'] <= x['t1'] <= f['t1'], (f, x)
            assert x['kind'] in ('tx', 'rx')
    assert len(r['bits_t']) == sum(x['nbits'] for x in fields(r) if x['kind'] == 'tx')


def protocol_vectors() -> None:
    for name, b, o, expected, codes in vectors():
        r = dec.run({'tx': edge(b)}, t1=b['end'], **o)
        got = [x['value'] for x in fields(r)]
        assert got == expected, (name, got, expected)
        actual = set(c for f in r['frames'] for c in f['reasons'])
        assert codes <= actual, (name, actual, codes)
        invariants(r)
        if name in ('U06', 'false start 0.3T'):
            assert any('false start 1' in w for w in r['warnings'])
        if name == 'U14':
            assert any('可能需切換反相' in w for w in r['warnings'])
        if name == 'U10':
            assert not fields(r)[1]['ok']
    for parity in ('N', 'E', 'O', 'M', 'S'):
        b = uart_line([0x12, 0xA5], parity=parity)
        r = dec.run({'tx': edge(b)}, t1=b['end'], baud=9600, parity=parity)
        assert all(x['ok'] for x in fields(r))
        assert [x['value'] for x in fields(r)] == [0x12, 0xA5]
    print(f'協定向量 {len(vectors())} 組、N/E/O/M/S：OK')


def handwritten() -> None:
    # H1 逐轉換手寫 9600 8N1 55；不透過符號編碼器產生。
    b = raw([(0, 1), (2, 0), (3, 1), (4, 0), (5, 1), (6, 0),
             (7, 1), (8, 0), (9, 1), (10, 0), (11, 1)], 14)
    r = dec.run({'tx': edge(b)}, t1=b['end'], baud=9600)
    assert [x['value'] for x in fields(r)] == [0x55]
    assert np.allclose(r['bits_t'], (np.arange(8) + 3.5) / 9600, atol=1e-15, rtol=0)
    assert r['bits_v'].tolist() == [1, 0, 1, 0, 1, 0, 1, 0]
    invariants(r)
    print('手寫真值 H1：OK')


def quality() -> None:
    a, b = uart_line([0x41]), uart_line([0x42])
    b['trans'] = [(t + .3 / 9600, v) for t, v in b['trans']]
    b['trans'].insert(0, (0., 1))
    b['end'] += .3 / 9600
    r = dec.run({'tx': edge(a), 'rx': edge(b)}, t1=b['end'], baud=9600)
    assert len(r['frames']) == 1
    assert [(x['kind'], x['value']) for x in fields(r)] == [('tx', 0x41), ('rx', 0x42)]
    invariants(r)
    for gap, count in ((10, 1), (30, 2)):
        a = uart_line([0x41, 0x42], gaps=gap)
        r = dec.run({'tx': edge(a)}, t1=a['end'], baud=9600)
        assert len(r['frames']) == count
    a = uart_line([0x41, 0x42])
    for seed in range(20):
        r = dec.decode_waveforms(*render(a, noise=.07, seed=seed), baud=9600)
        assert [x['value'] for x in fields(r)] == [0x41, 0x42]
        assert all(x['ok'] for x in fields(r))
    for levels, invert in (((12., -12.), True), ((1.2, -1.2), True), ((0., 3.3), False)):
        r = dec.decode_waveforms(*render(a, levels=levels), baud=9600, invert=invert)
        assert [x['value'] for x in fields(r)] == [0x41, 0x42]
    t, v = render(a, nan=(('tx', 5.2 / 9600, 5.8 / 9600),))
    r = dec.decode_waveforms(t, v, baud=9600)
    assert fields(r)[0]['value'] is None and 'unknown_bit' in r['frames'][0]['reasons']
    assert -1 in r['bits_v']
    invariants(r)
    x_mark()
    # HUNT 首候選無效：完整消耗其區間，不重複嘗試資料下降緣。
    a = raw([(0, 0), (1, 1), (2, 0), (4, 1), (5, 0), (13, 1)], 15)
    r = dec.run({'tx': edge(a)}, t1=a['end'], baud=9600)
    assert not fields(r) and all(f['kind'] == 'unsynced' for f in r['frames'])
    a = uart_line([0x41])
    t, v = render(a)
    r = dec.decode_waveforms(t, v, np.full_like(v, 3.3), baud=9600,
                             thresholds={'rx': (1., 2.)})
    assert r['ok'] and len(fields(r)) == 1
    r = dec.decode_waveforms(t, v, np.full_like(v, 3.3), baud=9600)
    assert not r['ok'] and 'RX' in r['reason'] and '；請改用手動門檻' in r['reason']
    r = dec.decode_waveforms(*render(a, fs=9600 * 6), baud=9600)
    assert any('取樣不足' in w for w in r['warnings'])
    for bad in ({}, {'baud': 0}, {'baud': float('nan')}, {'baud': True}, {'baud': 9600, 'stop': 1.5},
                {'baud': 9600, 'bits': 4}, {'baud': 9600, 'parity': 'Z'},
                {'baud': 9600, 'invert': 1}, {'baud': 9600, 'extra': 1}, None):
        try:
            dec.options(bad, {})
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    # SYNCED 的 false start 也必須重新要求連續 mark，不可沿用已同步資格。
    from scope_tool.web.uart_vectors import prefixed
    b = prefixed(raw([(0, 1), (.2, 0), (.5, 1), (1, 0), (10, 1),
                      (12, 0), (13, 1), (14, 0), (19, 1), (20, 0), (21, 1)], 24))
    rr = dec.run({'tx': edge(b)}, t1=b['end'], baud=9600)
    assert [x['value'] for x in fields(rr)] == [0x55, 0x41]
    limits()
    print('雙線／分組／20 seed／電氣／NaN／mark／false start／固定線／上限：OK')


def x_mark() -> None:
    a = raw([(0, 1), (2, -1), (2.2, 0), (11.2, 1), (14.2, 0), (15.2, 1),
             (16.2, 0), (21.2, 1), (22.2, 0), (23.2, 1)], 26)
    r = dec.run({'tx': edge(a)}, t1=a['end'], baud=9600)
    assert [x['value'] for x in fields(r)] == [0x41], fields(r)
    b = raw([(0, 1), (2, -1), (3, 1), (3.5, 0), (12.5, 1),
             (14.5, 0), (15.5, 1), (16.5, 0), (21.5, 1), (22.5, 0), (23.5, 1)], 26)
    rr = dec.run({'tx': edge(b)}, t1=b['end'], baud=9600)
    assert [x['value'] for x in fields(rr)] == [0x41]


def limits() -> None:
    a = uart_line([0x41, 0x42, 0x43], gaps=40)
    waves = render(a)
    for kw in ({'max_frames': 1}, {'max_fields': 1}, {'max_edges': 12}):
        r = dec.decode_waveforms(*waves, baud=9600, **kw)
        assert r['truncated'] and r['warnings']
        invariants(r)
        if 'max_frames' in kw:
            assert len(r['frames']) == 1
        if 'max_fields' in kw:
            assert len(fields(r)) == 1
        if 'max_edges' in kw:
            e = to_edges(*waves, *r['thresholds']['tx'], max_edges=12)
            assert r['t1'] == e.time[-1]
    a = uart_line([0x41, 0x42, 0x43])
    r = dec.decode_waveforms(*render(a), baud=9600, max_fields=1)
    invariants(r)
    assert len(fields(r)) == 1
    b = uart_line([0x55, 0x56])
    b['trans'] = [(tm + .3 / 9600, v) for tm, v in b['trans']]
    b['trans'].insert(0, (0., 1))
    rr = dec.run({'tx': edge(a), 'rx': edge(b)}, t1=a['end'], baud=9600, max_fields=1)
    invariants(rr)
    assert len(fields(rr)) == 1
    e = edge(raw([(1, 0), (2, 1)], 4))
    assert dec._levels_at(e, np.array([0., 1., 2., 4., 5.]) / 9600, 4 / 9600).tolist() == [-1, 0, 1, 1, -1]
    for key in ('max_frames', 'max_fields', 'max_edges'):
        try:
            dec.decode_waveforms(*waves, baud=9600, **{key: 0})
        except ValueError:
            pass
        else:
            raise AssertionError(key)


def performance() -> None:
    n = 10_000_000
    tt = np.arange(n) / (9600 * 64)
    aa, bb = np.full(n, 3.3), np.full(n, 3.3)
    t, a, b = render(uart_line([0x41, 0x42]), uart_line([0x55]))
    aa[:len(a)], bb[:len(b)] = a, b
    start = perf_counter()
    r = dec.decode_waveforms(tt, aa, bb, baud=9600)
    elapsed = perf_counter() - start
    assert [(x['kind'], x['value']) for x in fields(r)] == [('tx', 0x41), ('rx', 0x55), ('tx', 0x42)]
    invariants(r)
    print(f'效能 10M×2：{elapsed:.3f} s；{platform.platform()}')
    assert elapsed <= 15


def mutations() -> None:
    global dec
    original, source = dec, Path(dec.__file__).read_text()
    changes = [('E/O 對調', "'E': int(data.sum()) % 2, 'O': 1 - int(data.sum()) % 2", "'O': int(data.sum()) % 2, 'E': 1 - int(data.sum()) % 2"),
               ('取樣偏移', '(np.arange(total) + .5)', '(np.arange(total) + 0.)'),
               ('SYNCED 要求 mark', 'synced or (last_rise', 'False or (last_rise'),
               ('MSB first', 'int(v) << k', 'int(v) << (d - 1 - k)'),
               ('X 不清 mark', 'if val < 0:\n            last_rise = None', 'if val < 0:\n            pass')]
    for name, before, after in changes:
        assert before in source, name
        module = types.ModuleType('scope_tool.web._uart_mutation')
        exec(compile(source.replace(before, after), '<UART 變異>', 'exec'), module.__dict__)
        dec = module
        try:
            handwritten()
            protocol_vectors()
            x_mark()
        except AssertionError:
            print(f'變異已抓到：{name}')
        else:
            raise AssertionError(f'變異漏網：{name}')
        finally:
            dec = original


if __name__ == '__main__':
    handwritten()
    protocol_vectors()
    quality()
    performance()
    if '--mutations' in sys.argv:
        mutations()
    print('web.uart_check self-check OK')
