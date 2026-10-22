"""Analysis 的 FFT 部分（mixin）：fft、fft_track_rf 與頻譜二進位。狀態由 Analysis 提供。"""
from __future__ import annotations

import math

import numpy as np

from scope_tool.analysis import fft as fftmod
from scope_tool.analysis import marker as markermod
from scope_tool.analysis.peaks import SORTS
from scope_tool.web import decimate
from scope_tool.web.analysis_util import BadRequest, StaleError, _clean, _dx, _range


class FftMixin:
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

    def _fft_bytes(self, spectrum_id: str, f0: float, f1: float, px: int, log: bool) -> bytes:
        s = self._get_spec(spectrum_id)
        return decimate.spectrum(s["freq"], s["mag"], f0, f1, px, bool(log))

