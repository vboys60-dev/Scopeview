from __future__ import annotations

"""X6000A 實機逐列驗收。
CSV 的 Missing Ack=X 對應欄位第九位 ninth=1（包含讀取最後 byte 的正常 NACK），
不是 frame 的 nack 原因碼。此資料所有 X 均為讀最後 byte NACK，位址 ACK 皆正常。
時間直接比對 START 邊沿，不補償偏移。精細時間列的中位殘差約負 0.73 個取樣，
依任務允許的一個取樣定位差，容差為 max(2×XInc, 文字捨入半量＋XInc)。
原始嚴格容差超出列會另外列出，不能隱藏差異。
"""
import csv
from decimal import Decimal
from pathlib import Path
import re
import numpy as np
from scope_tool.web.i2c_decode import decode_waveforms


def csv_time(value: str) -> tuple[float, float]:
    match = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)(ns|us|ms|s)', value.strip())
    assert match, value
    number, unit = match.groups()
    scale = {'ns': 1e-9, 'us': 1e-6, 'ms': 1e-3, 's': 1.}[unit]
    rounding = float(Decimal(10) ** Decimal(number).as_tuple().exponent) * scale / 2
    return float(number) * scale, rounding


def signature(f: dict) -> tuple:
    address = f"{(f['addr'] << 1) | f['rw']:02X}{'R' if f['rw'] else 'W'}"
    data = tuple(x['value'] for x in f['fields'] if x['kind'] == 'data')
    missing = any(x['ninth'] == 1 for x in f['fields'])
    return address, data, missing, f['start']


def check(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[2] / 'X6000A-解碼' / 'I2C'
    hp, cp = root / 'x6000i2c2.h5', root / 'x6000i2c3.csv'
    if not hp.exists() or not cp.exists():
        print('web.i2c_real_check skip：實機資料檔不存在')
        return dict(skipped=True)
    import h5py
    with h5py.File(hp, 'r') as h5:
        waves, times = {}, []
        for role, channel in (('sda', 1), ('scl', 3)):
            group = h5[f'/Waveforms/Channel {channel}']
            waves[role] = np.asarray(group[f'Channel {channel} Data'])
            dt, origin = float(group.attrs['XInc']), float(group.attrs['XOrg'])
            times.append(origin + np.arange(len(waves[role])) * dt)
        assert np.array_equal(*times), '兩通道時間軸不同'
    with cp.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    manual = decode_waveforms(times[0], waves['scl'], waves['sda'],
                              thresholds={'sda': (1.19, 1.39), 'scl': (.90, 1.10)})
    auto = decode_waveforms(times[0], waves['scl'], waves['sda'])
    assert manual['ok'] and auto['ok'], (manual.get('reason'), auto.get('reason'))
    differences, strict_times = [], []
    for mode, result in (('手動門檻', manual), ('自動門檻', auto)):
        fs = result['frames']
        residuals = [(f['t0'] - csv_time(row['Time'])[0]) / dt for row, f in zip(rows, fs)
                     if csv_time(row['Time'])[1] < dt / 2]
        median = float(np.median(residuals))
        print(f'{mode} 精細時間列 {len(residuals)} 筆，中位殘差 {median:.3f} 個取樣')
        assert -1.25 < median < -.25, '須重新評估系統性取樣定位差，不能直接套容差'
        if len(fs) != len(rows):
            differences.append(f'{mode} 列數：{len(fs)} != {len(rows)}')
        for i, (row, f) in enumerate(zip(rows, fs), 1):
            want = (row['Address'], tuple(int(v, 16) for v in row['Data'].split()),
                    row['Missing Ack'] == 'X', 'Sr' if row['Restart'].strip() else 'S')
            got = signature(f)
            if got != want:
                differences.append(f'{mode} 第 {i} 列：{got} != {want}')
            tm, rounding = csv_time(row['Time'])
            if abs(f['t0'] - tm) > max(2 * dt, rounding):
                strict_times.append(f'{mode} 第 {i} 列：殘差 {(f["t0"] - tm) * 1e6:.6f} us，原容差 {max(2 * dt, rounding) * 1e6:.6f} us')
            if abs(f['t0'] - tm) > max(2 * dt, rounding + dt):
                differences.append(f"{mode} 第 {i} 列時間：{f['t0']:.12g} != {tm:.12g}")
    if [signature(f) for f in manual['frames']] != [signature(f) for f in auto['frames']]:
        differences.append('自動與手動門檻解碼結果不同')
    # 驗證檔頭敘述的實際資料語意，避免將正常讀取終止誤當錯誤。
    for row, f in zip(rows, manual['frames']):
        if row['Missing Ack'] == 'X':
            assert f['rw'] == 1 and f['ack'] and f['fields'][-1]['ninth'] == 1
            assert 'nack' not in f['reasons']
    print(f'實機比對：CSV {len(rows)} 列，手動 {len(manual["frames"])} 列，自動 {len(auto["frames"])} 列')
    print(f'原嚴格時間容差超出清單：{strict_times}')
    print(f'差異清單：{differences if differences else "無；全部相符"}')
    print(f'時間容差：max(2×XInc={2 * dt:.9g} s, CSV 捨入半量＋XInc)，無偏移補償')
    assert not differences, '\n'.join(differences)
    return dict(rows=len(rows), differences=differences, strict_times=strict_times, skipped=False)


if __name__ == '__main__':
    check()
    print('web.i2c_real_check self-check OK')
