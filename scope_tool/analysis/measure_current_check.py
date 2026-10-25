"""目前值選事件自檢：已知交越的非等週期波形，與事件時間標記。"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis import edge
from scope_tool.analysis.measure import MEASUREMENTS, measure, measure2, stats


def signal() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    t = np.arange(-25, 30, .01)
    starts = np.array([-22., -14., -3., 7., 20.])
    durations = np.array([.4, .6, .8, 1., 1.2])
    knots = np.column_stack((starts, starts+durations, starts+3, starts+4)).ravel()
    v = np.interp(t, knots, np.tile([0., 1., 1., 0.], 5))
    return t, v, starts+durations/2, starts+3.5


def _self_check() -> None:
    t, v, rise, fall = signal()
    for up in (True, False):
        for name in MEASUREMENTS:
            got = measure(name, t, v, rising=up)
            at = getattr(got, "at", None)
            if at is None:
                assert len(got) == 1
                assert stats(got, 0) == stats(got)
                continue
            mids = rise if up else fall
            if name.startswith("上升") or name == "+寬度":
                expected = rise
            elif name.startswith("下降") or name == "-寬度":
                expected = fall[:-1]
                if name.startswith("下降"):
                    expected = fall
            elif name == "前衝":
                expected = mids[1:] if up else mids
            elif name == "過衝":
                expected = mids if up else mids[:-1]
            else:
                expected = mids[:-1]
            assert np.allclose(at, expected), (name, up, at, expected)
            assert len(at) == len(got)
            # 時間跨 0，選第三事件；平移到全正後改用範圍中點。
            for offset in (0., 100.):
                shifted = measure(name, t+offset, v, rising=up)
                ref = 0. if offset == 0 else (t[0]+t[-1])/2+offset
                index = int(np.argmin(abs(expected+offset-ref)))
                assert stats(shifted, ref)[0] == shifted[index]
                assert stats(shifted, ref)[1:] == stats(shifted)[1:]
                assert stats(shifted)[0] == shifted[0]
    # 故意反序檢查同距選較早，並驗證無事件時間回退與上界選事件。
    tied = edge.timed(np.array([9., 3.]), [1., -1.])
    assert stats(tied, 0)[0] == 3 and stats(tied)[0] == 9
    assert stats(np.array([3., 1., 2.]), 0) == stats(np.array([3., 1., 2.]))
    bt = np.array([-10., -8., -7., -6., -5., -2., 0., 1., 2., 3., 4., 5.])
    bounded = measure("上升時間", bt, np.tile([0., 1., 1., 0.], 3))
    assert bounded.bound == "<" and np.allclose(bounded.at, [-9., -3.5, 2.5])
    assert stats(bounded, 0)[0] == 1 and stats(bounded)[0] == 2
    for name in ("延遲", "相位"):
        got = measure2(name, t, v, t+.1, v)
        assert np.allclose(got.at, rise if name == "延遲" else rise[:-1])
    print("analysis.measure_current self-check OK")


if __name__ == "__main__":
    _self_check()
