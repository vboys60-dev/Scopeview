"""分析服務（契約 owner=Analysis）：開檔、量測、游標、Marker、數學、FFT、Track RF、匯出。

純 numpy／分析層呼叫，不碰 driver、不拿儀器鎖。工作型方法（契約 job=true）為
同步函式直接回傳結果；由 server 依契約 job 旗標包成 job。
世代 gen：每次開檔 +1，舊檔工作結果一律以 STALE 丟棄；revision：每次 measure 提出時配號，
export_measurements 只認「最新已完成」的快照。
/wave、/fft 的二進位由模組函式 wave_bytes／fft_bytes（第一參數為 Analysis）提供。
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import threading
from pathlib import Path
from typing import Any

import numpy as np

from scope_tool.analysis import fft as fftmod
from scope_tool.analysis import marker as markermod
from scope_tool.analysis import mathfn
from scope_tool.analysis.measure import MEASUREMENTS, SLOPED, THRESHOLDS, measure as _measure, stats as _stats, unit_of
from scope_tool.analysis.peaks import SORTS
from scope_tool.contracts import ScopeError, Waveform
from scope_tool.storage import csv_export
from scope_tool.storage.reader import read_file_info, read_waveform_file
from scope_tool.storage.writer import timestamped
from scope_tool.web import decimate

try:  # L1a 已提供則共用同一組例外類別，server 才能映射錯誤碼
    from scope_tool.web.jobs import BadRequestError as BadRequest, StaleError
except ImportError:  # pragma: no cover  最小 stub：與 jobs.py 同名同語義（待 jobs.py 就緒）
    class BadRequest(ValueError):
        """參數錯誤（BAD_REQUEST）。"""

    class StaleError(Exception):
        """gen／revision／spectrum_id 過期（STALE）。"""
        code = "STALE"


def _clean(o: Any) -> Any:
    """NaN／Infinity → None，numpy → 原生型別（契約：JSON 不得出現 NaN）。"""
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(o) else None
    if isinstance(o, (str, bool, int)) or o is None:
        return o
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return str(o)


def _si(v: float, unit: str) -> str:
    if not math.isfinite(v) or v == 0:
        return f"{v:g} {unit}"
    for p, s in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")):
        if abs(v) >= p:
            return f"{v / p:.6g} {s}{unit}"
    return f"{v:.6g} {unit}"


def _range(r: Any) -> tuple[float, float] | None:
    if r is None:
        return None
    if not (isinstance(r, (list, tuple)) and len(r) == 2 and all(
            isinstance(x, (int, float)) and math.isfinite(x) for x in r)):
        raise BadRequest("range 必須是 [t0,t1] 或 null")
    return (float(min(r)), float(max(r)))  # 反序由後端排序


def _dx(dx: Any) -> dict[str, float]:
    if not isinstance(dx, dict) or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in dx.values()):
        raise BadRequest("dx 必須是 {通道名: 秒}")
    return {str(k): float(v) for k, v in dx.items()}


def _nearest(t: np.ndarray, x: float) -> int:
    i = min(max(int(np.searchsorted(t, x)), 0), len(t) - 1)
    return i - 1 if i > 0 and abs(t[i - 1] - x) < abs(t[i] - x) else i  # 同距取右


class Analysis:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._gen = 0
        self._rev = 0          # 已配出的最大 revision
        self._reset(None)

    # ---------------------------------------------------------------- 內部狀態
    def _reset(self, path: Path | None) -> None:
        self._path, self._waves, self._units, self._n_raw = path, [], {}, 0
        self._next_f, self._pyr, self._spec, self._snap = 1, {}, None, None
        self._spec_no = 0

    def _need(self) -> tuple[int, list[Waveform], dict[str, str]]:
        with self._lock:
            if not self._gen or not self._waves:
                raise ScopeError("尚未開啟波形檔")
            return self._gen, list(self._waves), dict(self._units)

    def _alive(self, gen: int) -> None:
        if gen != self._gen:
            raise StaleError("開檔世代已變更")

    def _wf(self, waves: list[Waveform], name: str) -> Waveform:
        for w in waves:
            if w.channel == name:
                return w
        raise BadRequest(f"通道不存在：{name}")

    @staticmethod
    def _cut(w: Waveform, rng: tuple[float, float] | None, dx: dict[str, float]):
        """顯示時間範圍 → 該通道來源資料（view）。先扣自己的 dx，兩端含。"""
        if rng is None:
            return w.time, w.voltage
        d = dx.get(w.channel, 0.0)
        a = int(np.searchsorted(w.time, rng[0] - d, "left"))
        b = int(np.searchsorted(w.time, rng[1] - d, "right"))
        return w.time[a:b], w.voltage[a:b]

    def _info(self, w: Waveform, units: dict[str, str], gen: int) -> dict:
        v = w.voltage[np.isfinite(w.voltage)]
        return {"name": w.channel, "unit": units[w.channel], "derived": w.channel not in self._raw_names(),
                "points": len(w.time), "t0": float(w.time[0]), "t1": float(w.time[-1]),
                "vmin": float(v.min()) if len(v) else None, "vmax": float(v.max()) if len(v) else None, "gen": gen}

    def _raw_names(self) -> set[str]:
        return {w.channel for w in self._waves[:self._n_raw]}

    # ---------------------------------------------------------------- 開檔
    def open_waveform(self, path: str) -> dict:
        p = Path(path).expanduser()

        def work() -> dict:
            waves = read_waveform_file(p)
            if not waves:
                raise ScopeError("沒有波形資料可畫。")
            info = read_file_info(p)
            with self._lock:
                self._gen += 1
                self._reset(p)
                self._waves, self._n_raw = list(waves), len(waves)
                self._units = {w.channel: "V" for w in waves}
                gen = self._gen
            big = any(len(w.time) > decimate.PYRAMID_MIN for w in waves)
            if big:  # 單層金字塔：在分析執行緒預建，之後 /wave 縮放不必掃全部原始點
                for w in waves:
                    if len(w.time) > decimate.PYRAMID_MIN:
                        self._pyr[w.channel] = decimate.Pyramid(w.voltage)
            t = waves[0].time
            rows = [("檔名", p.name)]
            rows += [(lbl, info[k]) for k, lbl in (("Model", "機型"), ("Series", "系列"), ("CapturedAt", "擷取時間"))
                     if k in info]
            rows += [("通道", ", ".join(w.channel for w in waves)), ("點數", f"{len(t):,}")]
            if len(t) > 1 and t[1] > t[0]:
                rows += [("取樣間隔", _si(float(t[1] - t[0]), "s")), ("取樣率", _si(1 / float(t[1] - t[0]), "Sa/s"))]
            if len(t):
                rows.append(("時間長度", _si(float(t[-1] - t[0]), "s")))
            return _clean({"path": str(p), "gen": gen, "model": info.get("Model"), "series": info.get("Series"),
                           "captured_at": info.get("CapturedAt"), "info": [list(r) for r in rows],
                           "channels": [self._info(w, self._units, gen) for w in waves], "pyramid": big})

        return work()

    # ---------------------------------------------------------------- 游標／Marker
    def cursor_readout(self, t1: float, t2: float, dx: dict) -> dict:
        _, waves, _ = self._need()
        dx = _dx(dx)
        first = waves[0]
        d0 = dx.get(first.channel, 0.0)
        i1, i2 = _nearest(first.time, t1 - d0), _nearest(first.time, t2 - d0)
        s1, s2 = float(first.time[i1]) + d0, float(first.time[i2]) + d0
        y: dict[str, dict] = {}
        for w in waves:
            d = dx.get(w.channel, 0.0)

            def at(s: float) -> float | None:
                x = s - d
                return None if x < w.time[0] or x > w.time[-1] else float(w.voltage[_nearest(w.time, x)])
            y[w.channel] = {"y1": at(s1), "y2": at(s2)}
        return _clean({"t1": s1, "t2": s2, "index1": i1, "index2": i2, "y": y})

    def marker_eval(self, mode: str, channel: str, x1: float, x2: float, y1: float, y2: float,
                    screen_width: float, measurements: list) -> dict:
        if mode not in markermod.MODES:  # 含 Track RF：只走 fft_track_rf
            raise BadRequest(f"未知或不支援的 Marker 模式：{mode}")
        _, waves, _ = self._need()
        w = self._wf(waves, channel)
        r = markermod.evaluate(mode, markermod.Position(x1, x2, y1, y2), markermod.Source(w.time, w.voltage),
                               screen_width=screen_width, measurements=[tuple(m) for m in measurements or []])
        p = r.position
        return _clean({"position": {"x1": p.x1, "x2": p.x2, "y1": p.y1, "y2": p.y2}, "available": r.available,
                       "reason": r.reason, "read_only": r.read_only, "points": [list(q) for q in r.points],
                       "versus": r.versus, "delta_x": r.delta_x, "inverse_delta_x": r.inverse_delta_x,
                       "delta_y": r.delta_y})

    # ---------------------------------------------------------------- 量測
    def measure(self, entries: list, range: list, dx: dict, threshold: str) -> dict:
        rng, dx = _range(range), _dx(dx)
        if threshold not in THRESHOLDS:
            raise BadRequest(f"未知閾值：{threshold}")
        for e in entries:
            if e.get("name") not in MEASUREMENTS:
                raise BadRequest(f"未知量測：{e.get('name')}")
        gen, waves, units = self._need()
        with self._lock:
            self._rev += 1
            rev = self._rev
        pct = THRESHOLDS[threshold]
        meta = [("量測範圍", "全部" if rng is None else f"游標區間 t1={rng[0]!r} s, t2={rng[1]!r} s"),
                ("閾值", threshold)]

        def work() -> dict:
            by = {w.channel: w for w in waves}
            out = []
            for e in entries:
                ch, name, rising = e["channel"], e["name"], bool(e.get("rising", True))
                w = by.get(ch)
                row = {"channel": ch, "name": name, "unit": unit_of(name, units.get(ch, "V")), "ok": False,
                       "stats": None, "reason": None, "gen": gen, "revision": rev,
                       "_label": f"{name}({ch}{(' ↑' if rising else ' ↓') if name in SLOPED else ''})"}
                if w is None:
                    row["reason"] = "來源通道已刪除"
                else:
                    t, v = self._cut(w, rng, dx)
                    if not len(t) or not np.isfinite(v).any():
                        row["reason"] = "所選範圍內沒有資料"
                    else:
                        try:
                            s = _stats(_measure(name, t, v, pct, rising))
                            row["ok"] = True
                            row["stats"] = dict(zip(("current", "mean", "min", "max", "range", "std", "count"), s))
                        except ScopeError as exc:
                            row["reason"] = str(exc)
                out.append(row)
            self._alive(gen)
            with self._lock:
                if self._snap is None or rev > self._snap["revision"]:
                    self._snap = {"gen": gen, "revision": rev, "results": out, "meta": meta}
            return _clean({"gen": gen, "revision": rev,
                           "results": [{k: v for k, v in r.items() if k != "_label"} for r in out]})

        return work()

    # ---------------------------------------------------------------- 數學
    def math(self, op: str, a: str, b: str, param: float) -> dict:
        if op not in mathfn.OPERATIONS:
            raise BadRequest(f"未知運算：{op}")
        if op in mathfn.BINARY and not b:
            raise BadRequest("二元運算需要來源 b")
        if op in mathfn.FILTERS and not param > 0:
            raise BadRequest("濾波／平滑參數必須 > 0")
        gen, waves, units = self._need()
        wa = self._wf(waves, a)
        wb = self._wf(waves, b) if op in mathfn.BINARY else None

        def work() -> dict:
            args = (wb.time, wb.voltage, units[wb.channel]) if wb else (None, None, "")
            t, v, unit = mathfn.derive(op, wa.time, wa.voltage, units[wa.channel], *args, float(param))
            with self._lock:
                self._alive(gen)
                name = f"F{self._next_f}"  # F 編號不重用
                self._next_f += 1
                w = Waveform(name, t, v)
                self._waves.append(w)
                self._units[name] = unit
                return _clean(self._info(w, self._units, gen))

        return work()

    def remove_channel(self, name: str) -> None:
        with self._lock:
            names = [w.channel for w in self._waves]
            if name not in names or names.index(name) < self._n_raw:
                raise ScopeError("只能刪除衍生通道")
            i = names.index(name)
            self._waves.pop(i)
            self._units.pop(name, None)
            self._pyr.pop(name, None)
        return None

    # ---------------------------------------------------------------- FFT
    def fft(self, source: str, range: list, dx: dict, window: str, unit: str, r_ohm: float,
            peak_count: int, peak_level: float, peak_sort: str) -> dict:
        rng, dx = _range(range), _dx(dx)
        if window not in fftmod.WINDOWS:
            raise BadRequest(f"未知視窗：{window}")
        if unit not in fftmod.UNITS:
            raise BadRequest(f"未知單位：{unit}")
        if peak_sort not in SORTS:
            raise BadRequest(f"未知峰排序：{peak_sort}")
        if not (r_ohm > 0) or not math.isfinite(peak_level) or not peak_count >= 1:
            raise BadRequest("r_ohm／peak_level／peak_count 無效")
        gen, waves, units = self._need()
        w = self._wf(waves, source)
        su = units[source]

        def fail(reason: str, out_unit: str) -> dict:
            with self._lock:
                self._spec = None  # 失敗後舊頻譜 id 失效
            return _clean({"ok": False, "reason": reason, "gen": gen, "spectrum_id": None, "source": source,
                           "unit": out_unit, "window": window, "df": None, "rbw": None, "enbw": None,
                           "enbw_bins": None, "cg": None, "n": None, "effective_n": None, "r_ohm": None,
                           "f_min": None, "f_max": None, "peaks": []})

        def work() -> dict:
            t, v = self._cut(w, rng, dx)
            fin = int(np.isfinite(v).sum())
            out_u = "°" if unit == "Phase" else (f"{su} rms" if su != "V" else unit)
            if not len(t) or not fin:
                return fail("所選範圍內沒有資料", out_u)
            if len(t) < 2:
                return fail("所選範圍內資料不足，無法計算 FFT", out_u)
            s = fftmod.spectrum(t, v, window, unit, r_ohm, su)
            pk = [] if s["unit"] == "°" else fftmod.peaks(s["freq"], s["mag"], peak_count, s["lobe"],
                                                        level=peak_level, sort=peak_sort, interpolate=True,
                                                        amplitude=s["rms"])
            self._alive(gen)
            with self._lock:
                self._spec_no += 1
                sid = f"s{self._spec_no}"
                self._spec = {"id": sid, "gen": gen, "freq": s["freq"], "mag": s["mag"]}
            return _clean({"ok": True, "reason": None, "gen": gen, "spectrum_id": sid, "source": source,
                           "unit": s["unit"], "window": window, "df": s["df"], "rbw": s["rbw"], "enbw": s["enbw"],
                           "enbw_bins": s["enbw_bins"], "cg": s["cg"], "n": s["n"],
                           "effective_n": s["effective_n"], "r_ohm": s["r_ohm"], "f_min": float(s["freq"][0]),
                           "f_max": float(s["freq"][-1]), "peaks": [{"x": x, "y": y} for x, y in pk]})

        return work()

    def _get_spec(self, sid: str) -> dict:
        with self._lock:
            s = self._spec
            if s is None or s["id"] != sid or s["gen"] != self._gen:
                raise StaleError("頻譜已過期，請重新計算 FFT")
            return s

    def fft_track_rf(self, spectrum_id: str, x: float, direction: int, level: float) -> dict:
        if direction not in (-1, 0, 1):
            raise BadRequest("direction 必須是 -1、0 或 1")
        s = self._get_spec(spectrum_id)
        r = markermod.track_rf(s["freq"], s["mag"], x, level=level, direction=direction)
        p = r.position
        return _clean({"x": p.x1, "y": p.y1, "available": r.available, "reason": r.reason})

    # ---------------------------------------------------------------- 匯出
    def export_csv(self, range: list, max_points: int, directory: str) -> dict:
        rng = _range(range)
        if max_points is not None and not max_points >= 1:
            raise BadRequest("max_points 必須 ≥ 1 或 null")
        _, waves, _ = self._need()
        with self._lock:
            raw, path = list(waves[:self._n_raw]), self._path
        if directory:
            out_dir = Path(directory).expanduser()
        elif path is not None:
            out_dir = path.parent
        else:
            raise ScopeError("沒有來源檔資料夾，請指定輸出資料夾")
        stem = path.stem if path else "waveform"

        def work() -> dict:  # 原始資料、來源時間軸，不套 dx
            p = csv_export.export_csv(out_dir, stem, raw, rng, int(max_points) if max_points else None)
            return {"path": str(p)}

        return work()

    def export_measurements(self, rows: list, gen: int, revision: int, directory: str) -> dict:
        with self._lock:
            snap, path = self._snap, self._path
            if snap is None or gen != self._gen or snap["gen"] != gen or snap["revision"] != revision:
                raise StaleError("量測結果已過期，請重新量測")
        if len(rows or []) != len(snap["results"]):
            raise StaleError("量測列與快照不符，請重新量測")
        out_dir = Path(directory).expanduser() if directory else (path.parent if path else None)
        if out_dir is None:
            raise ScopeError("沒有來源檔資料夾，請指定輸出資料夾")
        stem = path.stem if path else "waveform"
        meta = [("來源檔", str(path or "（未存檔）")), *snap["meta"],
                ("匯出時間", dt.datetime.now().isoformat(" ", "seconds"))]
        p = timestamped(out_dir, f"{stem}_量測", "csv")
        try:
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerows(meta)
                w.writerow([])
                w.writerow(["量測", "單位", "目前", "平均", "最小", "最大", "範圍", "標準差", "次數", "備註"])
                for r in snap["results"]:
                    s = r["stats"]
                    w.writerow([r["_label"], r["unit"], *(repr(s[k]) for k in
                                ("current", "mean", "min", "max", "range", "std", "count"))] + [""] if s
                               else [r["_label"], r["unit"], *[""] * 7, r["reason"] or ""])
        except OSError as e:
            raise ScopeError(f"匯出量測結果失敗：{e}") from e
        return {"path": str(p)}

    # ---------------------------------------------------------------- 二進位（server 經模組函式呼叫）
    def _wave_bytes(self, ch: str, t0: float, t1: float, px: int, gen: int) -> bytes:
        with self._lock:
            self._alive(gen)
            w = next((w for w in self._waves if w.channel == ch), None)
            if w is None:
                raise BadRequest(f"通道不存在：{ch}")
            pyr = self._pyr.get(ch)
            if pyr is None and len(w.time) > decimate.PYRAMID_MIN:  # 衍生通道：第一次用到才建
                pyr = self._pyr[ch] = decimate.Pyramid(w.voltage)
        return decimate.wave(w.time, w.voltage, t0, t1, px, pyr)

    def _fft_bytes(self, spectrum_id: str, f0: float, f1: float, px: int, log: bool) -> bytes:
        s = self._get_spec(spectrum_id)
        return decimate.spectrum(s["freq"], s["mag"], f0, f1, px, bool(log))


def wave_bytes(analysis: Analysis, ch: str, t0: float, t1: float, px: int, gen: int) -> bytes:
    """/wave：gen 不符 → StaleError（409）；通道不存在／px 無效 → ValueError（BAD_REQUEST）。"""
    return analysis._wave_bytes(ch, t0, t1, px, gen)


def fft_bytes(analysis: Analysis, spectrum_id: str, f0: float, f1: float, px: int, log: bool) -> bytes:
    """/fft：spectrum_id 不是目前頻譜 → StaleError（409）。"""
    return analysis._fft_bytes(spectrum_id, f0, f1, px, log)


def _self_check() -> None:
    import inspect
    import json
    import tempfile

    import h5py

    from scope_tool.web.decimate import decode

    # 方法名與參數名須與契約 owner=Analysis 完全一致
    c = json.loads((Path(__file__).parent / "static" / "api_contract.json").read_text(encoding="utf-8"))["methods"]
    want = {n: [p["name"] for p in m["params"]] for n, m in c.items() if m["owner"] == "Analysis"}
    got = {n: [p for p in inspect.signature(f).parameters if p != "self"]
           for n, f in inspect.getmembers(Analysis, inspect.isfunction) if not n.startswith("_")}
    assert got == want, (set(got) ^ set(want), got, want)

    A = Analysis()

    def run(r: Any) -> Any:  # 工作型方法已是同步函式
        return r

    def err(fn, *a, exc=Exception):
        try:
            fn(*a)
        except exc as e:
            return e
        raise AssertionError("應該失敗")

    n = 20000
    t = np.arange(n) * 1e-6
    sq = np.interp(t % 1e-3, [0, 10e-6, 500e-6, 510e-6, 1e-3], [0, 2, 2, 0, 0])
    sin = np.sin(2 * np.pi * 5e3 * t)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        csvp = tmp / "a.csv"
        csvp.write_text("Time(s),CH1(V),CH2(V)\n" + "\n".join(
            f"{float(a)!r},{float(b)!r},{float(c_)!r}" for a, b, c_ in zip(t, sq, sin)) + "\n", encoding="utf-8")
        assert isinstance(err(A.measure, [], None, {}, "10/50/90 %", exc=ScopeError), ScopeError)  # 未開檔

        fs = run(A.open_waveform(str(csvp)))
        assert fs["gen"] == 1 and [c["name"] for c in fs["channels"]] == ["CHAN1", "CHAN2"] and not fs["pyramid"]
        assert fs["channels"][0]["points"] == n and fs["model"] is None and ["檔名", "a.csv"] in fs["info"]

        ent = [{"channel": "CHAN1", "name": "頻率", "rising": True}, {"channel": "CHAN1", "name": "Vp-p", "rising": True},
               {"channel": "F9", "name": "Vmax", "rising": True}]
        m = run(A.measure(ent, None, {}, "10/50/90 %"))
        assert m["gen"] == 1 and m["revision"] == 1
        r0, r1, r2 = m["results"]
        assert r0["ok"] and abs(r0["stats"]["mean"] - 1000) < 1 and r0["stats"]["count"] >= 10 and r0["unit"] == "Hz"
        assert r1["ok"] and abs(r1["stats"]["max"] - 2) < 1e-9 and not r2["ok"] and r2["stats"] is None
        # dx：CHAN2 的 dx 讓同一顯示區間對應不同來源區間；反序 range 等價；兩端含
        e2 = [{"channel": "CHAN2", "name": "Vmax", "rising": True}]
        a1 = run(A.measure(e2, [0.004, 0.001], {}, "10/50/90 %"))["results"][0]
        a2 = run(A.measure(e2, [0.001, 0.004], {}, "10/50/90 %"))["results"][0]
        assert a1["stats"] == a2["stats"] and a1["ok"]
        b = run(A.measure(e2, [0.001, 0.004], {"CHAN2": 0.0002}, "10/50/90 %"))["results"][0]
        sl = (t >= 0.001 - 0.0002) & (t <= 0.004 - 0.0002)
        assert abs(b["stats"]["max"] - sin[sl].max()) < 1e-9
        # 空區間：具名失敗，不得 count=1
        em = run(A.measure(e2, [5.0, 6.0], {}, "10/50/90 %"))["results"][0]
        assert not em["ok"] and em["stats"] is None and em["reason"] == "所選範圍內沒有資料"
        # 匯出量測：最新 revision 成功，過期 revision／gen 為 STALE
        rev = run(A.measure(ent[:2], None, {}, "20/50/80 %"))
        exp = A.export_measurements(rev["results"], rev["gen"], rev["revision"], str(tmp))
        text = Path(exp["path"]).read_text(encoding="utf-8-sig")
        assert "頻率(CHAN1 ↑)" in text and "20/50/80 %" in text
        assert isinstance(err(A.export_measurements, rev["results"], 1, rev["revision"] - 1, str(tmp),
                              exc=StaleError), StaleError)
        assert isinstance(err(A.export_measurements, rev["results"], 9, rev["revision"], str(tmp),
                              exc=StaleError), StaleError)

        # 游標
        cr = A.cursor_readout(0.0012341, 0.002, {"CHAN2": 1e-6})
        assert cr["index1"] == 1234 and cr["y"]["CHAN2"]["y1"] is not None
        out = A.cursor_readout(0.0, 1.0, {})
        assert out["y"]["CHAN1"]["y2"] is not None and out["t2"] == float(t[-1])
        out = A.cursor_readout(0.0, 0.01, {"CHAN2": 0.5})  # CHAN2 平移後落在時間軸外 → null
        assert out["y"]["CHAN2"]["y1"] is None
        # Marker
        mk = A.marker_eval("Track Waveforms", "CHAN1", 1e-3, 2e-3, 0.0, 0.0, 1e-3, [])
        assert mk["available"] and mk["position"]["x1"] == 1e-3
        assert isinstance(err(A.marker_eval, "Track RF", "CHAN1", 0, 0, 0, 0, 1e-3, [], exc=BadRequest), BadRequest)
        mm = A.marker_eval("Track Measurements", "CHAN1", 0, 0, 0, 0, 1e-3, [[0, 1, "a"], [1, 3, "b"]])
        assert mm["read_only"] and mm["delta_y"] == 2

        # 數學：F1，編號不重用
        f1 = run(A.math("平方", "CHAN1", None, 0))
        assert f1["name"] == "F1" and f1["derived"] and f1["unit"] == "V²" and f1["gen"] == 1
        f2 = run(A.math("加", "CHAN1", "CHAN2", 0))
        assert f2["name"] == "F2"
        A.remove_channel("F2")
        assert run(A.math("反相", "CHAN1", None, 0))["name"] == "F3"
        assert isinstance(err(A.remove_channel, "CHAN1", exc=ScopeError), ScopeError)
        assert isinstance(err(A.math, "低通", "CHAN1", None, 0, exc=BadRequest), BadRequest)

        # FFT／Track RF
        kw = dict(window="Hanning", unit="dBV", r_ohm=50.0, peak_count=3, peak_level=-40.0,
                  peak_sort="Decreasing Magnitude")
        fr = run(A.fft("CHAN2", None, {}, **kw))
        assert fr["ok"] and fr["spectrum_id"] == "s1" and abs(fr["peaks"][0]["x"] - 5000) < 100
        assert fr["f_min"] == 0 and fr["df"] > 0
        fr2 = run(A.fft("F1", None, {}, **kw))  # 衍生通道：輸出單位為 <u> rms
        assert fr2["unit"] == "V² rms" and fr2["spectrum_id"] == "s2"
        assert isinstance(err(A.fft_track_rf, "s1", 5000.0, 0, -40.0, exc=StaleError), StaleError)
        fr = run(A.fft("CHAN2", None, {}, **kw))
        rf = A.fft_track_rf(fr["spectrum_id"], 4900.0, 0, -40.0)
        assert rf["available"] and abs(rf["x"] - 4900) <= fr["df"]
        rf = A.fft_track_rf(fr["spectrum_id"], rf["x"], 1, 0.0)  # 門檻 0 dBV 以上沒有峰 → 維持原位
        assert not rf["available"] and rf["reason"] and rf["y"] is not None and rf["x"] is not None
        assert isinstance(err(A.fft_track_rf, fr["spectrum_id"], 1.0, 2, -40.0, exc=BadRequest), BadRequest)
        # FFT 空區間形狀；失敗後舊頻譜失效
        fe = run(A.fft("CHAN2", [5.0, 6.0], {}, **kw))
        assert fe["ok"] is False and fe["spectrum_id"] is None and fe["peaks"] == [] and fe["df"] is None \
            and fe["reason"]
        assert isinstance(err(A.fft_track_rf, fr["spectrum_id"], 1.0, 0, -40.0, exc=StaleError), StaleError)
        fr = run(A.fft("CHAN2", None, {}, **kw))
        # 二進位
        n_, mode, bx, lo, hi = decode(wave_bytes(A, "CHAN1", 0.0, 1.0, 100, 1))
        assert mode == 1 and n_ == 100
        assert isinstance(err(wave_bytes, A, "CHAN1", 0.0, 1.0, 100, 7, exc=StaleError), StaleError)
        assert decode(fft_bytes(A, fr["spectrum_id"], 0.0, 1e6, 200, False))[1] == 1
        assert decode(fft_bytes(A, fr["spectrum_id"], 100.0, 1e6, 200, True))[2][0] > 0
        assert isinstance(err(fft_bytes, A, "s999", 0, 1, 10, False, exc=StaleError), StaleError)

        # 匯出 CSV（來源時間、不套 dx）；directory=null → 來源檔資料夾
        ex = run(A.export_csv([0.001, 0.002], 50, None))
        got_w = read_waveform_file(Path(ex["path"]))
        assert Path(ex["path"]).parent == tmp and 1 <= len(got_w[0].time) <= 50 and len(got_w) == 2
        assert isinstance(err(A.export_csv, [5.0, 6.0], None, str(tmp), exc=ScopeError), ScopeError)

        # NaN → null：含 NaN 的 h5；二進位保留 NaN
        nan_v = sq.copy()
        nan_v[100:110] = np.nan
        h5p = tmp / "b.h5"
        with h5py.File(h5p, "w") as hf:
            g = hf.create_group("Waveforms/Channel 1")
            g.create_dataset("Channel 1Data", data=nan_v)
            g.attrs["XInc"], g.attrs["XOrg"] = 1e-6, 0.0
        fs2 = run(A.open_waveform(str(h5p)))
        assert fs2["gen"] == 2 and fs2["channels"][0]["vmax"] == 2.0
        assert isinstance(err(wave_bytes, A, "CHAN1", 0.0, 1.0, 100, 1, exc=StaleError), StaleError)  # 舊 gen
        assert isinstance(err(A.fft_track_rf, fr["spectrum_id"], 1.0, 0, -40.0, exc=StaleError), StaleError)
        assert isinstance(err(A.export_measurements, [], 1, 5, str(tmp), exc=StaleError), StaleError)
        nm = run(A.measure([{"channel": "CHAN1", "name": "Vmax", "rising": True}], [0.0, 0.0001], {}, "10/50/90 %"))
        s = nm["results"][0]
        assert not s["ok"] and "NaN" in s["reason"] and json.dumps(nm, allow_nan=False)
        allnan = run(A.measure([{"channel": "CHAN1", "name": "Vmax", "rising": True}], [100e-6, 109e-6], {},
                               "10/50/90 %"))["results"][0]
        assert not allnan["ok"] and allnan["reason"] == "所選範圍內沒有資料"
        cr = A.cursor_readout(100e-6, 105e-6, {})
        assert cr["y"]["CHAN1"]["y1"] is None and json.dumps(cr, allow_nan=False)
        _, _, _, lo, hi = decode(wave_bytes(A, "CHAN1", 0.0, 1.0, 50, 2))
        assert np.isnan(lo).any() and np.array_equal(np.isnan(lo), np.isnan(hi))
        # 參數錯誤
        assert isinstance(err(A.measure, [], [1, "x"], {}, "10/50/90 %", exc=BadRequest), BadRequest)
        assert isinstance(err(A.measure, [], None, {}, "bad", exc=BadRequest), BadRequest)
        assert isinstance(err(A.fft, "CHAN1", None, {}, "Bad", "dBV", 50.0, 3, -40.0, SORTS[0], exc=BadRequest),
                          BadRequest)
    print("analysis_api self-check OK")


if __name__ == "__main__":
    _self_check()
