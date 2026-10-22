"""量測清單的背景計算：來源通道與邊緣方向在加入時固定；過期的結果丟棄。"""
from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from typing import Callable

import numpy as np
from PySide6.QtCore import QObject, QTimer

from scope_tool.analysis.measure import SLOPED, measure_all, unit_of
from scope_tool.ui.analysis_results import ResultsPane
from scope_tool.ui.worker import Job

# source(通道名) -> (時間, 數值, 單位, 顏色)，範圍已由分析頁切好；通道不存在回傳 None。
Source = Callable[[str], "tuple[np.ndarray, np.ndarray, str, str] | None"]


class MeasureRunner(QObject):
    def __init__(self, results: ResultsPane, source: Source, pct: Callable[[], tuple]) -> None:
        super().__init__(results)
        self.entries: list[tuple[str, str, bool]] = []  # (量測, 來源通道名, 上升緣)
        self._results, self._source, self._pct = results, source, pct
        self._seq = self._done_seq = 0
        self._jobs: set[Job] = set()
        self._timer = QTimer(self, singleShot=True, interval=150)
        self._timer.timeout.connect(self.run)
        results.remove_requested.connect(lambda r: (self.entries.pop(r), self.run()))
        results.clear_requested.connect(lambda: (self.entries.clear(), self.run()))

    def add(self, name: str, channel: str, rising: bool) -> None:
        self.entries.append((name, channel, rising))
        self.run()

    def schedule(self) -> None:
        """防抖：游標拖曳時停下 150 ms 才重算；序號先加、表上先顯示「…」，舊值與舊結果都不留。"""
        self._seq += 1
        self._timer.start()
        self._results.set_measurements(*self._pending()[:2])

    def busy(self) -> bool:
        """還有等待中或計算中的結果（表上是舊值或「…」），不能匯出。"""
        return self._timer.isActive() or self._done_seq != self._seq

    def _pending(self) -> tuple[list, list, list, list]:
        """(列〔結果 None＝計算中〕, 顏色, 背景工作, 工作對應的列號)。"""
        rows, colors, tasks, slots = [], [], [], []
        for k, (name, ch, rising) in enumerate(self.entries):
            src = self._source(ch)
            arrow = (" ↑" if rising else " ↓") if name in SLOPED else ""
            rows.append([f"{name}({ch}{arrow})", unit_of(name, src[2] if src else "V"),
                         None if src else "來源通道已刪除"])
            colors.append(src[3] if src else None)
            if src:
                tasks.append((name, src[0], src[1], rising))
                slots.append(k)
        return rows, colors, tasks, slots

    def run(self) -> None:
        self._timer.stop()  # 立即重算取代待執行的防抖，否則計時器到期會再算一次
        self._seq += 1
        seq = self._seq
        rows, colors, tasks, slots = self._pending()
        self._results.set_measurements(rows, colors)  # 先顯示「…」，舊值不留在表上
        if not tasks:
            self._done_seq = seq
            return

        def done(res: list) -> None:
            if seq == self._seq:
                self._done_seq = seq
                for k, r in zip(slots, res):
                    rows[k][2] = r
                self._results.set_measurements(rows, colors)

        job = Job(measure_all, tasks, self._pct())
        job.done.connect(done)
        job.failed.connect(lambda msg: done([msg] * len(slots)))
        job.finished.connect(lambda j=job: self._jobs.discard(j))
        self._jobs.add(job)
        job.start()


def _self_check() -> None:
    import time
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    pane = ResultsPane()
    t = np.arange(5000) * 1e-6
    sq = np.interp(t % 1e-3, [0, 10e-6, 500e-6, 510e-6, 1e-3], [0, 2, 2, 0, 0])
    data = {"CHAN1": (t, sq, "V", "#ffcc00")}
    jobs: list[int] = []  # pct() 每啟動一個背景工作呼叫一次，用來數工作次數
    runner = MeasureRunner(pane, data.get, lambda: jobs.append(1) or (10, 50, 90))

    def wait() -> None:
        for _ in range(100):
            app.processEvents()
            if not runner._jobs and not runner._timer.isActive():
                return
            time.sleep(0.02)

    runner.add("頻率", "CHAN1", True)
    runner.add("Vmax", "F9", True)
    assert pane.meas_table.item(0, 1).text() == "…" and pane.meas_table.item(1, 1).text() == "—"
    wait()
    assert pane.meas_table.item(0, 0).text() == "頻率(CHAN1 ↑)" and pane.meas_table.item(0, 2).text() == "1 kHz"
    assert pane.meas_table.item(1, 1).toolTip() == "來源通道已刪除"
    pane.remove_requested.emit(1)
    wait()
    assert runner.entries == [("頻率", "CHAN1", True)] and pane.meas_table.rowCount() == 1
    runner.schedule()
    assert runner.busy() and pane.meas_table.item(0, 2).text() == "…"  # 防抖等待中也不留舊值
    n_jobs = len(jobs)
    runner.run()
    assert runner.busy() and pane.meas_table.item(0, 2).text() == "…"  # 重算中不留舊值
    wait()
    time.sleep(0.2)  # 超過防抖 150 ms：被取代的計時器不得再跑一次
    app.processEvents()
    assert not runner.busy() and len(jobs) == n_jobs + 1
    # 防抖等待期間，舊工作回來也不會蓋上去
    data["CHAN1"] = (t, np.ones_like(t), "V", "#ffcc00")
    runner.run()  # 舊工作：沒有振幅 → 失敗
    data["CHAN1"] = (t, sq, "V", "#ffcc00")
    runner.schedule()
    runner._jobs and next(iter(runner._jobs)).wait()
    app.processEvents()
    assert runner._timer.isActive() and pane.meas_table.item(0, 2).text() == "…"  # 舊工作的失敗沒有填上
    wait()
    assert pane.meas_table.item(0, 2).text() == "1 kHz"
    data["CHAN1"] = (t, np.ones_like(t), "V", "#ffcc00")
    runner.schedule()
    wait()
    assert "振幅" in pane.meas_table.item(0, 1).toolTip()
    pane.clear_requested.emit()
    wait()
    assert not runner.entries and pane.meas_table.rowCount() == 0
    print("analysis_runner self-check OK")


if __name__ == "__main__":
    _self_check()
