from __future__ import annotations

"""eSPI 真值、邊界、整合及變異檢查。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import sys
import types
import numpy as np
from scope_tool.web import espi_decode as dec
from scope_tool.web.espi_table import crc8, command
from scope_tool.web.espi_synth import bus, edges, fixture
from scope_tool.web.logic import prepare


def check(module: types.ModuleType = dec) -> None:
    cases = [([0x25], [8,15,3], 0), ([0x21,0,4], [8,1,2,3,4,15,3], 0),
             ([0x22,0,4,1,2,3,4], [8,15,3], 0), ([4,0,2,0x55], [8,15,3], 0),
             ([4,3,1,2,3,4,5,6,7,8], [8,15,3], 0), ([0x25], [8,15,3], 2),
             ([0x25], [1,15,3], 0), ([0x25], [0xff], 0)]
    for cmd, response, waits in cases:
        b = bus(cmd, response, waits)
        r = module.run(edges(b), t1=b['end'])
        f = r['frames'][0]
        assert f['fields'][0]['value'] == cmd[0]
        assert len([x for x in f['fields'] if x['kind'] == 'wait']) == waits
        assert ('defer' in f['reasons']) == (response[0] == 1)
        assert ('no_response' in f['reasons']) == (response[0] == 0xff)
        assert not set(f['reasons']) & {'crc_cmd', 'crc_resp', 'incomplete'}
        if response[0] != 0xff:
            assert [x['value'] for x in f['fields'] if x['kind'] == 'status'] == [15,3]
        assert np.all(np.diff(r['bits_t']) > 0)
        assert all(f['t0'] <= x['t0'] <= x['t1'] <= f['t1'] for x in f['fields'])
    b = bus([0x25], [8,15,3])
    combined = dict(b, trans=b['trans'] + [(t+b['end']+3e-6, k, v) for t,k,v in b['trans']], end=2*b['end']+3e-6)
    e = edges(combined)
    e['cs'] = e['cs']._replace(value=e['cs'].value.copy())
    e['cs'].value[0] = 0
    r = module.run(e, t1=combined['end'])
    assert 'truncated' in r['frames'][0]['reasons'] and r['truncated']
    f = r['frames'][1]
    assert 'incomplete' not in f['reasons']
    assert [x['value'] for x in f['fields'] if x['kind'] == 'status'] == [15,3]
    assert any(x['kind'] == 'crc' for x in f['fields'])
    for lane, expected, cutoff in [('io0', 'crc_cmd', 11e-6), ('io1', 'crc_resp', 50e-6)]:
        b = bus([0x25], [8,15,3])
        e = edges(b)
        v = e[lane].value.copy()
        ix = int(np.searchsorted(e[lane].time, cutoff))
        if ix >= len(v):
            ix = len(v)-1
        v[ix:] = 1-v[ix:]
        e[lane] = e[lane]._replace(value=v)
        assert expected in module.run(e, t1=b['end'])['frames'][0]['reasons']
    b = bus([0xff,0xff], [], reset=True)
    assert module.run(edges(b), t1=b['end'])['frames'][0]['kind'] == 'reset'
    b = bus([0x30], [8,15,3])
    assert 'unknown_opcode' in module.run(edges(b), t1=b['end'])['frames'][0]['reasons']
    b = bus([0x25], [8,15,3])
    assert module.run(edges(b), t1=b['end'], max_fields=1)['truncated']
    assert module.run(edges(b), t1=12e-6)['truncated']


def integration() -> None:
    from scope_tool.web.analysis_api import Analysis
    with TemporaryDirectory() as d:
        p = Path(d) / 'espi.csv'
        f = fixture(p)
        api = Analysis()
        api.open_waveform(str(p))
        summary = api.decode('espi', f['channels'], dict.fromkeys(f['channels']), f['options'])
        assert summary['ok'], summary
        frames = api.decode_frames(summary['decode_id'])['frames']
        assert 1 < len(frames) < 2000 and {'cmd'} <= {x['kind'] for x in frames}


def performance() -> None:
    t = np.arange(10_000_000, dtype=float) / 1e7
    v = np.tile(np.r_[np.zeros(5000), np.ones(5000)], 1000)
    waves = {k:v for k in ('cs','clk','io0','io1')}
    start = perf_counter()
    e, _, end, error = prepare(t, waves, {k:(.3,.7) for k in waves}, require_edges=False)
    assert not error
    dec.run(e, t1=end)
    elapsed = perf_counter()-start
    print(f'10M 點×4：{elapsed:.3f} 秒')
    assert elapsed <= 15


def mutations() -> None:
    source = Path(dec.__file__).read_text(encoding='utf-8')
    for old, new in [("not halt", "not truncated"), ("pos += 2", "pos += 1"), ("clk.value == 1", "clk.value == 0"),
                     ("response[-3] | response[-2] << 8", "response[-2] | response[-3] << 8"),
                     ("crc8(response[:-1])", "crc8([15, 15] + response[:-1])")]:
        assert old in source
        mutant = types.ModuleType('mutant')
        exec(compile(source.replace(old, new), str(dec.__file__), 'exec'), mutant.__dict__)
        try:
            if old == 'clk.value == 1':
                b = bus([0x25], [8,15,3])
                e = edges(b)
                for lane in ('io0', 'io1'):
                    times = e[lane].time.copy()
                    times[1:] -= .3e-6
                    e[lane] = e[lane]._replace(time=times)
                assert mutant.run(e, t1=b['end'])['frames'][0]['fields'][0]['value'] == 0x25
            elif old.startswith('response[-3]'):
                b = bus([0x25], [8,0,0x40])
                assert 'reserved_bit' in mutant.run(edges(b), t1=b['end'])['frames'][0]['reasons']
            else:
                check(mutant)
        except AssertionError:
            continue
        raise AssertionError(f'變異未被偵測：{old}')
    assert crc8(b'123456789') == 0xf4
    def wrong_crc(data: bytes) -> int:
        c = 0xff
        for b in data:
            c ^= b
            for _ in range(8):
                c = ((c << 1) ^ (7 if c & 128 else 0)) & 255
        return c
    assert wrong_crc(b'123456789') != 0xf4


if __name__ == '__main__':
    assert [crc8(x) for x in (b'123456789', bytes.fromhex('25'), bytes.fromhex('21 00 04'), bytes.fromhex('08 0F 03'))] == [0xf4,0xfb,0x34,0x9b]
    assert command([0x42])[0] == '' and command([0x40])[1] == 4
    check()
    integration()
    performance()
    if '--mutations' in sys.argv:
        mutations()
    print('web.espi_check self-check OK')
