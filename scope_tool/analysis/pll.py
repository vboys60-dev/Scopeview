"""二階 type-II PLL 事件層原型（草案：docs/archive/草案_Jitter與RMS.md.gz 案 B）。
輸入已知標稱速率 NRZ 的中閾值交越時間，逐轉態依實際 Δt 更新 (q, w)，回傳預更新 TIE。
頻寬 B＝恢復時脈 JTF 高頻側 −3 dB；預設 R/1667。鎖定／捕獲／失鎖門檻為待校準的產品門檻。
只做事件層：不接 GUI、眼圖與匯出；不處理時脈型。
"""
from __future__ import annotations

from collections import deque
from typing import NamedTuple

import numpy as np

from scope_tool.contracts import ScopeError

ZETA = 1 / np.sqrt(2)
_C = np.sqrt(1 + 2 * ZETA ** 2 + np.sqrt((1 + 2 * ZETA ** 2) ** 2 + 1))  # B = c·ωn/2π
BW_DIVISOR, BW_MAX_DIVISOR = 1667, 1000
MAX_GAP_UI = 32          # 無轉態超過此 UI 數才失鎖
SLIP_UI = 0.35           # 單緣 |殘差| 達此值視為配對疑慮
W_LIMIT = 1500e-6        # w 相對 R 的失鎖門檻（待校準）
LOCK_P95, LOCK_FDIFF, LOCK_MIN_EDGES = 0.1, 100e-6, 200
_EVAL_EVERY = 16


class Track(NamedTuple):
    times: np.ndarray
    n: np.ndarray        # 各邊緣的 UI 格號（失鎖時為重設後的新編號，段內連續）
    tie_all: np.ndarray  # 預更新 TIE（秒），含未鎖定資料；被排除或重設的邊緣為 NaN
    tie: np.ndarray      # 僅鎖定後有效邊緣，其餘 NaN
    valid: np.ndarray
    seg: np.ndarray      # 區段編號（每次重設 +1）
    w: np.ndarray        # 更新後絕對速率 UI/s
    ok: bool
    reason: str
    diag: dict


def omega_n(rate: float, bw: float | None = None) -> float:
    bw = rate / BW_DIVISOR if bw is None else bw
    if not (0 < bw <= rate / BW_MAX_DIVISOR):
        raise ScopeError(f"PLL 頻寬須 0 < B <= R/{BW_MAX_DIVISOR}")
    return 2 * np.pi * bw / _C


def _locked(win: deque) -> bool:
    a = np.array(win)
    if len(a) < LOCK_MIN_EDGES or np.percentile(a[:, 1], 95) >= LOCK_P95:
        return False
    q = len(a) // 4
    return abs(a[:q, 2].mean() - a[-q:, 2].mean()) / a[:, 2].mean() < LOCK_FDIFF


def track(times: np.ndarray, rate: float, bw: float | None = None) -> Track:
    t = np.asarray(times, dtype=np.float64)
    wn = omega_n(rate, bw)
    bw = rate / BW_DIVISOR if bw is None else bw
    kp, ki = 2 * ZETA * wn, wn * wn
    t_settle, t_win = 10 / (ZETA * wn), max(1024 / rate, 5 / bw)
    N = len(t)
    n_arr = np.zeros(N, np.int64)
    tie_all, tie = np.full(N, np.nan), np.full(N, np.nan)
    valid, seg, w_arr = np.zeros(N, bool), np.zeros(N, np.int64), np.full(N, np.nan)
    diag = dict(R=rate, B=bw, zeta=ZETA, wn=wn, t_settle=t_settle, t_win=t_win, model="euler-v1",
                excluded=0, relocks=0, long_gaps=0, segments=[])
    if N < 2 or not np.all(np.isfinite(t)):
        return Track(t, n_arr, tie_all, tie, valid, seg, w_arr, False, "PLL_NOT_LOCKED", diag)

    w, qi, qf, tp, sid, locked = rate, 0, 0.0, t[0], 0, False
    seg_t, win = t[0], deque()
    w_arr[0], ok, reason, stop = w, True, "", N

    def reset(k: int, x: float) -> None:   # 以目前事件重設相位／時間／鎖定窗，w 保留
        nonlocal qi, qf, tp, sid, locked, seg_t
        qi, qf, tp, locked, seg_t = qi + int(np.rint(x + qf)), 0.0, t[k], False, t[k]
        sid += 1
        diag["relocks"] += 1
        win.clear()

    for k in range(1, N):
        dt = t[k] - tp
        seg[k], w_arr[k] = sid, w
        if not dt > 0:
            reset(k, 0.0)
            n_arr[k] = qi
            continue
        x = w * dt
        if np.rint(x) > MAX_GAP_UI:   # 以四捨五入的 UI 數判定，32 UI 不因數值誤差失鎖
            diag["long_gaps"] += 1
            reset(k, x)
            n_arr[k] = qi
            continue
        xi = np.rint(x)
        qi += int(xi)
        qf += x - xi
        r = np.rint(qf)
        e = r - qf                       # n − q⁻，僅局部差值
        n_arr[k] = qi + int(r)
        tie_all[k] = -e / w
        if abs(e) >= SLIP_UI:
            diag["excluded"] += 1
            tie_all[k] = np.nan
            reset(k, 0.0)
            continue
        valid[k] = locked
        if locked:
            tie[k] = tie_all[k]
        qf += kp * dt * e
        w += ki * dt * e
        tp = t[k]
        c = np.rint(qf)                  # 小數部分維持有界
        qi, qf = qi + int(c), qf - c
        w_arr[k] = w
        if not np.isfinite(w) or abs(w / rate - 1) > W_LIMIT:
            ok, reason, stop = False, "PLL_FREQ_OUT_OF_RANGE", k + 1
            break
        if not locked and t[k] - seg_t >= t_settle:
            win.append((t[k], abs(e), w))
            while win[0][0] < t[k] - t_win:
                win.popleft()
            # ponytail: 每 16 緣重算一次窗統計，逐緣評估為 O(N·窗長)；要更快改增量分位數
            if t[k] - seg_t - t_settle >= t_win and k % _EVAL_EVERY == 0 and _locked(win):
                locked = True
    valid, tie = valid[:stop], tie[:stop]
    if ok and not valid.any():
        ok, reason = False, "PLL_NOT_LOCKED"
    diag["locked_fraction"] = float(valid.mean()) if stop else 0.0
    return Track(t[:stop], n_arr[:stop], tie_all[:stop], tie, valid, seg[:stop], w_arr[:stop], ok, reason, diag)


def transfer(f: float, wn: float) -> tuple[complex, complex]:
    """連續模型 JTF H 與殘餘 OJTF E=1−H 在頻率 f 的值。"""
    s = 2j * np.pi * f
    h = (2 * ZETA * wn * s + wn * wn) / (s * s + 2 * ZETA * wn * s + wn * wn)
    return h, 1 - h


if __name__ == "__main__":
    from scope_tool.analysis import pll_check
    pll_check.run()
