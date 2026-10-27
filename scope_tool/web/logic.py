from __future__ import annotations

"""協定中立的類比判位；缺值打斷遲滯前態。# 待真機驗證。"""
from typing import NamedTuple
import numpy as np
from scope_tool.analysis.measure import levels

HYST = 0.1
LEVEL_SAMPLES = 4_000_000
CHUNK = 1 << 22
MAX_EDGES = 10_000_000


class Edges(NamedTuple):
    time: np.ndarray
    value: np.ndarray
    resync: np.ndarray
    unknown: list[tuple[float, float]]
    min_run: int
    single_sample: int
    truncated: bool


def auto_threshold(v: np.ndarray) -> tuple[float, float] | None:
    """固定種子隨機抽樣只用於平台估計，不改變解碼樣本。"""
    a = v if len(v) <= LEVEL_SAMPLES else v[np.random.default_rng(0).choice(len(v), LEVEL_SAMPLES)]
    a = a[np.isfinite(a)]
    if not len(a):
        return None
    _, _, top, base = levels(a)
    if top <= base:
        return None
    mid, half = (top + base) / 2, HYST * (top - base)
    return mid - half, mid + half


def validate_time(t: np.ndarray, other: np.ndarray | None = None) -> None:
    """完整驗證共同時間軸；由 P2 轉成 BAD_REQUEST。"""
    if t.ndim != 1 or len(t) < 2:
        raise ValueError('時間軸至少兩點且須一維')
    if other is not None and not np.array_equal(t, other):
        raise ValueError('兩通道時間軸不一致')
    for start in range(0, len(t), CHUNK):
        a = t[max(0, start - 1):start + CHUNK]
        if not np.all(np.isfinite(a)) or np.any(a[1:] <= a[:-1]):
            raise ValueError('時間軸須有限且嚴格遞增')


def to_edges(t: np.ndarray, v: np.ndarray, lo: float, hi: float,
             *, chunk: int = CHUNK, max_edges: int = MAX_EDGES) -> Edges:
    """分塊 forward-fill，不配置整條波形長度的 int64 暫存。"""
    if v.ndim != 1 or len(v) != len(t) or not np.isfinite([lo, hi]).all() or lo >= hi:
        raise ValueError('電壓長度或門檻不合法')
    if chunk < 1 or max_edges < 1:
        raise ValueError('分塊與邊沿上限須為正整數')
    times, values, syncs, indices = [], [], [], []
    prev, count, truncated = -1, 0, False
    for start in range(0, len(v), chunk):
        a = v[start:start + chunk]
        finite = np.isfinite(a)
        raw = np.full(len(a) + 1, -2, dtype=np.int8)
        raw[0] = prev
        raw[1:][a >= hi] = 1
        raw[1:][a <= lo] = 0
        raw[1:][~finite] = -1
        pos = np.maximum.accumulate(np.where(raw != -2, np.arange(len(raw)), 0))
        state = raw[pos]
        loc = np.flatnonzero(state[1:] != state[:-1])
        # 首值也保存為 resync，絕不當作真正邊沿。
        if start == 0 and state[1] >= 0 and (not len(loc) or loc[0] != 0):
            loc = np.r_[0, loc]
        if count + len(loc) > max_edges:
            loc = loc[:max_edges - count]
            truncated = True
        ix = loc + start
        val = state[loc + 1]
        old = state[loc]
        et = t[ix].astype(float, copy=True)
        real = (ix > 0) & (val >= 0) & (old >= 0)
        j = ix[real]
        threshold = np.where(val[real] == 1, hi, lo)
        et[real] = t[j - 1] + (t[j] - t[j - 1]) * (threshold - v[j - 1]) / (v[j] - v[j - 1])
        times.append(et)
        values.append(val)
        syncs.append((old < 0) & (val >= 0))
        indices.append(ix)
        count += len(loc)
        prev = int(state[-1])
        if truncated:
            break
    ts = np.concatenate(times) if times else np.array([], dtype=float)
    vs = np.concatenate(values) if values else np.array([], dtype=np.int8)
    rs = np.concatenate(syncs) if syncs else np.array([], dtype=bool)
    ix = np.concatenate(indices) if indices else np.array([], dtype=int)
    end = float(ts[-1]) if truncated else float(t[-1])
    unknown, begin = [], float(t[0])
    known = False
    for tm, val in zip(ts, vs):
        if val < 0 and known:
            begin, known = float(tm), False
        elif val >= 0 and not known:
            if tm > begin:
                unknown.append((begin, float(tm)))
            known = True
    if not known and end > begin:
        unknown.append((begin, end))
    runs = np.diff(ix)
    # 不將檔頭／檔尾未完整擷取的脈衝當最短穩定段。
    runs = runs[(vs[:-1] >= 0) & (vs[1:] >= 0)]
    return Edges(ts, vs, rs, unknown, int(runs.min()) if len(runs) else 0,
                 int(np.count_nonzero(runs == 1)), truncated)


MAX_FRAMES = 100_000
MAX_FIELDS = 100_000


def levels_at(e: Edges, t: np.ndarray, end: float) -> np.ndarray:
    """最後一個不晚於取樣時間的狀態；有效截止點外一律未知。"""
    ix = np.searchsorted(e.time, t, side='right') - 1
    out = np.full(np.shape(t), -1, dtype=np.int8)
    good = (ix >= 0) & (t <= end)
    out[good] = e.value[ix[good]]
    return out


def prepare(t: np.ndarray, volts: dict, thresholds: dict, *, require_edges: bool,
            max_edges: int = MAX_EDGES) -> tuple[dict, dict, float, str | None]:
    """共同判位與截止點；警告由各協定核心加入一次。"""
    validate_time(t)
    used = {r: auto_threshold(v) if thresholds[r] is None else tuple(thresholds[r]) for r, v in volts.items()}
    edges, end = {}, float(t[-1])
    for role, v in volts.items():
        th = used[role]
        if th is None:
            return edges, used, end, f'{role.upper()} 無有限高低平台'+('' if require_edges else '；請改用手動門檻')
        e = to_edges(t, v, *th, max_edges=max_edges)
        edges[role] = e
        if require_edges and not np.any((e.value >= 0) & ~e.resync):
            return edges, used, end, f'{role.upper()} 無轉態（門檻 {th}）'
        if not require_edges and not np.any(e.value >= 0):
            return edges, used, end, f'{role.upper()} 全段未定'
        if e.truncated:
            end = min(end, float(e.time[-1]))
    return edges, used, end, None


if __name__ == '__main__':
    t = np.arange(10, dtype=float)
    v = np.array([.5, 0, .5, 1, .5, np.nan, .5, 1, 0, 0])
    e = to_edges(t, v, .3, .7, chunk=3)
    assert e.value.tolist() == [0, 1, -1, 1, 0]
    assert e.resync.tolist() == [True, False, False, True, False]
    assert e.unknown == [(0., 1.), (5., 7.)]
    assert np.allclose(e.time, to_edges(t, v, .3, .7, chunk=100).time)
    assert auto_threshold(np.ones(20)) is None
    assert levels_at(e, np.array([0., 1., 11.]), 10).tolist() == [-1, 0, -1]
    assert prepare(t, {'a': np.ones(10)}, {'a': [.3, .7]}, require_edges=False)[3] is None
    assert prepare(t, {'a': np.ones(10)}, {'a': None}, require_edges=False)[3] == 'A 無有限高低平台；請改用手動門檻'
    assert prepare(t, {'a': np.full(10, .5)}, {'a': [.3, .7]}, require_edges=False)[3] == 'A 全段未定'
    print('web.logic self-check OK')
