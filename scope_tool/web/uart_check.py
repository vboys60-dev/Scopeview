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
from scope_tool.web.uart_vectors import vectors, raw, differential_checks


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


def estimation() -> None:
    from scope_tool.web.logic import prepare
    for baud in (None, 0, -1, '錯誤', True, float('nan')):
        assert dec.options({'estimate': True, 'baud': baud}, {})['estimate'] is True
    assert dec.options({'estimate': True}, {})['estimate'] is True
    for baud in dec.STANDARD_BAUD:
        for bits, parity, stop in ((8, 'N', 1), (7, 'E', 1), (9, 'O', 2)):
            line = uart_line([0x55, 0x41, 0x33] * 3, baud=baud, bits=bits, parity=parity, stop=stop)
            for levels in ((0., 3.3), (12., -12.)):
                t, v = render(line, fs=baud * 64, levels=levels)
                used, message = dec.estimate_waveforms(t, {'tx': v}, {'tx': None})
                expected = 921600 if baud == 1000000 else baud  # 8% 容差重疊時依規則取最低值。
                assert message.startswith(f'估計鮑率 {expected}；'), (baud, message)
                assert used['tx'] is not None
    t = np.arange(10000) / 1e6
    rng = np.random.default_rng(11)
    for v in (rng.normal(size=len(t)), np.where(t < .005, 0., 3.3)):
        _, message = dec.estimate_waveforms(t, {'tx': v}, {'tx': [1., 2.]})
        assert message.startswith('無法估計鮑率：'), message
    # 雙 bit 脈寬的週期為兩倍；最低通過鮑率因此是一半，無法從邊緣區分。
    b = raw([(i * 2, i % 2) for i in range(20)], 42)
    assert dec.estimate_lane(edge(b), 1 / (9600 * 64))[0] == 4800
    assert dec.estimate_lane(edge(uart_line([0x55] * 3)), 1 / 9600)[0] is None
    # 一條閒置線不阻止另一條估計；未知區段的 resync 不當邊緣。
    t, v = render(uart_line([0x55] * 3))
    _, message = dec.estimate_waveforms(t, {'tx': np.ones_like(v), 'rx': v}, {'tx': None, 'rx': None})
    assert message.startswith('估計鮑率 9600；')
    e = prepare(t, {'tx': v}, {'tx': None}, require_edges=False)[0]['tx']
    assert dec.estimate_lane(e, float(np.min(np.diff(t))))[0] == 9600
    # 毛刺短於兩取樣間隔時忽略；NaN 的兩端不可拼成假脈寬。
    noisy = e._replace(time=np.r_[e.time[:2], e.time[1] + 1e-7, e.time[1] + 2e-7, e.time[2:]],
                       value=np.r_[e.value[:2], 1, 0, e.value[2:]], resync=np.r_[e.resync[:2], False, False, e.resync[2:]])
    assert dec.estimate_lane(noisy, 1 / (9600 * 64))[0] == 9600
    short = edge(uart_line([0x55]))
    short = short._replace(resync=np.ones_like(short.resync))
    assert dec.estimate_lane(short, 1 / (9600 * 64))[0] is None
    # 兩線都可估時以有效間距較多者為準。
    slow, fast = uart_line([0x55] * 3), uart_line([0x55] * 10, baud=19200)
    tt, tx, rx = render(slow, fast, fs=19200 * 64)
    assert dec.estimate_waveforms(tt, {'tx': tx, 'rx': rx}, {'tx': None, 'rx': None})[1].startswith('估計鮑率 19200；')
    for bad in ({'estimate': 1}, {'estimate': False}, {'estimate': True, 'bits': 3}):
        try:
            dec.options(bad, {})
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    from scope_tool.web.analysis_api import Analysis
    from scope_tool.contracts import Waveform
    api = Analysis()
    api._gen, api._waves = 1, [Waveform('CH1', t, v)]
    good = api.decode('uart', {'tx': 'CH1'}, {'tx': None}, {'baud': 9600})
    before = api.decode_frames(good['decode_id'])
    for lane in ('tx', 'rx'):
        summary = api.decode('uart', {lane: 'CH1'}, {lane: None}, {'estimate': True})
        assert not summary['ok'] and summary['reason'].startswith('估計鮑率 9600；')
        assert api.decode_frames(good['decode_id']) == before
    print('鮑率估計：16 種標準值／8N1／7E1／9O2／反相／雜訊／少邊緣／雙 bit 歧義：OK')


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
    estimation()
    performance()
    differential_checks()
    if '--mutations' in sys.argv:
        mutations()
        try:
            differential_checks(mutation=True)
        except AssertionError:
            print('變異已抓到：移除 DIFF')
        else:
            raise AssertionError('變異漏網：移除 DIFF')
    print('web.uart_check self-check OK')
