from __future__ import annotations

"""I2C 協定、品質、上限與效能自檢；變異模組先成功載入才驗證能被測試抓到。"""
from pathlib import Path
import platform
import sys
from time import perf_counter
import types
import numpy as np
from scope_tool.web import i2c_decode as dec
from scope_tool.web.i2c_synth import Bus, self_check
from scope_tool.web.i2c_vectors import vectors, expected
from scope_tool.web.i3c_synth import render
from scope_tool.web.logic import to_edges


def invariants(r: dict) -> None:
    assert r['ok'], r
    assert r['addresses'] == []
    assert np.all(np.diff(r['bits_t']) > 0)
    assert len(r['bits_t']) == len(r['bits_v'])
    assert np.all(r['bits_t'] <= r['t1'])
    last = -np.inf
    for i, f in enumerate(r['frames']):
        assert f['i'] == i and last <= f['t0'] <= f['t1'] <= r['t1'], f
        last = f['t1']
        for x in f['fields']:
            assert f['t0'] <= x['t0'] <= x['t1'] <= f['t1'], (f, x)


def check_frames(r: dict, wants: list[dict], name: str) -> None:
    invariants(r)
    assert len(r['frames']) == len(wants), (name, r['frames'], wants)
    for f, want in zip(r['frames'], wants):
        for key in ('kind', 'addr', 'rw', 'ack', 'start', 'status', 'reasons'):
            assert f[key] == want[key], (name, key, f, want)
        actual = [(x['kind'], x['value'], x['nbits'], x['ninth'], x['ninth_kind'], x['ok']) for x in f['fields']]
        assert actual == want['fields'], (name, actual, want['fields'])
        for i, label in want['labels'].items():
            assert label in f['fields'][i]['label'], (name, f)


def run_bus(b: Bus, **kw: object) -> dict:
    waves = b.render()
    r = dec.decode_waveforms(*waves, **kw)
    invariants(r)
    return r


def protocol_vectors() -> None:
    for name, bus, wants in vectors():
        r = run_bus(bus)
        check_frames(r, wants, name)
        controls = [x for x in bus.truth if x[0] != 'byte']
        # 每筆完整交易的控制條件定位誤差須在兩個取樣週期內。
        for f, ctl in zip([f for f in r['frames'] if f['start']], [x for x in controls if x[0] != 'P']):
            delay = 300e-9 / 2.2 * np.log(2.5)
            assert abs(f['t0'] - ctl[1] - delay) <= 2 / 20e6, (name, f, ctl)
        for f in r['frames']:
            for item in f['fields']:
                if item['nbits'] != 9:
                    continue
                truth = min((x for x in bus.truth if x[0] == 'byte'), key=lambda x: abs(x[1] - item['t0']))
                assert abs(item['t0'] - truth[1] - delay) <= 2 / 20e6
                assert abs(item['t1'] - truth[1] - 8 * bus.period - delay) <= 2 / 20e6
    # 10-bit 脈絡被不同目標、錯誤 ACK、不同高位或 NaN 打斷。
    for mode in ('other', 'A1', 'A2', 'high'):
        b = Bus().start().byte(0xF4, mode != 'A1')
        if mode != 'A1':
            b.byte(0xA5, mode != 'A2')
        if mode == 'other':
            b.rstart().byte(0xA0)
        b.rstart().byte(0xF3 if mode == 'high' else 0xF5).stop()
        f = run_bus(b)['frames'][-1]
        assert f['addr'] is None and 'addr10_unresolved' in f['reasons'], (mode, f)
    for value, label in ((6, '重設'), (4, '不重設'), (0xA1, '50'), (0x12, '12')):
        assert label in run_bus(Bus().start().byte(0).byte(value).stop())['frames'][0]['fields'][1]['label']
    print(f'協定向量 {len(vectors())} 組與 10-bit 脈絡：OK')


def handwritten() -> None:
    # H1 與 H2 直接列出線上位元串，不呼叫 Bus 或以 byte 轉成位元。
    def waves(commands: list[str]) -> tuple:
        tm, c, d = 10e-6, 1, 1
        trans = [(0., 'scl', 1), (0., 'sda', 1)]
        def put(line: str, v: int) -> None:
            nonlocal c, d
            if (c if line == 'scl' else d) != v:
                trans.append((tm, line, v))
            if line == 'scl':
                c = v
            else:
                d = v
        for command in commands:
            if command == 'S':
                put('sda', 0); tm += 5e-6; put('scl', 0)
            elif command in ('Sr', 'P'):
                tm += 2.5e-6; put('sda', int(command == 'Sr'))
                tm += 2.5e-6; put('scl', 1)
                tm += 5e-6; put('sda', int(command == 'P'))
                tm += 5e-6
                if command == 'Sr':
                    put('scl', 0)
            else:
                for bit in command:
                    tm += 2.5e-6; put('sda', int(bit))
                    tm += 2.5e-6; put('scl', 1)
                    tm += 5e-6; put('scl', 0)
        return render(trans, 20e6, tr=0, noise=0, end=tm + 10e-6)
    h1 = dec.decode_waveforms(*waves(['S', '101000000', '000100100', '001101000', 'P']))
    check_frames(h1, [expected('write', 0x50, 0, [0xA0, 0x12, 0x34])], 'H1')
    assert np.allclose(h1['bits_t'], 20e-6 + np.arange(27) * 10e-6, atol=2 / 20e6, rtol=0)
    h2 = dec.decode_waveforms(*waves(['S', '111101000', '101001010', 'Sr', '111101010', '001101001', 'P']))
    check_frames(h2, [expected('write', 0x2A5, 0, [0xF4, 0xA5], low=True),
                      expected('read', 0x2A5, 1, [0xF5, 0x34], acks=(True, False), start='Sr')], 'H2')
    print('手寫真值 H1/H2：OK')


def quality() -> None:
    for count in (1, 4, 8):
        for ending in ('P', 'Sr', 'EOF'):
            b = Bus().start().word(0xA5 >> (8 - count), count)
            if ending == 'P':
                b.stop()
            elif ending == 'Sr':
                b.rstart().byte(0xA0).stop()
            f = run_bus(b)['frames'][0]
            assert f['reasons'] == ['truncated' if ending == 'EOF' else 'byte_cut'], f
            assert f['fields'][0]['nbits'] == count and f['fields'][0]['ninth'] is None
    b = Bus().start().byte(0xA0).byte(0x12).byte(0x34).stop()
    for seed in range(20):
        r = dec.decode_waveforms(*b.render(noise=.05, seed=seed))
        check_frames(r, [expected('write', 0x50, 0, [0xA0, 0x12, 0x34])], f'雜訊{seed}')
    b = Bus().start().byte(0xA0).byte(0x12).stop().start().byte(0xA1).byte(0x34, False).stop()
    t, c, d = b.render(nan=((100e-6, 120e-6),))
    r = dec.decode_waveforms(t, c, d)
    invariants(r)
    assert 'truncated' in r['frames'][0]['reasons'] and r['frames'][-1]['addr'] == 0x50
    # 同一 SCL 低期間反覆 SDA 下降兩次，並驗證下一筆可以恢復。
    b = Bus().start().byte(0xA0)
    begin = b.now
    b.raw([(begin + (i + 1) * 1e-6, 'sda', v) for i, v in enumerate((1, 0, 1, 0))])
    b.idle(1e-6).set('scl', 1)
    b.idle(10e-6).set('sda', 1)
    b.idle(10e-6).bit(1).rstart().byte(0xA0).stop()
    r = run_bus(b)
    assert 'sda_glitch' in r['frames'][0]['reasons'] and 'truncated' in r['frames'][0]['reasons']
    assert r['frames'][-1]['addr'] == 0x50
    r = dec.decode_waveforms(*Bus().start().byte(0xA0).stop().render(fs=500_000, tr=0))
    assert r['ok'] and any('取樣不足' in w for w in r['warnings'])
    # 邊沿上限直接傳給純函式入口，並檢查共同截止點與所有欄位。
    b = Bus().start().byte(0xA0).byte(1).stop().start().byte(0xA1).byte(2, False).stop()
    waves = b.render()
    for kw in ({'max_frames': 1}, {'max_fields': 1}, {'max_edges': 12}):
        r = dec.decode_waveforms(*waves, **kw)
        invariants(r)
        assert r['truncated'] and r['warnings'], (kw, r)
        if 'max_frames' in kw:
            assert len(r['frames']) <= 1
        if 'max_fields' in kw:
            assert sum(len(f['fields']) for f in r['frames']) <= 1
        if 'max_edges' in kw:
            cuts = [to_edges(waves[0], v, *r['thresholds'][key], max_edges=12) for key, v in zip(('scl', 'sda'), waves[1:])]
            assert r['t1'] == min(e.time[-1] for e in cuts if e.truncated)
        assert any(f"{r['t1']:.12g}" in w for w in r['warnings'])
    assert dec.options({}, {}) == dec.options({'addr_bits': 7}, {}) == dec.options({'addr_bits': 8}, {}) == {}
    for invalid in ({'x': 1}, None, [], *({'addr_bits': v} for v in (None, True, False, 7.0, '8', 0, 9, [], {}))):
        try:
            dec.options(invalid, {})
        except ValueError:
            pass
        else:
            raise AssertionError('非法參數應拒絕')
    assert not dec.decode_waveforms(np.arange(10.), np.ones(10), np.ones(10))['ok']
    for kwargs in ({'max_frames': 0}, {'max_fields': 0}, {'max_edges': 0}):
        try:
            dec.decode_waveforms(*waves, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError('非法上限應拒絕')
    print('缺第九位／20 seed／NaN／取樣不足／glitch／上限：OK')


def display_snapshot() -> None:
    from tempfile import TemporaryDirectory
    import csv
    from scope_tool.web.analysis_api import Analysis
    from scope_tool.web.i2c_synth import fixture
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'i2c_20261027_120000.csv'
        config = fixture(path)
        api = Analysis()
        api.open_waveform(str(path))
        baseline = None
        for bits in (7, 8):
            opt = {'addr_bits': bits}
            summary = api.decode('i2c', config['channels'], {'scl': None, 'sda': None}, opt)
            opt['addr_bits'] = 8 if bits == 7 else 7
            assert api._dec['meta']['options'] == {'addr_bits': bits}
            frames = api.decode_frames(summary['decode_id'])['frames']
            if baseline is None:
                baseline = frames
            assert frames == baseline
            out = Path(directory) / str(bits)
            out.mkdir()
            rows = list(csv.reader(Path(api.export_decode(summary['decode_id'], str(out))['path']).open(encoding='utf-8-sig')))
            data = rows[7:]
            assert data[0][4] == str(0xA0 if bits == 8 else 0x50)
            for f in frames:
                addr = dec.display_addr(f, {'addr_bits': bits})
                assert all(row[4] == str(addr) if addr is not None else row[4] == '' for row in data if row[0] == str(f['i']))
                if bits == 8 and f['kind'] == 'read' and f['addr'] == 0x50:
                    assert addr == 0xA1
                if f['kind'] not in ('write', 'read') or f['addr'] is None or f['addr'] > 0x7F:
                    assert addr == f['addr']
    print('選項快照／frames 不變／CSV 位址：OK')


def performance() -> None:
    b = Bus().start().byte(0xA0).byte(0x12).byte(0x34).stop()
    t, c, d = b.render()
    # 長 idle 配合實際交易，測量完整 10M 點×兩通道的門檻、邊沿與解碼。
    n = 10_000_000
    tt = np.arange(n, dtype=float) / 20e6
    cc, dd = np.full(n, 1.8), np.full(n, 1.8)
    cc[:len(c)], dd[:len(d)] = c, d
    begin = perf_counter()
    r = dec.decode_waveforms(tt, cc, dd)
    elapsed = perf_counter() - begin
    check_frames(r, [expected('write', 0x50, 0, [0xA0, 0x12, 0x34])], '效能')
    print(f'效能 10M×2：{elapsed:.3f} s；{platform.platform()} {platform.machine()}')
    assert elapsed <= 15, elapsed


def mutations() -> None:
    global dec
    original = dec
    source = Path(dec.__file__).read_text()
    changes = [('ACK 反相', "item['ninth'] == 0", "item['ninth'] == 1"),
               ('拿掉 pending', 'self.pending = (tm, event[2])', 'self.bit(tm, event[2])'),
               ('10-bit 讀誤判', "f['addr'] = old\n", "f['addr'] = old\n                    self.stage = 'addr_lo'\n")]
    for name, before, after in changes:
        assert before in source, name
        module = types.ModuleType('scope_tool.web._i2c_mutation')
        exec(compile(source.replace(before, after), '<I2C 變異>', 'exec'), module.__dict__)
        dec = module
        try:
            protocol_vectors()
            handwritten()
        except AssertionError:
            print(f'變異已抓到：{name}')
        else:
            raise AssertionError(f'變異漏網：{name}')
        finally:
            dec = original


if __name__ == '__main__':
    self_check()
    handwritten()
    protocol_vectors()
    quality()
    display_snapshot()
    performance()
    if '--mutations' in sys.argv:
        mutations()
    print('web.i2c_check self-check OK')
