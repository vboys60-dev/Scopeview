"""眼圖格（Infiniium Real-Time Eye）：單次擷取依還原時脈折疊成 2 UI 的色階圖，黑底。"""
from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from typing import Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF

from scope_tool.analysis import eye
from scope_tool.analysis.clock import ClockSpec, recover
from scope_tool.ui.analysis_jitter import ClockPane, Provider


def _eye(t: np.ndarray, v: np.ndarray, pct: tuple, spec: ClockSpec) -> dict:
    ck = recover(t, v, pct, spec)
    counts, ylim = eye.density(t, v, ck)
    return {"clock": ck, "counts": counts, "ylim": ylim, "n_ui": float(t[-1] - t[0]) / ck.ui,
            "kept": eye.crossing(ck)[2]}


class EyePane(ClockPane):
    TITLE = "眼圖 "
    compute = staticmethod(_eye)

    def __init__(self, provider: Provider, spec: Callable[[], ClockSpec],
                 pct: Callable[[], tuple[float, float, float]]) -> None:
        super().__init__(provider, spec, pct)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "UI")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.image = pg.ImageItem()
        self.image.setColorMap(pg.colormap.get("inferno"))  # 0 次＝黑
        self.plot.addItem(self.image)
        self.plot.setXRange(*eye.X_RANGE, padding=0)
        self.body.addWidget(self.plot)

    def summary(self, res: dict) -> str:
        text = f"{res['n_ui']:,.0f} UI｜色階＝樣本密度（相鄰取樣線性補點只供顯示，量測用原始取樣）"
        if res["kept"] < 0.95:
            text += f"｜交叉點只保留 {res['kept']:.0%}（有離群或多峰，眼 Jitter／眼寬偏樂觀）"
        return text

    def draw(self, res: dict, unit: str, color: str) -> None:
        lo, hi = res["ylim"]
        self.image.setImage(np.log1p(res["counts"]), autoLevels=True)  # 取對數，稀疏的軌跡才看得到
        self.image.setRect(QRectF(eye.X_RANGE[0], lo, eye.X_RANGE[1] - eye.X_RANGE[0], hi - lo))
        self.plot.setLabel("left", "", units=unit)
        self.plot.setRange(xRange=eye.X_RANGE, yRange=(lo, hi), padding=0)

    def clear(self) -> None:
        self.image.clear()


def _self_check() -> None:
    import time
    from PySide6.QtWidgets import QApplication

    from scope_tool.analysis.clock import nrz

    app = QApplication.instance() or QApplication([])
    rng = np.random.default_rng(5)
    bits = rng.integers(0, 2, 3000)
    bits[:3] = (0, 1, 0)
    t, v = nrz(bits, 1e-9, 16, rise=4, jitter=rng.normal(0, 5e-12, 3001))
    data = {"CHAN1": (t, v, "V", "#ffcc00"), "CHAN2": (t[:10], v[:10], "V", "#00d0ff")}
    pane = EyePane(data.get, lambda: ClockSpec("NRZ 資料"), lambda: (10, 50, 90))
    pane.resize(600, 400)
    pane.show()
    pane.set_sources(["CHAN1", "CHAN2"])

    def wait() -> None:
        for _ in range(300):
            app.processEvents()
            if not pane._jobs and not pane._timer.isActive():
                return
            time.sleep(0.01)

    wait()
    img = pane.image.image
    assert img is not None and img.shape == (400, 256) and "3,000 UI" in pane.status.text(), pane.status.text()
    assert img[200, 128] == 0 and img[100, 128] > 0  # 眼中心沒有中間電壓；交叉處（0 UI）有
    rect = pane.image.mapRectToParent(pane.image.boundingRect())
    assert abs(rect.left() + 0.5) < 1e-9 and abs(rect.width() - 2) < 1e-9 and "還原速率 1" in pane.status.text()
    pane.source.setCurrentIndex(1)
    wait()
    assert "振幅" in pane.status.text() and pane.image.image is None
    print("analysis_eye self-check OK")


if __name__ == "__main__":
    _self_check()
