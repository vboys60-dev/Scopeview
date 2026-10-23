"""眼圖格（Infiniium Real-Time Eye）：單次擷取依還原時脈折疊成 2 UI 的色階圖，黑底。"""
from __future__ import annotations

import os

os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from typing import Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF

from scope_tool.analysis import eye, status as st
from scope_tool.analysis.clock import ClockSpec, recover
from scope_tool.ui.analysis_jitter import ClockPane, Provider
from scope_tool.ui.analysis_results import fmt


def _eye(t: np.ndarray, v: np.ndarray, pct: tuple, spec: ClockSpec) -> dict:
    ck = recover(t, v, pct, spec)
    counts, ylim = eye.density(t, v, ck)
    return {"clock": ck, "counts": counts, "ylim": ylim, "n_ui": float(t[-1] - t[0]) / ck.ui,
            "assessment": eye.assess("眼寬", t, v, ck)}


class EyePane(ClockPane):
    TITLE = "眼圖 "
    STATUS_LABEL = "眼寬狀態"
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
        d = res["assessment"].diagnostics
        limited = st.CROSSING_TRIMMED in res["assessment"].reasons
        label = "（受限：裁切 σ、6σ 估計與眼寬可能偏樂觀）" if limited else ""
        text += (f"｜原始 σ {fmt(d['raw_sigma'], 's')}｜實測 p-p {fmt(d['measured_pp'], 's')}"
                 f"｜裁切 σ {fmt(d['trimmed_sigma'], 's')}｜Jitter 6σ 估計 {fmt(d['six_sigma_estimate'], 's')}{label}"
                 f"｜資訊：剔除 {d['trimmed_count']} 點／{d['trimmed_fraction']:.2%}")
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
    assert "眼寬狀態 受限" in pane.status.text() and "時脈狀態 受限" in pane.status.text() and "未給定速率" in pane.warn.text()
    assert "實測 p-p" in pane.status.text() and "Jitter 6σ 估計" in pane.status.text()
    img = pane.image.image
    assert img is not None and img.shape == (400, 256) and "3,000 UI" in pane.status.text(), pane.status.text()
    assert img[200, 128] == 0 and img[100, 128] > 0  # 眼中心沒有中間電壓；交叉處（0 UI）有
    rect = pane.image.mapRectToParent(pane.image.boundingRect())
    assert abs(rect.left() + 0.5) < 1e-9 and abs(rect.width() - 2) < 1e-9 and "還原速率 1" in pane.status.text()
    res = _eye(t, v, (10, 50, 90), ClockSpec("NRZ 資料", mode="手動", rate=1e9))
    for fraction in (0.0099, 0.01, 0.0101):
        limited = fraction > 0.01
        res["assessment"] = res["assessment"]._replace(
            status=st.LIMITED if limited else st.VALID, reasons=(st.CROSSING_TRIMMED,) if limited else ())
        res["assessment"].diagnostics.update(trimmed_count=round(fraction * 10000), trimmed_fraction=fraction)
        pane._show("CHAN1", "V", "#ffcc00", res)
        assert f"眼寬狀態 {st.STATUS_TEXT[res['assessment'].status]}" in pane.status.text()
        assert "時脈狀態 有效" in pane.status.text() and pane.status.text().count("剔除") == 1
        assert ("裁切 σ、6σ 估計與眼寬可能偏樂觀" in pane.status.text()) == limited
        assert "資訊：剔除" in pane.status.text() and "剔除" not in pane.warn.text()
        assert "偏樂觀" not in pane.warn.text()  # 提示涵蓋裁切 σ、6σ 估計與眼寬。
    res["assessment"] = res["assessment"]._replace(status=st.INVALID, reasons=(st.EYE_NO_POSITIVE_OPENING,))
    pane._show("CHAN1", "V", "#ffcc00", res)
    assert "眼寬狀態 無效" in pane.status.text() and "時脈狀態 有效" in pane.status.text()
    pane.source.setCurrentIndex(1)
    wait()
    assert "振幅" in pane.status.text() and pane.image.image is None
    print("analysis_eye self-check OK")


if __name__ == "__main__":
    _self_check()
