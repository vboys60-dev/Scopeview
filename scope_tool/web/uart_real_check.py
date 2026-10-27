from __future__ import annotations

"""X6000A UART 逐列驗收；核心 8O1 與儀器 8N1 列格式分開檢查。
首列欠缺 start，65 不能獨立重建；末列資料截斷，只驗 start 中心。
首段可能假同步，以首個 odd parity 正確且 stop 正確的候選恢復；
此邊界處理只用波形，不拿 CSV 字元決定候選。
"""
import csv
from decimal import Decimal
from pathlib import Path
import re
import numpy as np
from scope_tool.web.logic import to_edges
from scope_tool.web.uart_decode import run, _levels_at


def csv_time(value: str) -> tuple[float, float]:
    match = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)(ns|us|ms|s)', value.strip())
    assert match, value
    number, unit = match.groups()
    scale = {'ns': 1e-9, 'us': 1e-6, 'ms': 1e-3, 's': 1.}[unit]
    half = float(Decimal(10) ** Decimal(number).as_tuple().exponent) * scale / 2
    return float(number) * scale, half


def recover_prefix(e: tuple, end: float) -> tuple:
    """只處理第一個字元時間內的候選；無足夠證據時不修補。"""
    inv = e._replace(value=np.where(e.value < 0, -1, 1 - e.value))
    for j in range(1, len(e.time)):
        tm = e.time[j]
        if tm - e.time[0] > 11 / 19200:
            break
        if inv.value[j] != 0 or inv.value[j - 1] != 1:
            continue
        q = _levels_at(inv, tm + (np.arange(11) + .5) / 19200, end)
        if q[0] == 0 and q[10] == 1 and np.all(q >= 0) and int(q[1:10].sum()) % 2 == 1:
            # 從候選前一個 mark 起點保留真實邊沿，不捏造 idle。
            return e._replace(time=e.time[j - 1:], value=e.value[j - 1:], resync=e.resync[j - 1:])
    return e


def vendor_rows(result: dict) -> list[tuple]:
    """以實際第九位重現儀器的 8N1 stop 檢查；不改核心原因碼。"""
    rows = []
    for f in result['frames']:
        for x in f['fields']:
            lane, value = x['kind'], x['value']
            start_center = x['t0'] - 1 / 19200
            if value is None:
                rows.append((start_center, '', '', '', '尾端截斷'))
            elif x['ninth'] == 1:
                rows.append((start_center, f'{value:02X}' if lane == 'rx' else '',
                             f'{value:02X}' if lane == 'tx' else '', '', '字元'))
            else:
                rows.append((start_center, '', '', '', '錯誤前空白'))
                rows.append((start_center + 9 / 19200, '', '',
                             f'Unknown {lane.title()} Error', 'framing'))
    return sorted(rows)


def check(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[2] / 'X6000A-解碼' / 'RS-232'
    hp, cp = root / 'x6000rs234.h5', root / 'x6000rs235.csv'
    if not hp.exists() or not cp.exists():
        print('web.uart_real_check skip：實機資料檔不存在')
        return dict(skipped=True)
    # HDF5 僅驗收工具沿用既有可用讀取套件；核心、合成器與向量只用 numpy／標準庫。
    import h5py
    with h5py.File(hp, 'r') as h5:
        edges, axes, volts = {}, [], {}
        for lane, channel, threshold in (('tx', 1, 1.29), ('rx', 3, 1.00)):
            g = h5[f'Waveforms/Channel {channel}']
            v = np.asarray(g[f'Channel {channel} Data'])
            dt = float(g.attrs['XInc'])
            t = float(g.attrs['XOrg']) + np.arange(len(v)) * dt
            axes.append(t)
            volts[lane] = v
            edges[lane] = to_edges(t, v, threshold - .1, threshold + .1)
        assert np.array_equal(*axes), '兩通道時間軸不同'
    with cp.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    edges['rx'] = recover_prefix(edges['rx'], t[-1])
    r = run(edges, t1=t[-1], baud=19200, bits=8, parity='O', stop=1, invert=True)
    generated = vendor_rows(r)
    differences, strict, residuals = [], [], []
    # CSV 首列僅能驗相容性：第一點在既有 e 的資料後半，不能驗前方字元值。
    first = rows[0]
    assert first['Time'] == '?' and first['Rx'] == '65' and not first['Errors']
    assert generated[0][0] > t[0]
    # 完整資料中的第九位反例必須保留；不能直接把核心 parity 錯誤改成儀器錯誤。
    complete = [x for f in r['frames'] for x in f['fields'] if x['value'] is not None]
    rx_word = [0x4B, 0x65, 0x79, 0x73, 0x69, 0x67, 0x68, 0x74, 0x52, 0x52, 0x52]
    tx_word = [0x4D, 0x53, 0x4F, 0x73, 0x23, 0x31]
    for lane, expected in (('rx', rx_word[2:] + rx_word * 3 + rx_word[:9]),
                           ('tx', tx_word * 4 + tx_word[:4])):
        actual = [x['value'] for x in complete if x['kind'] == lane]
        assert actual == expected, (lane, actual, expected)
    for x in complete:
        e = edges[x['kind']]
        inv = e._replace(value=np.where(e.value < 0, -1, 1 - e.value))
        start = x['t0'] - 1.5 / 19200
        q = _levels_at(inv, start + (np.arange(11) + .5) / 19200, t[-1])
        assert q[0] == 0 and q[10] == 1
        assert q[1:9].tolist() == [(x['value'] >> k) & 1 for k in range(8)]
        assert q[9] == x['ninth']
    # 第一列只核對可見的後半位元，CSV 的 65 仍不能當成獨立還原成功。
    first_rx = next(x for x in complete if x['kind'] == 'rx')
    partial_start = first_rx['t0'] - 12.5 / 19200
    centers = partial_start + (np.arange(11) + .5) / 19200
    observed = centers >= t[0]
    q = np.where(volts['rx'][np.searchsorted(t, centers[observed]) - 1] < 1., 1, 0)
    symbol = np.array([0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1])
    assert np.array_equal(q, symbol[observed]), (q, symbol[observed])
    partials = [x for f in r['frames'] for x in f['fields'] if x['value'] is None]
    assert len(partials) == 1 and partials[0]['kind'] == 'rx'
    parity_frames = [f for f in r['frames'] if 'parity' in f['reasons']]
    assert len(parity_frames) == 1
    bad = [x for f in parity_frames for x in f['fields'] if not x['ok']]
    assert len(bad) == 1 and bad[0]['value'] == 0x31 and bad[0]['ninth'] == 1
    if len(generated) != len(rows) - 1:
        differences.append(f'可驗時間列數 {len(generated)} != {len(rows) - 1}')
    for i, (row, got) in enumerate(zip(rows[1:], generated), 2):
        tm, half = csv_time(row['Time'])
        want = (row['Rx'], row['Tx'], row['Errors'])
        if got[1:4] != want:
            differences.append(f'第 {i} 列值：{got[1:4]} != {want}')
        delta = abs(got[0] - tm)
        residuals.append((got[0] - tm) * 1e6)
        tolerance = max(2 * dt, half + dt)
        if delta > tolerance:
            differences.append(f'第 {i} 列時間：差 {(got[0] - tm) * 1e6:.6f} us > {tolerance * 1e6:.6f} us')
        if delta > max(2 * dt, half):
            strict.append(f'第 {i} 列：差 {(got[0] - tm) * 1e6:.6f} us，嚴格容差 {max(2 * dt, half) * 1e6:.6f} us')
    print(f'實機比對：CSV {len(rows)} 列；產生 {len(generated)} 列＋首列邊界例外 1 列')
    print('首列 ?/65：欠缺 start 與資料前半，無法獨立驗值；末列：只驗截斷 start 中心')
    print(f'完整字元 {sum(x[4] in ("字元", "錯誤前空白") for x in generated)}；錯誤列 {sum(x[4] == "framing" for x in generated)}；尾端截斷 {len(partials)}')
    print(f'時間殘差範圍 {min(residuals):.6f}～{max(residuals):.6f} us')
    print(f'原嚴格時間容差超出清單：{strict}')
    print(f'差異清單：{differences if differences else "無；所有可驗列相符"}')
    print(f'時間容差 max(2×XInc={2 * dt:.12g} s, 文字捨入半量＋XInc)；只用已證實的 .5T／9.5T 時間語意')
    assert not differences, '\n'.join(differences)
    return dict(rows=len(rows), generated=len(generated), differences=differences,
                strict_times=strict, skipped=False, unverifiable=['第 1 列 ?/65'])


if __name__ == '__main__':
    check()
    print('web.uart_real_check self-check OK')
