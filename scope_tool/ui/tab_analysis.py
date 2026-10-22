"""波形分析頁（Infiniium 風格）：開檔、通道、游標、量測、數學的行為；版面與接線在 analysis_layout.py。"""
from __future__ import annotations

import os

# 必須在匯入 pyqtgraph 前指定 Qt 綁定。
os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from scope_tool.contracts import ScopeError, Waveform
from scope_tool.storage.reader import read_waveform_file
from scope_tool.ui.analysis_export import export_results
from scope_tool.ui.analysis_layout import setup_ui, wire
from scope_tool.ui.analysis_math import run_math
from scope_tool.ui.analysis_results import file_info_rows, fmt
from scope_tool.ui.worker import Job

# 通道顏色循環，數量夠多不必為固定值另外做設定。
_CHANNEL_COLORS = ["#ffcc00", "#00d0ff", "#ff5b5b", "#7cff5b", "#c58bff", "#ff9d3f"]


class AnalysisTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._waveforms: list[Waveform] = []  # 原始通道在前，衍生波形 F1、F2… 在後
        self._units: dict[str, str] = {}
        self._colors: list[str] = []
        self._n_raw = 0
        self._source_path: Path | None = None
        self._jobs: set[Job] = set()
        self._gen, self._next_f = 0, 1  # 開檔世代（丟棄舊檔的數學結果）；F 編號不重用，量測來源才不會被頂替
        setup_ui(self)
        wire(self)

    # ---- 開檔與通道 ----
    def _on_open_clicked(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "開啟波形檔", "", "波形檔 (*.csv *.h5 *.hdf5)")
        try:
            if path_str:
                self._open_file(Path(path_str))
        except ScopeError as e:
            QMessageBox.critical(self, "開檔失敗", str(e))

    def _open_file(self, path: Path) -> None:
        self.load_waveforms(read_waveform_file(path), source_path=path)

    def load_waveforms(self, waveforms: list[Waveform], source_path: Path | None = None) -> None:
        """畫一組原始波形（衍生波形清空，量測清單保留、依通道名對應）。"""
        if not waveforms:
            raise ScopeError("沒有波形資料可畫。")
        self.markers.measurements, self.markers.measurement_source = [], ""
        self._source_path, self._gen = source_path, self._gen + 1
        self._waveforms, self._n_raw = list(waveforms), len(waveforms)
        self._units = {wf.channel: "V" for wf in waveforms}
        self._colors = [_CHANNEL_COLORS[i % len(_CHANNEL_COLORS)] for i in range(len(waveforms))]
        self.export_bar.set_data(list(waveforms), source_path)  # 只匯出原始通道
        self.plot_widget.set_waveforms(waveforms, self._colors, ["V"] * len(waveforms))
        self.overview.set_waveforms(waveforms, self._colors)
        self.toolbar.set_loaded(True)
        self.measbar.setEnabled(True)
        t = waveforms[0].time
        rate = fmt(1 / float(t[1] - t[0]), "Sa/s") if len(t) > 1 and t[1] > t[0] else "—"
        self.toolbar.summary.setText(f"{len(t):,} 點｜{rate}")
        span = t[-1] - t[0]
        self.vline1.setValue(t[0] + span * 0.25)
        self.vline2.setValue(t[0] + span * 0.75)
        self.hline1.setValue(-2)
        self.hline2.setValue(2)
        self._refresh_channels()

    def _names(self) -> list[str]:
        return [wf.channel for wf in self._waveforms]

    def _refresh_channels(self) -> None:
        names = self._names()
        self.chanbar.set_channels(names, self._colors, [self._units[n] for n in names],
                                  [i >= self._n_raw for i in range(len(names))],
                                  [c.isVisible() for c in self.plot_widget.curves])
        self.fft.set_sources(names)
        self._offsets_changed()

    def _offsets_changed(self) -> None:
        for i, (scale, (_, pos)) in enumerate(zip(self.plot_widget.scales, self.plot_widget.offsets)):
            self.chanbar.set_state(i, scale, pos)
        self._update_readout()
        self._range_changed()

    def _set_color(self, i: int, color: str) -> None:
        self._colors[i] = color
        self.plot_widget.set_color(i, color)
        if i < self._n_raw:
            self.overview.set_color(i, color)
        self._update_readout()
        self.runner.run()

    def _remove_channel(self, i: int) -> None:
        if i < self._n_raw:
            return
        name = self._waveforms.pop(i).channel
        self._colors.pop(i)
        del self._units[name]
        self.plot_widget.remove_waveform(i)
        self._refresh_channels()

    def _show_file_info(self) -> None:
        QMessageBox.information(self, "檔案資訊", "\n".join(
            f"{k}：{v}" for k, v in file_info_rows(self._source_path, self._waveforms[:self._n_raw])))

    # ---- 游標 ----
    @staticmethod
    def _nearest(time: np.ndarray, voltage: np.ndarray, t: float) -> tuple[float, float]:
        idx = min(max(int(np.searchsorted(time, t)), 0), len(time) - 1)
        if idx > 0 and abs(time[idx - 1] - t) < abs(time[idx] - t):
            idx -= 1
        return float(time[idx]), float(voltage[idx])

    def _update_readout(self, *_: object) -> None:
        src = self.chanbar.selected()
        if not 0 <= src < len(self._waveforms):  # 刪通道時通道列還沒重建
            return
        legacy, _ = self.markers.update(src)
        if not legacy:
            return
        first, offsets = self._waveforms[0], self.plot_widget.offsets
        dx0 = offsets[0][0]
        # 垂直游標吸附第一通道的取樣點。
        t1 = self._nearest(first.time, first.voltage, self.vline1.value() - dx0)[0] + dx0
        t2 = self._nearest(first.time, first.voltage, self.vline2.value() - dx0)[0] + dx0
        self.vline1.setValue(t1)
        self.vline2.setValue(t2)
        scale, pos, name = self.plot_widget.scales[src], offsets[src][1], self._waveforms[src].channel
        unit = self._units[name]
        v1, v2 = (self.hline1.value() - pos) * scale, (self.hline2.value() - pos) * scale
        channels = [(wf.channel, color, self._units[wf.channel], self._nearest(wf.time, wf.voltage, t1 - dx)[1],
                     self._nearest(wf.time, wf.voltage, t2 - dx)[1])
                    for wf, color, (dx, _) in zip(self._waveforms, self._colors, offsets)]
        self.results.set_cursor_values(t1, t2, v1, v2, unit, name, channels)

    # ---- 量測、FFT ----
    def _slice(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """量測範圍：游標區間（扣掉該通道的顯示平移）或全部，回傳原始資料的 view。"""
        wf = self._waveforms[i]
        if not self.toolbar.use_cursors():
            return wf.time, wf.voltage
        dx = self.plot_widget.offsets[i][0]
        lo, hi = sorted((self.vline1.value() - dx, self.vline2.value() - dx))
        a, b = np.searchsorted(wf.time, lo, "left"), np.searchsorted(wf.time, hi, "right")
        return wf.time[a:b], wf.voltage[a:b]

    def _source(self, name: str) -> tuple[np.ndarray, np.ndarray, str, str] | None:
        """量測／FFT 的資料來源：(範圍內時間, 數值, 單位, 顏色)；通道已不存在回傳 None。"""
        names = self._names()
        if name not in names:
            return None
        i = names.index(name)
        return (*self._slice(i), self._units[name], self._colors[i])

    def _range_changed(self, *_: object) -> None:
        self.runner.schedule()
        self.fft.refresh()

    def _add_measurement(self, name: str) -> None:
        i = self.chanbar.selected()
        if i >= 0:
            self.runner.add(name, self._waveforms[i].channel, self.measbar.rising())

    def _export_results(self) -> None:
        if self.runner.busy():
            QMessageBox.information(self, "匯出結果", "量測還在計算，完成後再匯出。")
            return
        span = (f"游標區間 t1={self.vline1.value()!r} s, t2={self.vline2.value()!r} s"
                if self.toolbar.use_cursors() else "全部")
        export_results(self, self.results, self._source_path,
                       [("量測範圍", span), ("閾值", self.toolbar.threshold.currentText())])

    # ---- 數學 ----
    def _open_math(self) -> None:
        job = run_math(self, self._waveforms, self._units, max(self.chanbar.selected(), 0),
                       lambda *res, g=self._gen: g == self._gen and self._add_derived(*res))
        if job is not None:
            job.finished.connect(lambda: self._jobs.discard(job))
            self._jobs.add(job)

    def _add_derived(self, t: np.ndarray, v: np.ndarray, unit: str) -> str:
        """衍生波形接在最後，不重載原始通道，游標與各通道顯示設定都保留。"""
        wf = Waveform(f"F{self._next_f}", t, v)
        self._next_f += 1
        color = _CHANNEL_COLORS[len(self._waveforms) % len(_CHANNEL_COLORS)]
        self._waveforms.append(wf)
        self._colors.append(color)
        self._units[wf.channel] = unit
        self.plot_widget.add_waveform(wf, color, unit)
        self._refresh_channels()
        return wf.channel


def _self_check() -> None:
    import time
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    tab = AnalysisTab()
    assert not tab.toolbar.math_action.isEnabled() and not tab.measbar.isEnabled()
    t = np.arange(5000) * 1e-6
    sq = np.interp(t % 1e-3, [0, 10e-6, 500e-6, 510e-6, 1e-3], [0, 2, 2, 0, 0])
    tab.load_waveforms([Waveform("CHAN1", t, sq), Waveform("CHAN2", t + 0.5e-6, np.sin(2e3 * np.pi * t))])
    tab.resize(1400, 900)
    tab.show()
    tab.toolbar.range.setCurrentIndex(1)
    tab.vline1.setValue(t[100] + 0.3e-6)
    tab._update_readout()
    assert tab.vline1.value() == t[100] and len(tab.chanbar.chips) == 2  # 游標吸附第一通道取樣點
    tab.measbar.buttons["頻率"].click()
    assert tab._add_derived(t, sq ** 2, "V²") == "F1" and tab.chanbar.chips[2].unit == "V²"
    assert len(tab.plot_widget.curves) == 3 and len(tab.export_bar._waveforms) == 2  # 衍生波形不匯出
    tab.chanbar.set_selected(2)
    tab._remove_channel(2)
    assert len(tab.plot_widget.curves) == 2 and tab.chanbar.selected() == 1
    assert tab._add_derived(t, sq, "V") == "F2"  # 刪掉的 F1 不重用
    tab._remove_channel(2)
    tab.toolbar.fft_action.setChecked(True)
    for _ in range(300):
        app.processEvents()
        time.sleep(0.01)
    assert tab.results.fft_table.rowCount() == 5 and tab.results.meas_table.item(0, 2).text() == "1 kHz"
    tab.load_waveforms([Waveform("CHAN1", np.arange(1_000_000) * 1e-6, np.zeros(1_000_000))])
    print("tab_analysis self-check OK")


if __name__ == "__main__":
    _self_check()
