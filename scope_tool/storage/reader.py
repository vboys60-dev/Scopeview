"""波形檔案讀取器。支援 CSV 與 HDF5 格式。"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import replace
from pathlib import Path

import h5py
import numpy as np

from scope_tool.contracts import ScopeError, Waveform


def read_file_info(path: Path) -> dict[str, str]:
    """直接讀取 HDF5 的工具資訊，不載入波形或整個檔案。"""
    if path.suffix.lower() not in (".h5", ".hdf5"):
        return {}
    try:
        with h5py.File(path, "r") as hf:
            if "ScopeTool" not in hf:
                return {}
            attrs = hf["ScopeTool"].attrs
            return {key: attrs[key].decode() if isinstance(attrs[key], bytes) else str(attrs[key])
                    for key in ("Model", "Series", "CapturedAt") if key in attrs}
    except Exception as e:
        raise ScopeError(f"讀取 HDF5 檔案資訊時發生錯誤：{e}") from e


def read_waveform_file(path: Path) -> list[Waveform]:
    """從檔案讀取波形。支援 .csv、.h5、.hdf5、.bin（Keysight AG10）格式。"""
    suffix = path.suffix.lower()
    if suffix == ".bin":
        return _read_bin(path)
    if suffix == ".csv":
        return _read_csv(path)
    elif suffix in (".h5", ".hdf5"):
        return read_waveform_bytes(path.read_bytes())
    raise ScopeError(f"不支援的檔案格式：{suffix}。請使用 .csv、.h5 / .hdf5 或 .bin 檔案。")


def read_waveform_bytes(data: bytes) -> list[Waveform]:
    """從 HDF5 位元組讀取波形。給 T3（存檔轉取）使用。"""
    try:
        with h5py.File(io.BytesIO(data), "r") as hf:
            return _extract_waveforms(hf)
    except ScopeError:
        raise
    except Exception as e:
        raise ScopeError(f"讀取 HDF5 資料時發生錯誤：{e}")


def _read_bin(path: Path) -> list[Waveform]:
    """BIN 以通道標籤當通道名（SDA1、TX1…）；標籤重複時加 #2、#3 以維持唯一。"""
    from scope_tool.storage.bin_reader import read_bin_file
    seen: dict[str, int] = {}
    waves = []
    for label, w in read_bin_file(path):
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            w = replace(w, channel=f"{label}#{seen[label]}")
        waves.append(w)
    return waves


def _read_csv(path: Path) -> list[Waveform]:
    """讀取本工具格式的 CSV 檔案。格式：Time(s),CH1(V),CH2(V),... """
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header or header[0] != "Time(s)":
                raise ScopeError("不支援示波器面板匯出的 CSV，請用本工具擷取。")

            channels = header[1:]
            if not channels or not all(col.endswith("(V)") for col in channels):
                raise ScopeError("不支援示波器面板匯出的 CSV，請用本工具擷取。")

            rows = list(reader)
            if not rows:
                raise ScopeError("CSV 檔案無資料列。")

            # 逐行讀資料
            time_list, volt_dict = [], {col: [] for col in channels}
            for row_idx, row in enumerate(rows, 2):
                if len(row) != len(header):
                    raise ScopeError(f"CSV 第 {row_idx} 列欄位數不符。")
                try:
                    time_list.append(float(row[0]))
                    for col_idx, col in enumerate(channels, 1):
                        volt_dict[col].append(float(row[col_idx]))
                except ValueError as e:
                    raise ScopeError(f"CSV 第 {row_idx} 列資料格式錯誤：{e}")

            time = np.array(time_list, dtype=np.float64)
            return [Waveform(
                channel=f"CHAN{col[2:-3]}" if re.fullmatch(r"CH[0-9]+\(V\)", col) else col[:-3],
                time=time,
                voltage=np.array(volt_dict[col], dtype=np.float64),
                preamble=None
            ) for col in channels]

    except ScopeError:
        raise
    except Exception as e:
        raise ScopeError(f"讀取 CSV 檔案時發生錯誤：{e}")


def _extract_waveforms(hf: h5py.File) -> list[Waveform]:
    """從已開啟的 HDF5 檔案提取波形。結構：/Waveforms/Channel N/Channel NData。"""
    if "Waveforms" not in hf:
        raise ScopeError("HDF5 檔案缺少 /Waveforms 群組。")

    waveforms = []
    for ch_key in sorted(hf["Waveforms"].keys()):
        data_key = f"{ch_key}Data"
        if data_key not in hf["Waveforms"][ch_key]:
            continue

        dataset = hf["Waveforms"][ch_key][data_key]
        # 契約/Keysight 原生：attrs 在 group 上；退回 dataset attrs 容忍舊檔
        attrs = hf["Waveforms"][ch_key].attrs
        if "XInc" not in attrs:
            attrs = dataset.attrs

        if "XInc" not in attrs or "XOrg" not in attrs:
            raise ScopeError(f"HDF5 {data_key} 缺少時間軸參數。")

        voltage = np.array(dataset, dtype=np.float64)
        if np.issubdtype(dataset.dtype, np.integer) and all(
                key in attrs for key in ("YInc", "YOrg")):
            # 本工具的原始碼值須扣參考值；MXR254B 原生 H5INt 實測不扣。
            if "ScopeTool" in hf:
                voltage -= float(attrs["YReference"])
            voltage = voltage * float(attrs["YInc"]) + float(attrs["YOrg"])
        x_inc = float(attrs["XInc"])
        x_org = float(attrs["XOrg"])
        time = np.arange(len(voltage), dtype=np.float64) * x_inc + x_org

        # 通道名正規化：Channel N → CHANN
        ch_name = f"CHAN{ch_key[8:].strip()}" if ch_key.startswith("Channel ") else ch_key

        waveforms.append(Waveform(
            channel=ch_name,
            time=time,
            voltage=voltage,
            preamble=None
        ))

    if not waveforms:
        raise ScopeError("HDF5 檔案中找不到波形資料。")
    return waveforms


def _self_check() -> None:
    """自我檢查。寫測試檔讀回驗證。"""
    import tempfile
    import shutil

    tmpdir = Path(tempfile.gettempdir()) / "scope_tool_reader_test"
    tmpdir.mkdir(exist_ok=True)

    try:
        # 測試 0：BIN 走 .bin 分派，通道名＝標籤（資料檔不存在則略過）
        real = Path(__file__).resolve().parents[2] / "X6000A-解碼" / "I2C" / "x6000i2c1.bin"
        if real.exists():
            assert [w.channel for w in read_waveform_file(real)] == ["SDA1", "SCL1"]

        # 測試 1：CSV
        csv_file = tmpdir / "test.csv"
        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Time(s)", "CH1(V)", "CH2(V)"])
            writer.writerow([0.0, 1.0, 2.0])
            writer.writerow([1e-6, 1.1, 2.1])
            writer.writerow([2e-6, 1.2, 2.2])

        wf = read_waveform_file(csv_file)
        assert len(wf) == 2, f"CSV：通道數錯誤 {len(wf)}"
        assert [waveform.channel for waveform in wf] == ["CHAN1", "CHAN2"]
        assert len(wf[0].time) == 3, f"CSV：點數錯誤"
        assert abs(wf[0].time[0] - 0.0) < 1e-12 and abs(wf[0].time[-1] - 2e-6) < 1e-12
        assert abs(wf[0].voltage[0] - 1.0) < 1e-12

        # 測試 2：HDF5（含 /ScopeTool）
        h5_file = tmpdir / "test.h5"
        with h5py.File(h5_file, "w") as hf:
            hf.create_group("ScopeTool").attrs["Model"] = "DSO-X 3014G"
            wf_group = hf.create_group("Waveforms")

            for ch_num in [1, 2]:
                ch_group = wf_group.create_group(f"Channel {ch_num}")
                data = ch_group.create_dataset(
                    f"Channel {ch_num}Data",
                    data=np.array([1.0 + ch_num*0.1*i for i in range(3)], dtype=np.float64)
                )
                data.attrs["XInc"] = 1e-6
                data.attrs["XOrg"] = 0.0
                data.attrs["YInc"] = 0.1
                data.attrs["YOrg"] = float(ch_num)
                data.attrs["YReference"] = 0
                data.attrs["NumPoints"] = 3

        assert read_file_info(h5_file)["Model"] == "DSO-X 3014G"
        wf = read_waveform_file(h5_file)
        assert len(wf) == 2
        assert len(wf[0].time) == 3
        assert abs(wf[0].time[0] - 0.0) < 1e-12 and abs(wf[0].time[-1] - 2e-6) < 1e-12

        # 測試 3：HDF5 無 /ScopeTool
        h5_no_scope = tmpdir / "test_no_scope.h5"
        with h5py.File(h5_no_scope, "w") as hf:
            wf_group = hf.create_group("Waveforms")
            ch_group = wf_group.create_group("Channel 1")
            data = ch_group.create_dataset("Channel 1Data", data=np.array([1.0, 1.1, 1.2], dtype=np.float64))
            data.attrs.update({"XInc": 1e-6, "XOrg": 0.0, "YInc": 0.1, "YOrg": 1.0, "YReference": 0, "NumPoints": 3})

        assert read_file_info(h5_no_scope) == {}
        assert read_file_info(csv_file) == {}
        wf = read_waveform_file(h5_no_scope)
        assert len(wf) == 1, "應能容忍缺 /ScopeTool"

        # 原生整數 H5 也要依 attrs 換算電壓
        with h5py.File(h5_no_scope, "a") as hf:
            group = hf["Waveforms/Channel 1"]
            del group["Channel 1Data"]
            group.create_dataset("Channel 1Data", data=np.array([-2, 0, 2], dtype=np.int16))
            group.attrs.update({"XInc": 1e-6, "XOrg": 0.0, "YInc": 0.1, "YOrg": 1.0, "YReference": 1})
        assert np.max(np.abs(read_waveform_file(h5_no_scope)[0].voltage - [0.8, 1.0, 1.2])) < 1e-12

        # 測試 4：不支援的格式 .txt
        txt_file = tmpdir / "test.txt"
        txt_file.write_text("text")
        try:
            read_waveform_file(txt_file)
            raise AssertionError("應拋 ScopeError")
        except ScopeError as e:
            assert "不支援的檔案格式" in str(e)

        # 測試 5：示波器面板 CSV
        scope_csv = tmpdir / "scope.csv"
        with open(scope_csv, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows([["Time", "CH1", "CH2"], [0.0, 1.0, 2.0]])
        try:
            read_waveform_file(scope_csv)
            raise AssertionError("應拋 ScopeError")
        except ScopeError as e:
            assert "不支援示波器面板匯出" in str(e)

        # 測試 6：bytes 與 file 一致
        h5_bytes = h5_file.read_bytes()
        wf_bytes = read_waveform_bytes(h5_bytes)
        wf_file = read_waveform_file(h5_file)
        assert len(wf_bytes) == len(wf_file)
        for wb, wf in zip(wf_bytes, wf_file):
            assert np.allclose(wb.time, wf.time)
            assert np.allclose(wb.voltage, wf.voltage)

        print("reader self-check OK")

    finally:
        if tmpdir.exists():
            shutil.rmtree(tmpdir)


if __name__ == "__main__":
    _self_check()
