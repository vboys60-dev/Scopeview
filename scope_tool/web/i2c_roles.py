"""I2C 兩種角色配置的保守估計；僅回建議，不建立解碼快照。"""
from __future__ import annotations
import numpy as np
from scope_tool.web.logic import prepare


def estimate_waveforms(time: np.ndarray, volts: dict, thresholds: dict) -> tuple[dict, str]:
    """門檻各算一次；封包數至少兩倍且有效邊沿數一致才給建議。"""
    from scope_tool.web.i2c_decode import run
    if set(volts) != {'scl', 'sda'}:
        return dict(thresholds), '無法判斷 SCL／SDA（請選齊 SCL 與 SDA）'
    edges, used, end, error = prepare(time, volts, thresholds, require_edges=True)
    if error:
        return used, f'無法判斷 SCL／SDA（{error}）'
    counts = []
    for candidate in (edges, {'scl': edges['sda'], 'sda': edges['scl']}):
        result = run(candidate, t1=end, max_frames=2000)
        counts.append(sum(f['kind'] in ('write', 'read') and f['addr'] is not None
                          for f in result['frames']))
    cur, swp = counts
    n = {r: int(np.count_nonzero((e.value >= 0) & ~e.resync)) for r, e in edges.items()}
    if swp >= max(1, 2 * cur) and n['sda'] > n['scl']:
        return used, f'角色建議：對調（有位址封包 {swp} 對 {cur}）'
    if cur >= max(1, 2 * swp) and n['scl'] > n['sda']:
        return used, f'角色建議：維持（有位址封包 {cur} 對 {swp}）'
    return used, f'無法判斷 SCL／SDA（有位址封包 {cur} 對 {swp}，邊沿 {n["scl"]} 對 {n["sda"]}）'


def self_check() -> None:
    from time import perf_counter
    from unittest.mock import patch
    from scope_tool.web.i2c_synth import Bus
    from scope_tool.web import i2c_decode as dec
    from scope_tool.web.analysis_api import Analysis
    from scope_tool.contracts import Waveform
    for frequency in (100_000, 400_000):
        bus = Bus(frequency)
        for _ in range(5):
            bus.start().byte(0xA0).byte(0x55).stop()
        time, scl, sda = bus.render()
        for a, b, expected in ((scl, sda, '維持'), (sda, scl, '對調')):
            _, message = estimate_waveforms(time, {'scl': a, 'sda': b}, {'scl': None, 'sda': None})
            assert message == f'角色建議：{expected}（有位址封包 5 對 0）', message
        # 不同電壓平台，手動門檻必須與實際通道一起交換。
        volts, th = {'scl': scl + 5, 'sda': sda}, {'scl': (5.7, 6.1), 'sda': (.7, 1.1)}
        auto = estimate_waveforms(time, volts, dict.fromkeys(volts))[1]
        assert estimate_waveforms(time, volts, th)[1] == auto
        swapped, swapped_th = {'scl': sda, 'sda': scl + 5}, {'scl': th['sda'], 'sda': th['scl']}
        assert '對調' in estimate_waveforms(time, swapped, swapped_th)[1]
    time, scl, sda = Bus().start().byte(0xFF, False).stop().render()
    for a, b, expected in ((scl, sda, '維持'), (sda, scl, '對調')):
        assert expected in estimate_waveforms(time, {'scl': a, 'sda': b}, {'scl': None, 'sda': None})[1]
    assert 'SDA 無有限高低平台' in estimate_waveforms(time, {'scl': scl, 'sda': np.ones_like(sda)}, {'scl': None, 'sda': None})[1]
    bus = Bus().word(0xAA55, 16)
    t, c, d = bus.render()
    assert estimate_waveforms(t, {'scl': c, 'sda': d}, {'scl': None, 'sda': None})[1].startswith('無法判斷')
    api = Analysis()
    api._gen, api._waves = 1, [Waveform('SCL', time, scl), Waveform('SDA', time, sda)]
    ch, th = {'scl': 'SCL', 'sda': 'SDA'}, {'scl': None, 'sda': None}
    summary = api.decode('i2c', ch, th, {})
    before, snapshot = api.decode_frames(summary['decode_id']), api._dec
    estimated = api.decode('i2c', ch, th, {'estimate': True})
    assert estimated['ok'] is False and estimated['reason'].startswith('角色建議')
    assert estimated['decode_id'] is None and all(v == 0 for v in estimated['counts'].values())
    assert api._dec is snapshot and api.decode_frames(summary['decode_id']) == before
    # 3000 個 byte；包裝真 run 驗證兩向都套用上限，反向會截斷。
    bus = Bus()
    for _ in range(3000):
        bus.start().byte(0xA0).stop()
    t, c, d = bus.render(fs=2e6)
    with patch.object(dec, 'run', wraps=dec.run) as run:
        start = perf_counter()
        assert '維持' in estimate_waveforms(t, {'scl': c, 'sda': d}, th)[1]
        elapsed = perf_counter() - start
        assert run.call_count == 2 and all(call.kwargs['max_frames'] == 2000 for call in run.call_args_list)
        assert elapsed < 1, elapsed
    print(f'I2C 角色估計合成／門檻／快照／上限：OK（3000 byte {elapsed:.3f} s）')


if __name__ == '__main__':
    self_check()
    print('web.i2c_roles self-check OK')
