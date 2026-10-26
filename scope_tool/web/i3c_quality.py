from __future__ import annotations

"""取樣、截斷、效能與記憶體向量 28–40。"""
import json
import platform
import resource
import subprocess
import sys
from time import perf_counter
import numpy as np
from scope_tool.web import logic
from scope_tool.web.i3c_decode import decode_waveforms
from scope_tool.web.i3c_synth import Bus, render
from scope_tool.web.i3c_vectors import check_result, private, run


def fingerprint(r: dict) -> list:
    return [(f['kind'], f['start'], f['addr'], f['rw'], f['ack'], f['ccc'], f['ccc_name'],
             f['status'], f['reasons'], [(x['kind'], x['value'], x['nbits'], x['ninth'], x['ok']) for x in f['fields']])
            for f in r['frames']]


def performance_wave() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    b = Bus().start().header(0x7E, od=True).rstart().header(8)
    for i in range(20_000):
        b.byte_w(i & 255)
    b.stop()
    waves = render(b.trans, 500e6, noise=0, end=(10_000_000 - 1) / 500e6)
    assert len(waves[0]) == 10_000_000
    return waves


def memory_worker(repeats: int) -> None:
    waves = performance_wave()
    for _ in range(repeats):
        result = decode_waveforms(*waves)
        assert result['ok'] and len(result['frames'][0]['fields']) == 20_002
        del result
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(f'{rss / (1024 ** 2 if sys.platform == "darwin" else 1024):.1f}')


def quality_vectors(heavy: bool = True) -> list[str]:
    passed = []
    b = private(tuple(range(24)))
    b.start().header(8).byte_w(0xA5).stop()
    waves = b.render(noise=0)
    cut = int(len(waves[0]) * .37)
    r = check_result(decode_waveforms(*(v[cut:] for v in waves)))
    assert r['frames'][0]['kind'] == 'partial' and r['frames'][-1]['kind'] == 'private_write'
    assert all(a['how'] == 'observed' and a['pid'] is None and a['t_from'] is None for a in r['addresses'])
    passed.append('28')
    b = private()
    clean = fingerprint(decode_waveforms(*b.render(noise=0, tr=3e-9)))
    for seed in range(20):
        assert fingerprint(decode_waveforms(*b.render(noise=.05, tr=3e-9, seed=seed))) == clean
    passed.append('29')
    r = decode_waveforms(*b.render(fs=40e6, noise=0))
    assert r['ok'] and any('取樣不足' in s for s in r['warnings'])
    passed.append('30')
    t, c, d = b.render(noise=0)
    r = decode_waveforms(t, c, d, thresholds={'sda': (2., 3.)})
    assert not r['ok'] and 'SDA' in r['reason']
    for v in (np.ones_like(d), np.full_like(d, np.nan), np.full_like(d, np.inf)):
        r = decode_waveforms(t, c, v)
        assert not r['ok'] and 'SDA' in r['reason']
    passed.append('31')
    b = private(tuple(range(24)))
    b.start().header(8).byte_w(0x55).stop()
    for missing in (np.nan, np.inf):
        t, c, d = b.render(noise=0)
        a = len(t) // 3
        c[a:a + 1000] = missing
        d[a:a + 1000] = missing
        r = check_result(decode_waveforms(t, c, d))
        assert 'truncated' in r['frames'][0]['reasons']
        assert r['frames'][-1]['kind'] == 'private_write' and r['frames'][-1]['fields'][-1]['value'] == 0x55
        assert len([f for f in r['frames'] if f['kind'] == 'private_write']) == 2
    passed.append('32')
    n = logic.CHUNK + 50
    t = np.arange(n, dtype=float)
    v = np.zeros(n)
    v[logic.CHUNK - 1:logic.CHUNK + 1] = 1
    v[logic.CHUNK + 3:logic.CHUNK + 5] = np.nan
    a, b = logic.to_edges(t, v, .4, .6), logic.to_edges(t, v, .4, .6, chunk=n)
    for key in ('time', 'value', 'resync'):
        assert np.array_equal(getattr(a, key), getattr(b, key))
    assert a.unknown == b.unknown and a.min_run == b.min_run
    del t, v, a, b
    passed.append('33')
    t = np.arange(30, dtype=float)
    c = np.tile([1., 1., 0., 0., 1., 0.], 5)
    d = c.copy()
    r = decode_waveforms(t, c, d)
    assert r['ok'] and any('ambiguous_edge' in s for s in r['warnings'])
    passed.append('34')
    for other in (np.r_[t[:15], t[15] + .1, t[16:]], t[::-1]):
        try:
            logic.validate_time(t, other)
        except ValueError:
            pass
        else:
            raise AssertionError('時間軸差異未拒絕')
    for bad in (t[::-1], np.r_[t[:-1], np.nan]):
        try:
            logic.validate_time(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('時間軸未驗證')
    passed.append('35')
    b = Bus().idle(.001).start().header(8).byte_w(0xA5).stop()
    r = run(b)
    assert r['frames'][0]['fields'][-1]['value'] == 0xA5
    assert all(0 < lo < hi < 1.8 for lo, hi in r['thresholds'].values())
    alias = np.tile([0., 1.8], logic.LEVEL_SAMPLES // 2 + 100)
    lo, hi = logic.auto_threshold(alias)
    assert 0 < lo < hi < 1.8
    del alias
    passed.append('36')
    b = Bus()
    for _ in range(510):
        b.start().header(8).byte_w(0xA5).stop()
    for option, limit in [('max_frames', 500), ('max_fields', 500)]:
        r = run(b, **{option: limit})
        assert r['truncated'] and any('只解到 t=' in s for s in r['warnings'])
        assert (len(r['frames']) if option == 'max_frames' else sum(len(f['fields']) for f in r['frames'])) <= limit
    for limit in range(1, 9):
        r = run(Bus().entdaa([(1, 6, 4)]), max_fields=limit)
        assert sum(len(f['fields']) for f in r['frames']) <= limit
    r = run(Bus().start().header(8).byte_w(1).target_reset(), max_frames=1)
    assert r['truncated'] and len(r['frames']) == 1
    passed.append('37')
    t = np.arange(5000, dtype=float)
    c, d = (np.arange(5000) // 5 % 2).astype(float), (np.arange(5000) // 2 % 2).astype(float)
    r = decode_waveforms(t, c, d, max_edges=1000)
    assert r['ok'] and r['truncated']
    edges = [logic.to_edges(t, v, .4, .6, max_edges=1000) for v in (c, d)]
    cutoff = min(e.time[-1] for e in edges if e.truncated)
    assert r['t1'] == cutoff and (not len(r['bits_t']) or r['bits_t'][-1] <= cutoff)
    passed.append('39')
    if not heavy:
        return passed
    b = Bus().start().header(8)
    for i in range(100_000):
        b.byte_w(i & 255)
    b.stop()
    r = decode_waveforms(*b.render(fs=125e6, noise=0))
    assert r['truncated'] and sum(len(f['fields']) for f in r['frames']) == 100_000
    size = len(json.dumps(r['frames'], ensure_ascii=False).encode('utf-8'))
    print(f'100k fields JSON: {size:,} bytes')
    del b, r
    waves = performance_wave()
    started = perf_counter()
    r = check_result(decode_waveforms(*waves))
    elapsed = perf_counter() - started
    assert len(r['frames'][0]['fields']) == 20_002 and elapsed <= 15, elapsed
    chip = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], capture_output=True, text=True).stdout.strip() if sys.platform == 'darwin' else platform.processor()
    print(f'10M×2 / 20,000 bytes: {elapsed:.3f} s; {platform.platform()}; {chip or platform.machine()}')
    passed.append('38')
    del waves, r
    for repeats in (1, 5):
        proc = subprocess.run([sys.executable, '-B', '-m', 'scope_tool.web.i3c_quality', '--memory', str(repeats)],
                              capture_output=True, text=True, check=True)
        print(f'峰值 RSS（獨立子程序，{repeats} 次解碼）: {proc.stdout.strip()} MiB')
    passed.append('40')
    return passed


if __name__ == '__main__':
    if '--memory' in sys.argv:
        memory_worker(int(sys.argv[-1]))
    else:
        print('向量', ','.join(quality_vectors()))
        print('web.i3c_quality self-check OK')
