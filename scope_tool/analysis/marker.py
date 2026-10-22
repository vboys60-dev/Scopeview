"""Marker 純數值運算，依 dlg_MarkerSetup、GS_Markers、Marker_Results。

手冊未載明吸附與同距點規則：本工具取最近資料點，同距取右點。待真機驗證。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MODES = ("Manual X only", "Manual Y only", "Manual X and Y",
         "Track Waveforms", "Track Measurements")
DELTA_TO = (("X1", "X2"), ("X2", "X1"), ("Y1", "Y2"), ("Y2", "Y1"))


@dataclass(frozen=True)
class Position:
    x1: float | None = None
    x2: float | None = None
    y1: float | None = None
    y2: float | None = None


@dataclass(frozen=True)
class Source:
    t: np.ndarray
    v: np.ndarray


@dataclass(frozen=True)
class MarkerResult:
    position: Position
    available: bool = True
    reason: str = ""
    read_only: bool = False
    points: tuple[tuple[float, float, str], ...] = ()
    versus: bool = False
    delta_to: tuple[tuple[str, str], ...] = DELTA_TO

    @property
    def delta_x(self) -> float | None:
        p = self.position
        return None if p.x1 is None or p.x2 is None else p.x2 - p.x1

    @property
    def inverse_delta_x(self) -> float | None:
        d = self.delta_x
        return None if self.versus or d is None or d == 0 else 1 / d

    @property
    def delta_y(self) -> float | None:
        p = self.position
        return None if p.y1 is None or p.y2 is None else p.y2 - p.y1

    @property
    def fields(self) -> dict[str, float | None]:
        return {"ΔX": self.delta_x, "1/ΔX": self.inverse_delta_x, "ΔY": self.delta_y}


def evaluate(mode: str, position: Position = Position(), source: Source | None = None, *,
             digital: bool = False, screen_width: float = 0.0, trigger_t: float = 0.0,
             measurements: list[tuple[float, float, str]] | None = None,
             versus: bool = False, peak_level: float = -np.inf,
             direction: int = 0) -> MarkerResult:
    """傳入來源座標；Manual 保留使用者位置，不量化也不吸附。

    measurements 是呼叫端提供的「最近新增量測」位置，順序照輸入；前兩點形成差值。
    手冊未載明多點量測的配對方式，本工具保留全部位置供顯示，不推導量測位置。
    手冊未載明 ΔX 的符號規則；本工具一律 X2−X1，不排序，負號保留。
    數位來源的 Manual Y only／X and Y 整組不可用是本工具取捨；
    手冊只說 Y markers will not be displayed，未要求連 X 也隱藏。
    """
    if mode == "Track RF":
        if source is None:
            return MarkerResult(Position(), False, "尚未提供 FFT 來源", versus=True)
        if position.x1 is None or not np.isfinite(position.x1):
            return MarkerResult(Position(), False, "尚未提供有限的 Track RF 位置", versus=True)
        return track_rf(source.t, source.v, position.x1, level=peak_level, direction=direction)
    if mode not in MODES:
        raise ValueError(f"未知 Marker 模式：{mode}")
    if digital and mode in MODES[1:3]:
        return MarkerResult(Position(), False, "數位來源不支援 Manual Y only／X and Y", versus=versus)
    if mode == "Track Measurements":
        points = tuple((float(x), float(y), str(label)) for x, y, label in (measurements or []))
        points = tuple(point for point in points if np.isfinite(point[:2]).all())
        p = Position(points[0][0] if points else None, points[1][0] if len(points) > 1 else None,
                     points[0][1] if points else None, points[1][1] if len(points) > 1 else None)
        return MarkerResult(p, read_only=True, points=points, versus=versus)
    active = ((position.x1, position.x2) if mode == MODES[0] else
              (position.y1, position.y2) if mode == MODES[1] else
              (position.x1, position.x2) if mode == MODES[3] else
              (position.x1, position.x2, position.y1, position.y2))
    if any(value is None or not np.isfinite(value) for value in active):
        raise ValueError("作用中的 Marker 位置必須是有限值")
    if mode.startswith("Manual"):
        p = (Position(position.x1, position.x2) if mode == MODES[0] else
             Position(y1=position.y1, y2=position.y2) if mode == MODES[1] else position)
        return MarkerResult(p, versus=versus)
    if not np.isfinite(screen_width) or screen_width < 0 or not np.isfinite(trigger_t):
        raise ValueError("螢幕寬必須非負，觸發點必須是有限值")
    if source is None:
        return MarkerResult(Position(), False, "尚未提供來源波形", versus=versus)
    t, v = np.asarray(source.t), np.asarray(source.v)
    if t.ndim != 1 or v.ndim != 1 or len(t) != len(v):
        raise ValueError("來源時間與數值必須是等長一維陣列")
    if not np.isfinite(t).all() or np.any(np.diff(t) < 0):
        return MarkerResult(Position(), False, "來源時間必須有限且非遞減（可非等距）", versus=versus)
    radius = max(1.0, screen_width)
    lo, hi = trigger_t - radius, trigger_t + radius
    a, b = np.searchsorted(t, lo, side="left"), np.searchsorted(t, hi, side="right")
    if a == b:
        return MarkerResult(Position(), False, "允許範圍內沒有資料點", versus=versus)

    def snap(x: float) -> tuple[float, float]:
        i = int(np.clip(np.searchsorted(t, x), a, b - 1))
        if i > a and abs(t[i - 1] - x) < abs(t[i] - x):
            i -= 1
        return float(t[i]), float(v[i])

    x1, y1 = snap(position.x1)
    x2, y2 = snap(position.x2)
    return MarkerResult(Position(x1, x2, y1, y2), versus=versus)


# Track RF 獨立掛於 FFT 格，時間域工具列仍維持原五種模式。
RF_MODE = "Track RF"


def track_rf(freq: np.ndarray, mag: np.ndarray, x: float, *, level: float = -np.inf,
             direction: int = 0) -> MarkerResult:
    """FFT 上讀取最近頻格，或跳至左／右下一個高於 Peak Level 的局部峰。

    手冊未載明吸附與邊界規則；本工具同距取右格，無下一峰回不可用且保留位置，
    不環繞、不套主瓣略過範圍；左右跳峰使用原始頻格，不使用峰值表頻率內插。
    UI 暫與峰值表共用 Peak Level；手冊 Add Marker 的 RF 有自己的 Peak Level。
    等於門檻是否列峰手冊未載明，本工具採嚴格大於。整條等值譜不算峰，
    DC 有實際下降時仍可為端點峰；以上均待真機比對。
    """
    from scope_tool.analysis.peaks import SORTS, peaks

    f, y = np.asarray(freq), np.asarray(mag)
    if direction not in (-1, 0, 1) or not np.isfinite(x):
        raise ValueError("Track RF 位置與方向無效")
    if f.ndim != 1 or y.shape != f.shape or not np.isfinite(f).all() or not np.isfinite(y).all():
        raise ValueError("Track RF 來源必須為等長有限一維陣列")
    if np.any(np.diff(f) <= 0) or np.isnan(level):
        raise ValueError("Track RF 頻率或門檻無效")
    if not len(f):
        return MarkerResult(Position(), False, "尚未提供 FFT 來源", versus=True)
    i = min(int(np.searchsorted(f, x)), len(f) - 1)
    if i > 0 and abs(f[i - 1] - x) < abs(f[i] - x):
        i -= 1
    if direction:
        candidates = peaks(f, y, len(f), start=0, level=level, sort=SORTS[1])
        eligible = [(a, b) for a, b in candidates if (a - x) * direction > 0]
        if not eligible:
            return MarkerResult(Position(float(f[i]), y1=float(y[i])), False, "該方向沒有高於門檻的峰", versus=True)
        a, b = eligible[0] if direction > 0 else eligible[-1]
    else:
        a, b = float(f[i]), float(y[i])
    return MarkerResult(Position(a, y1=b), points=((a, b, RF_MODE),), versus=True)


def _self_check() -> None:
    from dataclasses import FrozenInstanceError

    t = np.array([-3., -1., -0.2, 0., 0.3, 0.9, 1., 3.])
    source = Source(t, 2 * t + 1)
    r = evaluate(MODES[3], Position(-0.18, 0.85), source)
    assert r.position == Position(-0.2, 0.9, 0.6, 2.8)
    assert np.allclose(list(r.fields.values()), [1.1, 1 / 1.1, 2.2])
    assert r.delta_to == DELTA_TO and dict(r.delta_to)["X2"] == "X1"
    r = evaluate(MODES[3], Position(-99, 99), source)
    assert r.position == Position(-1., 1., -1., 3.)
    r = evaluate(MODES[3], Position(-99, 99), source, screen_width=3)
    assert r.position.x1 == -3 and r.position.x2 == 3  # 螢幕外仍計算差值
    r = evaluate(MODES[3], Position(-99, 99), source, trigger_t=2)
    assert r.position.x1 == 1 and r.position.x2 == 3
    r = evaluate(MODES[3], Position(0.9, -0.2), source)
    assert r.delta_x < 0 and np.isclose(r.inverse_delta_x, -1 / 1.1)
    assert evaluate(MODES[0], Position(0, 0)).inverse_delta_x is None
    assert evaluate(MODES[0], Position(0, 1), versus=True).inverse_delta_x is None
    p = Position(0.123456, -0.456789, 1.234567, -2.345678)
    assert evaluate(MODES[2], p).position == p  # Manual 不吸附取樣點
    assert evaluate(MODES[0], p).position.y1 is None
    assert evaluate(MODES[1], p).delta_x is None
    for mode in MODES[1:3]:
        assert not evaluate(mode, p, digital=True).available
    assert evaluate(MODES[0], p, digital=True).available
    assert not evaluate(MODES[4]).points and evaluate(MODES[4]).read_only
    r = evaluate(MODES[4], measurements=[(0, 1, "起點"), (2, 4, "終點"), (3, 5, "其他")])
    assert r.position == Position(0, 2, 1, 4) and r.delta_y == 3 and len(r.points) == 3
    try:
        r.position = p
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("追蹤量測結果應為唯讀")
    assert not evaluate(MODES[3], p, Source(np.array([9.]), np.array([1.]))).available
    assert not evaluate(MODES[3], p, Source(np.array([]), np.array([]))).available
    assert evaluate(MODES[3], Position(0.15, 0.15), source).position.x1 == 0.3
    # 窗內只有一點；兩側窗外鄰點即使較近，也不得吸附。
    r = evaluate(MODES[3], Position(-99, 99), Source(np.array([-1.1, 0.5, 1.05]), np.zeros(3)))
    assert r.position == Position(0.5, 0.5, 0., 0.)
    r = evaluate(MODES[3], Position(0.1, 0.8), Source(np.array([0., 0., 1.]), np.array([2., 2., 3.])))
    assert r.available and r.position == Position(0., 1., 2., 3.)
    for times in ([0., 1., 0.5], [0., np.nan, 1.]):
        r = evaluate(MODES[3], Position(0, 1), Source(np.array(times), np.zeros(3)))
        assert not r.available and r.reason and r.position == Position()
    r = evaluate(MODES[4], measurements=[(np.nan, 1, "無效 X"), (0, 1, "起點"),
                 (1, np.inf, "無效 Y"), (-np.inf, 2, "無效 X"), (2, 4, "終點"), (3, np.nan, "無效 Y")])
    assert r.points == ((0., 1., "起點"), (2., 4., "終點")) and r.position == Position(0, 2, 1, 4)
    f, y = np.arange(9.), np.array([0., 3., 0., 5., 0., 2., 0., 4., 0.])
    assert track_rf(f, y, 2.5).position == Position(3., y1=5.)
    assert track_rf(f, y, 3, level=2, direction=1).position == Position(7., y1=4.)
    assert track_rf(f, y, 7, level=2, direction=-1).position == Position(3., y1=5.)
    assert not track_rf(f, y, 7, level=2, direction=1).available
    assert not track_rf(np.array([]), np.array([]), 0).available
    assert evaluate(RF_MODE, Position(3), Source(f, y), peak_level=2, direction=1).position.x1 == 7
    assert track_rf(f, y, 2).position.y1 == 0  # 一般追蹤不受 Peak Level 限制
    r = evaluate(RF_MODE, Position(), Source(f, y))
    assert not r.available and r.reason and r.versus and r.position == Position()
    # RF 為頻率／振幅座標，成功及各種不可用結果皆維持 versus。
    for r in (track_rf(f, y, 3), track_rf(f, y, 7, direction=1),
              track_rf(np.array([]), np.array([]), 0), evaluate(RF_MODE)):
        assert r.versus and r.inverse_delta_x is None
    r = track_rf(f, np.zeros(len(f)), 3, direction=-1)
    assert not r.available and r.reason and r.position.x1 == 3 and r.versus
    # 有下降的 DC 仍可跳入；等值譜才不可把 DC 當峰，端點規則不變。
    r = track_rf(np.arange(3.), np.array([3., 0., 2.]), 1, direction=-1)
    assert r.available and r.position.x1 == 0 and r.versus
    print("marker self-check OK")


if __name__ == "__main__":
    _self_check()
