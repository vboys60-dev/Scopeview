"""波形與截圖寫檔。永不覆蓋，檔名帶時間戳。"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import tempfile
from pathlib import Path

import h5py
import numpy as np

from scope_tool.contracts import (
    CaptureResult,
    ImageFormat,
    WaveformFormat,
)


def _channel_to_csv_header(channel: str) -> str:
    """把通道名轉成 CSV 欄位名。例如 CHAN1 或 CH1 → CH1。"""
    match = re.search(r'\d+', channel)
    if match:
        num = match.group()
        return f"CH{num}"
    return channel


def _channel_to_hdf5_name(channel: str) -> str:
    """把通道名轉成 HDF5 群組名。例如 CHAN1 → Channel 1。"""
    match = re.search(r'\d+', channel)
    if match:
        num = match.group()
        return f"Channel {num}"
    return channel


def timestamped(directory: Path, name: str, ext: str) -> Path:
    """產生時間戳檔名，同秒撞名就接 _2、_3，永不覆蓋。

    格式：{name}_{YYYYMMDD}_{HHMMSS}.{ext}
    若檔案已存在，改為 {name}_{YYYYMMDD}_{HHMMSS}_2.{ext} 等。
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")

    base = f"{name}_{date_str}_{time_str}"
    filepath = directory / f"{base}.{ext}"

    if filepath.exists():
        counter = 2
        while True:
            filepath = directory / f"{base}_{counter}.{ext}"
            if not filepath.exists():
                break
            counter += 1

    return filepath


def write_screenshot(directory: Path, name: str, data: bytes,
                     fmt: ImageFormat) -> Path:
    """寫圖片檔。

    Args:
        directory: 輸出目錄
        name: 檔名前綴
        data: 影像原始位元組
        fmt: 圖片格式（PNG 或 BMP）

    Returns:
        寫出的檔案路徑
    """
    filepath = timestamped(directory, name, fmt.value.lower())
    filepath.write_bytes(data)
    return filepath


def write_waveform(directory: Path, name: str, result: CaptureResult,
                   fmt: WaveformFormat) -> Path:
    """寫波形檔。

    若 result.native_file 不為 None 且 fmt 為 HDF5，
    則直接寫原始位元組（不重組）；
    否則依格式規格寫 CSV 或 HDF5。

    Args:
        directory: 輸出目錄
        name: 檔名前綴
        result: 波形擷取結果
        fmt: 波形格式（CSV 或 HDF5）

    Returns:
        寫出的檔案路徑
    """
    # 直接寫原生位元組（若有）
    if result.native_file is not None and fmt == WaveformFormat.HDF5:
        filepath = timestamped(directory, name, "h5")
        filepath.write_bytes(result.native_file)
        return filepath

    # 寫 CSV
    if fmt == WaveformFormat.CSV:
        filepath = timestamped(directory, name, "csv")
        _write_csv(filepath, result)
        return filepath

    # 寫 HDF5
    filepath = timestamped(directory, name, "h5")
    _write_hdf5(filepath, result)
    return filepath


def _write_csv(filepath: Path, result: CaptureResult) -> None:
    """寫 CSV：Time(s),CH1(V),CH2(V),... 格式。

    首列為欄位名，之後每列一筆取樣點。
    """
    if not result.waveforms:
        return

    time_axis = result.waveforms[0].time

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # 欄位名
        headers = ['Time(s)']
        for wf in result.waveforms:
            headers.append(f"{_channel_to_csv_header(wf.channel)}(V)")
        writer.writerow(headers)

        # 數據行
        for i in range(len(time_axis)):
            row = [f"{time_axis[i]:.6e}"]
            for wf in result.waveforms:
                row.append(f"{wf.voltage[i]}")
            writer.writerow(row)


def _write_hdf5(filepath: Path, result: CaptureResult) -> None:
    """寫 HDF5：Keysight 原生格式相容。

    結構：
      /Waveforms/Channel 1/Channel 1Data   ← 原始整數 uint16；無法還原整數時存 float64 電壓
        attrs: NumPoints, XInc, XOrg, YInc, YOrg, YReference
      /ScopeTool                           ← 本工具自訂
        attrs: Model, Series, CapturedAt, SCPI (JSON 字串)
    """
    with h5py.File(filepath, 'w') as f:
        waveforms_group = f.create_group('Waveforms')

        for wf in result.waveforms:
            ch_name = _channel_to_hdf5_name(wf.channel)
            ch_group = waveforms_group.create_group(ch_name)

            # 有前導參數且能還原原始碼值時，存 uint16 節省空間
            data = wf.voltage.astype(np.float64, copy=False)
            if wf.preamble and data.size:
                pre = wf.preamble
                raw = (data - pre.y_origin) / pre.y_increment + pre.y_reference
                rounded = np.rint(raw)
                if np.max(np.abs(raw - rounded)) < 1e-3 and np.min(rounded) >= 0 and np.max(rounded) <= 65535:
                    data = rounded.astype(np.uint16)
            ch_group.create_dataset(f"{ch_name}Data", data=data)

            # 寫 attrs（六個必要欄位）
            if wf.preamble:
                ch_group.attrs['NumPoints'] = wf.preamble.points
                ch_group.attrs['XInc'] = wf.preamble.x_increment
                ch_group.attrs['XOrg'] = wf.preamble.x_origin
                ch_group.attrs['YInc'] = wf.preamble.y_increment
                ch_group.attrs['YOrg'] = wf.preamble.y_origin
                ch_group.attrs['YReference'] = wf.preamble.y_reference

        # 寫 /ScopeTool 群組
        scopetool_group = f.create_group('ScopeTool')
        scopetool_group.attrs['Model'] = result.model
        scopetool_group.attrs['Series'] = result.series.value
        scopetool_group.attrs['CapturedAt'] = result.captured_at
        scopetool_group.attrs['SCPI'] = json.dumps(result.scpi_settings)


if __name__ == "__main__":
    from scope_tool.instruments.fake import FakeDriver

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        driver = FakeDriver()

        # 驗收條件 1: 連寫兩次同名 → 兩個不同檔名，第一個檔沒被覆蓋
        result1 = driver.capture(["CHAN1", "CHAN2"], 100, retrigger=False)
        file1 = write_waveform(tmpdir, "test", result1, WaveformFormat.CSV)
        file2 = write_waveform(tmpdir, "test", result1, WaveformFormat.CSV)

        assert file1 != file2, f"檔名應不同：{file1} vs {file2}"
        assert file1.exists(), f"第一個檔應存在：{file1}"
        assert file2.exists(), f"第二個檔應存在：{file2}"

        # 驗收條件 2: CSV 內容首列是 Time(s),CH1(V),CH2(V)，列數 = 點數 + 1
        with open(file1) as f:
            lines = f.readlines()
        assert lines[0].strip() == "Time(s),CH1(V),CH2(V)", \
            f"CSV 欄位名錯誤：{lines[0]}"
        assert len(lines) == 101, \
            f"CSV 列數應為 101（100 筆資料 + 1 欄位名），實際 {len(lines)}"

        # 驗收條件 3: HDF5 結構
        result3 = driver.capture(["CHAN1", "CHAN2"], 50, retrigger=False)
        hdf5_file = write_waveform(tmpdir, "test_hdf5", result3,
                                   WaveformFormat.HDF5)

        with h5py.File(hdf5_file, 'r') as f:
            assert "/Waveforms/Channel 1/Channel 1Data" in f, \
                "HDF5 路徑 /Waveforms/Channel 1/Channel 1Data 不存在"
            data = f["/Waveforms/Channel 1/Channel 1Data"][:]
            assert data.dtype == np.float64  # 模擬波形不是整數碼值，保留電壓
            assert len(data) == 50, \
                f"波形長度應為 50，實際 {len(data)}"

            attrs = f["/Waveforms/Channel 1"].attrs
            required_attrs = ['NumPoints', 'XInc', 'XOrg', 'YInc', 'YOrg',
                            'YReference']
            for attr in required_attrs:
                assert attr in attrs, f"HDF5 attrs 缺少 {attr}"

        # 整數碼值寫入後，讀回電壓不得損失精度
        from scope_tool.contracts import Preamble, Waveform
        from scope_tool.storage.reader import read_waveform_file
        pre = Preamble.parse("1,2,5,1,1e-9,0,0,0.01,0.125,128")
        raw = np.array([0, 1, 128, 32768, 65535], dtype=np.uint16)
        result3.waveforms = [Waveform.from_raw("CHAN1", pre, raw)]
        integer_file = write_waveform(tmpdir, "integer", result3, WaveformFormat.HDF5)
        with h5py.File(integer_file, "r") as f:
            stored = f["Waveforms/Channel 1/Channel 1Data"]
            assert stored.dtype == np.uint16 and np.array_equal(stored[:], raw)
        restored = read_waveform_file(integer_file)[0]
        assert np.max(np.abs(restored.voltage - result3.waveforms[0].voltage)) < 1e-12
        result3.waveforms = [Waveform("CHAN1", restored.time, restored.voltage)]
        float_file = write_waveform(tmpdir, "float", result3, WaveformFormat.HDF5)
        with h5py.File(float_file, "r") as f:
            assert f["Waveforms/Channel 1/Channel 1Data"].dtype == np.float64

        # 驗收條件 4: native_file 有值時，寫出來的位元組與傳入的完全相同
        result4 = driver.capture(["CHAN1"], 10, retrigger=False)
        native_content = b"test native hdf5 content here"
        result4.native_file = native_content
        native_file = write_waveform(tmpdir, "native_test", result4,
                                     WaveformFormat.HDF5)
        written_bytes = native_file.read_bytes()

        assert written_bytes == native_content, \
            f"native_file 位元組不符：期望 {len(native_content)} 字節，" \
            f"得到 {len(written_bytes)} 字節"

    print("writer self-check OK")
