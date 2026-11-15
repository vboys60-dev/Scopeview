from __future__ import annotations

"""SPI 手寫真值、合成波形及資源界線檢查。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import sys
import types
import numpy as np
from scope_tool.web import spi_decode as dec
from scope_tool.web.logic import Edges, prepare
from scope_tool.web.spi_synth import spi_bus, edges, fixture


def values(r: dict, lane: str) -> list:
    return [x['value'] for f in r['frames'] for x in f['fields'] if x['kind'] == lane]


def invariants(r: dict) -> None:
    assert np.all(np.diff(r['bits_t']) > 0)
    assert all(a['t1'] <= b['t0'] for a, b in zip(r['frames'], r['frames'][1:]))
    for i, f in enumerate(r['frames']):
        assert f['i'] == i and f['t0'] <= f['t1'] <= r['t1']
        assert set(f['reasons']) <= {'incomplete', 'truncated', 'clk_phase', 'unknown_bit', 'no_cs'}
        assert all(f['t0'] <= x['t0'] <= x['t1'] <= f['t1'] for x in f['fields'])


def handwritten() -> None:
    def edge(times: list, vals: list) -> Edges:
        return Edges(np.array(times, dtype=float), np.array(vals, dtype=np.int8),
                     np.array([True] + [False]*(len(times)-1)), [], 32, 0, False)
    e = {'sclk': edge(list(range(18)), [0]+[1, 0]*8+[0]),
         'mosi': edge([0, 2, 6, 8, 10, 14], [1, 0, 1, 0, 1, 0]),
         'miso': edge([0, 4, 6, 8, 12, 14], [0, 1, 0, 1, 0, 1]),
         'cs': edge([0, .5, 17.5], [1, 0, 1])}
    r = dec.run(e, t1=18)
    assert values(r, 'mosi') == [0x96] and values(r, 'miso') == [0x2d]
    invariants(r)


def vectors(module: types.ModuleType = dec, only: str | None = None) -> None:
    for name, mode in [('T1', 0), ('T2', 3), ('T3a', 1), ('T3b', 2)]:
        if only and name != only:
            continue
        b = spi_bus([(0x96, 0x2d)], mode=mode)
        e = edges(b)
        if name == 'T3b':
            # 明寫取樣後移位的序列，錯誤上升緣會讀到下一位。
            e['mosi'] = Edges(np.array([0., 3.75, 5.75, 6.75, 7.75, 9.75, 10.75])*1e-6,
                              np.array([1, 0, 1, 0, 1, 0, 1]), np.array([True]+[False]*6), [], 32, 0, False)
        r = module.run(e, t1=b['end'], mode=mode)
        assert values(r, 'mosi') == [0x96] and values(r, 'miso') == [0x2d], name
        invariants(r)
    if only:
        return
    b = spi_bus([(0x96, 0x2d)])
    r = module.run(edges(b), t1=b['end'], lsb=True)
    assert values(r, 'mosi') == [0x69] and values(r, 'miso') == [0xb4], 'T4'
    for width, words, name in [(16, [(0x1234, 0xabcd), (0x5678, 0xef01)], 'T5'),
                               (8, [(0x12, 0x34), (0x56, 0x78)], 'T12b'),
                               (12, [(0xabc, 0x123), (0xdef, 0x456)], 'T21')]:
        b = spi_bus(words, bits=width, cs=name != 'T12b')
        e = edges(b)
        if name == 'T12b':
            del e['cs']
        r = module.run(e, t1=b['end'], bits=width)
        assert values(r, 'mosi') == [x[0] for x in words], name
        invariants(r)
    b = spi_bus([(0x96, 0x2d)], cs_active='high')
    r = module.run(edges(b), t1=b['end'], cs_active='high')
    assert values(r, 'mosi') == [0x96]


def edge_cases() -> None:
    b = spi_bus([(0x96, 0x2d), (0x55, 0xaa)], gap=5e-6)
    e = edges(b)
    del e['cs']
    for name, idle, expected in [('T12', 2e-6, 2), ('T13b', 2e-6, 2)]:
        r = dec.run(e, t1=b['end'], idle=idle)
        assert len(r['frames']) == expected and all('incomplete' not in f['reasons'] for f in r['frames']), name
        invariants(r)
    # 第三個取樣之後插入閒置，驗殘餘位元和下一框重新對齊。
    b = spi_bus([(0x96, 0x2d), (0x55, 0xaa)])
    cut = 6.2e-6
    b['trans'] = [(t + (5e-6 if t > cut else 0), lane, v) for t, lane, v in b['trans']]
    b['end'] += 5e-6
    e = edges(b)
    del e['cs']
    r = dec.run(e, t1=b['end'], idle=2e-6)
    assert len(r['frames']) == 2 and 'incomplete' in r['frames'][0]['reasons'], 'T13a'
    for mode in (1,):
        b = spi_bus([(0x96, 0x2d)], mode=mode)
        e = edges(b)
        del e['cs']
        r = dec.run(e, t1=b['end'], mode=mode, idle=2e-6)
        assert values(r, 'mosi') == [0x96] and 'clk_phase' not in r['frames'][0]['reasons'], 'T14'
        e['sclk'] = e['sclk']._replace(value=1-e['sclk'].value)
        r = dec.run(e, t1=b['end'], mode=mode, idle=2e-6)
        assert 'clk_phase' in r['frames'][0]['reasons'], 'T14b'
    b = spi_bus([(0x96, 0x2d), (0x55, 0xaa)])
    e = edges(b)
    stop = float(e['sclk'].time[24])
    cs = e['cs']
    e['cs'] = cs._replace(time=np.array([cs.time[0], cs.time[1], stop]), value=np.array([1, 0, 1]), resync=np.array([True, False, False]))
    r = dec.run(e, t1=b['end'])
    assert [x['nbits'] for x in r['frames'][0]['fields'] if x['kind'] == 'mosi'] == [8, 4] and 'incomplete' in r['frames'][0]['reasons'], 'T7'
    e = edges(b)
    cs = e['cs']
    e['cs'] = cs._replace(time=np.array([0., cs.time[-1]]), value=np.array([0, 1]), resync=np.array([True, False]))
    r = dec.run(e, t1=b['end'])
    assert 'truncated' in r['frames'][0]['reasons'] and values(r, 'mosi')[0] == 0x96, 'T8'
    e = edges(b)
    e['miso'] = e['miso']._replace(value=e['miso'].value.copy())
    e['miso'].value[0] = -1
    r = dec.run(e, t1=b['end'])
    assert values(r, 'miso')[0] is None and 'unknown_bit' in r['frames'][0]['reasons'], 'T11a'
    e = edges(b)
    del e['miso']
    r = dec.run(e, t1=b['end'])
    assert values(r, 'mosi') == [0x96, 0x55] and not values(r, 'miso'), 'T17'
    e = edges(b)
    cut = float(e['sclk'].time[32]) + .1e-6
    r = dec.run(e, t1=cut)
    assert values(r, 'mosi') == [0x96, 0x55] and 'truncated' in r['frames'][0]['reasons'] and 'incomplete' not in r['frames'][0]['reasons'], 'T23'
    # 在兩個字組之間解除 CS。
    e = edges(b)
    cs = e['cs']
    e['cs'] = cs._replace(time=np.array([0., 2e-6, 10.5e-6, 11e-6, cs.time[-1]]),
                          value=np.array([1, 0, 1, 0, 1]), resync=np.array([True, False, False, False, False]))
    r = dec.run(e, t1=b['end'])
    assert len(r['frames']) == 2 and values(r, 'mosi') == [0x96, 0x55], 'T6'
    invariants(r)


def waveform_checks() -> None:
    b = spi_bus([(0x96, 0x2d), (0x55, 0xaa)])
    from scope_tool.web.synth import render
    t, *v = render(b['trans'], 32e6, lines=('sclk', 'mosi', 'miso', 'cs'), noise=.01, end=b['end'])
    names = ('sclk', 'mosi', 'miso', 'cs')
    volts = dict(zip(names, v))
    e, _, end, error = prepare(t, volts, dict.fromkeys(names), require_edges=False)
    assert not error
    r = dec.run(e, t1=end)
    assert values(r, 'mosi') == [0x96, 0x55]
    invariants(r)
    e, _, end, error = prepare(t, volts, dict.fromkeys(names), require_edges=False, max_edges=5)
    assert not error and end < t[-1]
    r = dec.run(e, t1=end)
    assert r['truncated'] and all(x <= end for x in r['bits_t'])
    fixed = {'sclk': v[0], 'mosi': np.zeros(len(t)), 'miso': np.ones(len(t)), 'cs': np.zeros(len(t))}
    manual = {k: (.3, .7) for k in fixed}
    e, _, end, error = prepare(t, fixed, manual, require_edges=False)
    assert not error and values(dec.run(e, t1=end), 'mosi') == [0, 0]
    _, _, _, error = prepare(t, fixed, dict.fromkeys(fixed), require_edges=False)
    assert error and '請改用手動門檻' in error
    r = dec.run(edges(b), t1=b['end'], max_fields=1)
    assert r['truncated']


def unknown_checks(module: types.ModuleType = dec) -> None:
    from scope_tool.web.synth import render
    b = spi_bus([(0x96, 0), (0xA5, 0)])
    names = ('sclk', 'mosi', 'miso', 'cs')
    t, *v = render(b['trans'], 32e6, lines=names, noise=.01, end=b['end'])
    for lane in ('sclk', 'cs'):
        volts = {k: x.copy() for k, x in zip(names, v)}
        volts[lane][(t >= 7e-6) & (t < 15e-6)] = np.nan
        e, _, end, error = prepare(t, volts, dict.fromkeys(names), require_edges=False)
        assert not error
        r = module.run(e, t1=end)
        invariants(r)
        if lane == 'sclk':
            fields = [x for f in r['frames'] for x in f['fields'] if x['kind'] == 'mosi']
            assert all(x['value'] != 0x95 and x['nbits'] != 8 for x in fields)
            assert [(x['value'], x['nbits']) for x in fields] == [(9, 4), (5, 4)]
            assert 'unknown_bit' in r['frames'][0]['reasons']
        else:
            assert len(r['frames']) == 2 and all('truncated' in f['reasons'] for f in r['frames'])
            assert not any(w.startswith('CS 外時脈') for w in r['warnings'])


def integration() -> None:
    from scope_tool.web.analysis_api import Analysis
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'spi.csv'
        f = fixture(path)
        api = Analysis()
        api.open_waveform(str(path))
        summary = api.decode('spi', f['channels'], dict.fromkeys(f['channels']), f['options'])
        assert summary['ok'], summary
        frames = api.decode_frames(summary['decode_id'])['frames']
        assert 1 < len(frames) < 2000 and {'txn'} <= {x['kind'] for x in frames}


def performance() -> None:
    t = np.arange(10_000_000, dtype=float) / 1e7
    v = np.tile(np.r_[np.zeros(5000), np.ones(5000)], 1000)
    waves = {k: v.copy() for k in ('sclk', 'mosi', 'miso', 'cs')}
    start = perf_counter()
    e, _, end, error = prepare(t, waves,
                                {k: (.3, .7) for k in ('sclk', 'mosi', 'miso', 'cs')}, require_edges=False)
    assert not error
    dec.run(e, t1=end)
    elapsed = perf_counter() - start
    print(f'10M 點×4：{elapsed:.3f} 秒')
    assert elapsed <= 15


def mutations() -> None:
    source = Path(dec.__file__).read_text(encoding='utf-8')
    for old, new in [('rising = (cpol == cpha)', 'rising = (cpha == 0)'),
                     ("j if o['lsb'] else len(v)-1-j", "len(v)-1-j if o['lsb'] else j"),
                     ("np.searchsorted(st,gaps)", "[]"),
                     ("range(lo, hi, o['bits'])", "range(lo, hi, max(1, hi-lo))")]:
        assert old in source
        mutant = types.ModuleType('mutant')
        exec(compile(source.replace(old, new), str(dec.__file__), 'exec'), mutant.__dict__)
        if old.startswith('rising'):
            for target in ('T2', 'T3b'):
                try:
                    vectors(mutant, target)
                except AssertionError:
                    continue
                raise AssertionError(f'變異未被偵測：{target}')
        elif old.startswith('np.searchsorted'):
            try: unknown_checks(mutant)
            except AssertionError: continue
            raise AssertionError('未知時脈變異未被偵測')
        else:
            b = spi_bus([(0x96, 0x2d), (0x55, 0xaa)], cs=False)
            e = edges(b)
            del e['cs']
            r = mutant.run(e, t1=b['end'], lsb=old.startswith('j if'))
            expected = [0x69, 0xaa] if old.startswith('j if') else [0x96, 0x55]
            assert values(r, 'mosi') != expected, 'T4 或 T12b 未偵測變異'



if __name__ == '__main__':
    handwritten()
    vectors()
    edge_cases()
    waveform_checks()
    unknown_checks()
    integration()
    performance()
    if '--mutations' in sys.argv:
        mutations()
    print('web.spi_check self-check OK')
