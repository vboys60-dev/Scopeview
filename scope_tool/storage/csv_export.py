"""依 RULES.md 第 5 條匯出 CSV：共用時間軸、游標範圍、縮點與逐欄科學記號。"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np

from scope_tool.contracts import ScopeError, Waveform
from scope_tool.storage import writer

_BLOCK = 1_000_000


def _sci_format(values: np.ndarray) -> str:
    """相異值以最小間隔與最大絕對值決定 1–17 位有效數字；常數保留可還原位數。"""
    if not values.size:
        raise ScopeError("沒有取樣點可匯出。")
    u = np.unique(values)
    if not np.all(np.isfinite(u)):
        raise ScopeError("CSV 取樣值必須是有限數值。")
    if len(u) >= 2:
        step = np.min(np.diff(u))
        M = np.max(np.abs(u))
        sig = min(17, max(1, math.ceil(math.log10(M / step)) + 2))
    else:
        value = float(u[0])
        sig = next(s for s in range(1, 18) if float(f"{value:.{s-1}e}") == value)
    return f"%.{sig-1}e"


def export_csv(directory: Path, name: str, waveforms: list[Waveform],
               t_range: tuple[float, float] | None = None,
               max_points: int | None = None) -> Path:
    """先含端點選區間，再從區間第一點每 N 點取一點，逐塊寫入時間戳檔案。"""
    if max_points is not None and max_points < 1:
        raise ScopeError("點數上限必須至少為 1。")
    if not waveforms or not len(waveforms[0].time):
        raise ScopeError("沒有取樣點可匯出。")
    time = waveforms[0].time
    if any(len(w.time) != len(time) or len(w.voltage) != len(time) for w in waveforms):
        raise ScopeError("所有通道長度必須一致。")
    columns = [time] + [w.voltage for w in waveforms]
    if t_range is None:
        lo, hi = 0, len(time)
    else:
        low, high = min(t_range), max(t_range)
        lo = np.searchsorted(time, low, 'left')
        hi = np.searchsorted(time, high, 'right')
    if hi <= lo:
        raise ScopeError("游標區間內沒有取樣點。")
    count = hi - lo
    stride = math.ceil(count / max_points) if max_points else 1
    selected = [c[lo:hi:stride] for c in columns]
    t0 = selected[0]
    dt = (time[-1] - time[0]) / (len(time) - 1) if len(time) > 1 else 0
    tol = 0.01 * dt
    for w in waveforms[1:]:
        for start in range(0, len(t0), _BLOCK):
            d = np.max(np.abs(w.time[lo:hi:stride][start:start + _BLOCK] - t0[start:start + _BLOCK]))
            if not d <= tol:
                raise ScopeError(f"通道 {w.channel} 的時間軸與 {waveforms[0].channel} 不一致（最大差 {d:.3g} s，容差 {tol:.3g} s），無法共用時間欄匯出。")
    formats = [_sci_format(column) for column in selected]
    header = ["Time(s)"] + [f"{n}(V)" for n in writer._unique_names([w.channel for w in waveforms], "CH{n}")]
    try:
        def write(tmp: Path) -> None:
            with tmp.open("w", encoding="utf-8", newline="") as stream:
                stream.write(",".join(header) + "\n")
                for start in range(0, len(selected[0]), _BLOCK):
                    block = np.column_stack([column[start:start + _BLOCK] for column in selected])
                    np.savetxt(stream, block, fmt=formats, delimiter=",")
        path = writer._atomic(writer.timestamped(directory, name, "csv"), write)
    except OSError as exc:
        raise ScopeError(f"匯出 CSV 失敗：{exc}") from exc
    return path


def _self_check() -> None:
    from scope_tool.contracts import Preamble
    from scope_tool.storage.reader import read_waveform_file

    pre = Preamble.parse("1,2,100,1,1e-11,-5e-4,0,6e-4,0.3,32768")
    waves = [Waveform.from_raw(ch, pre, np.arange(30000, 30100)) for ch in ("CHAN1", "CHAN2")]
    time, voltage = waves[0].time, waves[0].voltage
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        path = export_csv(directory, "precision", waves)
        restored = read_waveform_file(path)
        for wave in restored:
            assert np.max(np.abs(wave.time - time)) < 1e-12
            assert np.max(np.abs(wave.voltage - voltage)) < 6e-5
            assert len(np.unique(wave.voltage)) == 100
        with path.open() as stream:
            assert stream.readline().strip() == "Time(s),CH1(V),CH2(V)"
            assert stream.readline().strip() == f"{time[0]:.9e},{voltage[0]:.5e},{voltage[0]:.5e}"
        cut = read_waveform_file(export_csv(directory, "cut", waves, (time[60], time[20])))[0]
        assert len(cut.time) == 41
        assert cut.time[0] == time[20] and cut.time[-1] == time[60]
        large = [Waveform(ch, np.arange(1000, dtype=float), np.arange(1000, dtype=float))
                 for ch in ("CHAN1", "CHAN2")]
        reduced = read_waveform_file(export_csv(directory, "reduced", large, max_points=300))[0]
        assert len(reduced.time) == 250 and reduced.time[0] == 0 and reduced.time[1] == 4
        both = read_waveform_file(export_csv(directory, "both", large, (100, 199), 30))[0]
        assert np.array_equal(both.time, large[0].time[100:200:4])
        for inputs, kwargs in [(waves, {"t_range": (1, 2)}),
                               ([waves[0], large[0]], {}), (waves, {"max_points": 0})]:
            try:
                export_csv(directory, "invalid", inputs, **kwargs)
            except ScopeError:
                pass
            else:
                raise AssertionError("無效參數應拋 ScopeError")
        t = np.array([0., 1., 2.])
        first = Waveform("first", t, t)
        for offset in (10., 0.02, np.nan):
            second = Waveform("second", t + offset, t)
            try:
                export_csv(directory, "mismatch", [first, second])
            except ScopeError as exc:
                assert "second" in str(exc)
            else:
                raise AssertionError("時間軸不一致應拋 ScopeError")
        second = Waveform("second", t + 0.0008, t)
        back = read_waveform_file(export_csv(directory, "tolerance", [first, second]))[0]
        assert np.array_equal(back.time, t)
        second = Waveform("second", np.array([10., 1., 2.]), t)
        export_csv(directory, "selected", [first, second], (1, 2))
        export_csv(directory, "single", [first])
        constant = Waveform("CHAN1", time, np.full(100, 0.0123456789))
        back = read_waveform_file(export_csv(directory, "constant", [constant]))[0]
        assert np.array_equal(back.voltage, constant.voltage)
        assert _sci_format(np.array([-0.010699999999999987, -0.0101])) == "%.3e"
    print("csv_export self-check OK")


if __name__ == "__main__":
    _self_check()
