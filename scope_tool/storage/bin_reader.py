from __future__ import annotations

"""獨立的 Keysight AG10 類比波形讀取器；不負責檔案格式分派。"""

import struct
from pathlib import Path

import numpy as np

from scope_tool.contracts import ScopeError, Waveform


_WAVE_HEADER = struct.Struct("<iiiiifdddii16s16s24s16sdi")
_DATA_HEADER = struct.Struct("<ihhi")
_ERROR_PREFIX = "讀取 BIN 檔案時發生錯誤："


def _fail(reason: str) -> None:
    raise ScopeError(_ERROR_PREFIX + reason)


def _require_span(data: bytes, offset: int, size: int, name: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        _fail(f"{name}超出檔尾或長度無效。")


def read_bin_bytes(data: bytes) -> list[tuple[str, Waveform]]:
    """讀取 AG10 單一浮點 buffer 波形，保留標籤及原始取樣順序。"""
    try:
        _require_span(data, 0, 12, "檔案標頭")
        cookie, version, total_size, count = struct.unpack_from("<2s2sii", data)
        if cookie != b"AG":
            _fail("檔案識別碼不是 AG。")
        if version != b"10":
            _fail("僅支援版本 10。")
        if total_size != len(data):
            _fail("宣告的檔案總大小與實際長度不符。")
        if count <= 0:
            _fail("波形數必須大於 0。")
        result = []
        offset = 12
        for index in range(1, count + 1):
            _require_span(data, offset, 4, "波形標頭長度欄位")
            hs = struct.unpack_from("<i", data, offset)[0]
            if hs < _WAVE_HEADER.size:
                _fail("波形標頭長度不足以包含必要欄位。")
            _require_span(data, offset, hs, "波形標頭")
            fields = _WAVE_HEADER.unpack_from(data, offset)
            wave_type, n_buffers, points = fields[1:4]
            x_inc, x_origin = fields[7:9]
            if wave_type != 1:
                _fail(f"不支援波形類型 {wave_type}（包含峰值偵測或數位波形）。")
            if n_buffers != 1:
                _fail(f"僅支援單一 buffer，不支援多 buffer／峰值偵測：{n_buffers}。")
            if points < 2:
                _fail("取樣點數必須至少為 2。")
            if not np.isfinite(x_inc) or x_inc <= 0:
                _fail("XInc 必須是有限且大於 0 的數值。")
            if not np.isfinite(x_origin):
                _fail("XOrigin 必須是有限數值。")
            label = fields[14].decode("ascii").replace("\x00", "").strip()
            label = label or f"WAVE{index}"
            offset += hs
            _require_span(data, offset, _DATA_HEADER.size, "資料標頭")
            dhs, buffer_type, bytes_per_point, buffer_size = _DATA_HEADER.unpack_from(data, offset)
            if dhs < _DATA_HEADER.size:
                _fail("資料標頭長度不足以包含必要欄位。")
            _require_span(data, offset, dhs, "資料標頭")
            if buffer_type != 1:
                _fail(f"不支援 buffer 類型 {buffer_type}，僅支援類比浮點資料（不含數位 buffer）。")
            if bytes_per_point != 4:
                _fail(f"每點位元組數必須為 4，實際為 {bytes_per_point}。")
            if points * 4 != buffer_size:
                _fail("取樣點數乘以 4 與 bufferSize 不符。")
            offset += dhs
            _require_span(data, offset, buffer_size, "波形資料")
            voltage = np.frombuffer(data, dtype="<f4", count=points, offset=offset).astype(np.float64)
            with np.errstate(over="raise", invalid="raise"):
                time = np.arange(points, dtype=np.float64) * x_inc + x_origin
            result.append((label, Waveform(label, time, voltage, preamble=None)))
            offset += buffer_size
        if offset != len(data):
            _fail("波形結束後仍有未宣告的資料。")
        return result
    except ScopeError:
        raise
    except Exception as e:
        raise ScopeError(_ERROR_PREFIX + "標頭解析、標籤解碼或陣列轉換失敗。") from e


def read_bin_file(path: Path) -> list[tuple[str, Waveform]]:
    """從路徑讀取 BIN，將檔案存取錯誤轉成共用錯誤型別。"""
    try:
        return read_bin_bytes(path.read_bytes())
    except ScopeError:
        raise
    except Exception as e:
        raise ScopeError(_ERROR_PREFIX + f"無法讀取檔案：{path}。") from e


def guess_roles(labels: list[str], protocol: str) -> dict[str, str]:
    """以通道標籤前綴提供角色建議，缺少的角色不填入。"""
    roles = {"i2c": ("scl", "sda"), "uart": ("tx", "rx")}.get(protocol.lower(), ())
    result = {}
    for role in roles:
        for label in labels:
            if label.lower().startswith(role):
                result[role] = label
                break
    return result


def _self_check() -> None:
    """組裝最小波形、檢查壞檔，並在資料存在時核對實機 H5。"""
    import tempfile

    values = [np.array([1.25, -2.5, 0, 8], dtype="<f4"),
              np.array([-1, 2, 3, 0.125], dtype="<f4")]

    def assemble(labels: tuple[str, ...] = (" SDA1 ", "SCL1"),
                 hs: int = 140, dhs: int = 12) -> bytes:
        # 組裝器只供自檢使用；擴充區填值可抓出寫死標頭長度的錯誤。
        body = bytearray()
        for label, voltage in zip(labels, values):
            body += _WAVE_HEADER.pack(hs, 1, 1, len(voltage), 1, 1, 0, 0.25, -0.5,
                                      2, 1, b"", b"", b"", label.encode(), 0, 0)
            body += b"W" * (hs - _WAVE_HEADER.size)
            body += _DATA_HEADER.pack(dhs, 1, 4, voltage.nbytes)
            body += b"D" * (dhs - _DATA_HEADER.size) + voltage.tobytes()
        return struct.pack("<2s2sii", b"AG", b"10", 12 + len(body), len(labels)) + body

    def changed(data: bytes, offset: int, fmt: str, value: object) -> bytes:
        output = bytearray(data)
        struct.pack_into(fmt, output, offset, value)
        return bytes(output)

    def rejected(data: bytes, reason: str = "") -> None:
        try:
            read_bin_bytes(data)
        except ScopeError as e:
            assert str(e).startswith(_ERROR_PREFIX) and reason in str(e), str(e)
        else:
            raise AssertionError("壞檔應拋出 ScopeError。")

    good = assemble()
    for data in (good, assemble(hs=156, dhs=20)):
        waves = read_bin_bytes(data)
        assert [label for label, _ in waves] == ["SDA1", "SCL1"]
        for index, (label, wave) in enumerate(waves):
            assert wave.channel == label and wave.preamble is None
            assert wave.time.dtype == wave.voltage.dtype == np.dtype("float64")
            assert np.array_equal(wave.voltage, values[index])
            assert np.array_equal(wave.time, -0.5 + np.arange(4, dtype=np.float64) * 0.25)
    assert [label for label, _ in read_bin_bytes(assemble(("", " \x00 ")))] == ["WAVE1", "WAVE2"]
    assert read_bin_bytes(assemble(("TX1", "RX1")))[0][0] == "TX1"

    # 每一種不支援格式與邊界錯誤都須由 ScopeError 說明原因。
    bad_fields = [
        (0, "2s", b"ZZ", "識別碼"), (2, "2s", b"11", "版本"),
        (4, "i", len(good) + 1, "總大小"), (8, "i", 0, "波形數"),
        (8, "i", -1, "波形數"), (16, "i", 2, "峰值偵測"),
        (16, "i", 5, "數位"), (20, "i", 2, "多 buffer"),
        (20, "i", 0, "單一 buffer"), (24, "i", 1, "取樣點數"),
        (24, "i", -1, "取樣點數"), (44, "d", 0, "XInc"),
        (44, "d", -1, "XInc"), (44, "d", float("nan"), "XInc"),
        (44, "d", float("inf"), "XInc"), (52, "d", float("nan"), "XOrigin"),
        (44, "d", 1e308, "陣列轉換"), (24, "i", 0, "取樣點數"),
        (12, "i", 139, "標頭長度"), (12, "i", len(good), "超出檔尾"),
        (152, "i", 11, "標頭長度"), (152, "i", len(good), "超出檔尾"),
        (156, "h", 6, "數位 buffer"), (156, "h", 2, "buffer 類型"),
        (158, "h", 2, "位元組數"), (160, "i", 12, "bufferSize"),
        (160, "i", -1, "bufferSize"), (124, "B", 255, "標籤解碼"),
    ]
    for offset, fmt, value, reason in bad_fields:
        rejected(changed(good, offset, "<" + fmt, value), reason)
    rejected(changed(good + b"X", 4, "<i", len(good) + 1), "未宣告")
    rejected(changed(good, 8, "<i", 3), "超出檔尾")
    # 原檔總長與修正總長兩者皆逐 byte 截斷，避免只驗到檔案大小檢查。
    for length in range(len(good)):
        rejected(good[:length])
        if length >= 12:
            rejected(changed(good[:length], 4, "<i", length))
    assert len(read_bin_bytes(good[:len(good)])) == 2
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "check.bin"
        path.write_bytes(good)
        assert np.array_equal(read_bin_file(path)[0][1].voltage, values[0])
        try:
            read_bin_file(Path(temp) / "不存在.bin")
        except ScopeError as e:
            assert str(e).startswith(_ERROR_PREFIX)
        else:
            raise AssertionError("不存在的檔案應拋出 ScopeError。")

    assert guess_roles(["SDA1", "SCL1"], "i2c") == {"sda": "SDA1", "scl": "SCL1"}
    assert guess_roles(["TX1", "RX1"], "uart") == {"tx": "TX1", "rx": "RX1"}
    assert guess_roles(["sDa1", "ScL1", "SCL2"], "I2C") == {"sda": "sDa1", "scl": "ScL1"}
    assert guess_roles(["tX1", "Rx1", "TX2"], "UART") == {"tx": "tX1", "rx": "Rx1"}
    assert guess_roles(["SDA1"], "i2c") == {"sda": "SDA1"}
    assert guess_roles(["RX1"], "uart") == {"rx": "RX1"}
    assert guess_roles([], "i2c") == {}
    assert guess_roles(["SDA1", "TX1"], "other") == {}

    print("合成波形、加長標頭、壞檔、逐 byte 截斷及角色推測：通過")
    _check_real_files()
    print("storage.bin_reader self-check OK")


def _check_real_files() -> None:
    """只在自檢時使用 h5py，正式讀取器僅依賴 numpy 與標準函式庫。"""
    root = Path(__file__).resolve().parents[2] / "X6000A-解碼"
    cases = [("I2C", "x6000i2c1", "x6000i2c2", {"SDA1": 1, "SCL1": 3}),
             ("RS-232", "x6000rs233", "x6000rs234", {"TX1": 1, "RX1": 3}),
             ("CAN", "x6000can", "x6000can", {"CAN_L-H1": 3})]
    failures = []
    for folder, bin_name, h5_name, channels in cases:
        bin_path = root / folder / (bin_name + ".bin")
        h5_path = root / folder / (h5_name + ".h5")
        if not bin_path.exists() or not h5_path.exists():
            print(f"實機比對 {folder}：略過（資料檔不存在）")
            continue
        import h5py

        data = bin_path.read_bytes()
        waves = read_bin_file(bin_path)
        assert [label for label, _ in waves] == list(channels)
        offset = 12
        with h5py.File(h5_path, "r") as hf:
            for label, wave in waves:
                group = hf[f"Waveforms/Channel {channels[label]}"]
                dataset = group[f"Channel {channels[label]} Data"]
                voltage = dataset[::33][:1955]
                h5_inc, h5_origin = float(group.attrs["XInc"]), float(group.attrs["XOrg"])
                time = (np.arange(len(dataset), dtype=np.float64) * h5_inc + h5_origin)[::33][:1955]
                bin_inc = struct.unpack_from("<d", data, offset + 32)[0]
                assert len(wave.voltage) == 1955
                # 兩檔 float32 各自換算，差約 1 ULP（≤1.2e-7 V，遠小於 1 LSB＝1.3e-4 V）；容差取 4e-7 V
                equal = np.allclose(wave.voltage, voltage, rtol=0, atol=4e-7)
                if not equal:
                    failures.append(f"{folder}/{label}")
                time_error = float(np.max(np.abs(wave.time - time)))
                assert time_error < 1e-12
                assert abs(bin_inc / (33 * h5_inc) - 1) < 1e-9
                voltage_error = float(np.max(np.abs(wave.voltage - voltage)))
                different = int(np.count_nonzero(wave.voltage != voltage))
                print(f"實機比對 {folder}/{label}：電壓在 4e-7 V 內相等={equal}，"
                      f"差異 {different}/1955 點，最大電壓差 {voltage_error:.12g} V，"
                      f"時間差 {time_error:.3g} 秒，XInc 比例 33 通過")
                hs = struct.unpack_from("<i", data, offset)[0]
                dhs, _, _, size = _DATA_HEADER.unpack_from(data, offset + hs)
                offset += hs + dhs + size
    assert not failures, "實機電壓超出 4e-7 V 容差：" + "、".join(failures)


if __name__ == "__main__":
    _self_check()
