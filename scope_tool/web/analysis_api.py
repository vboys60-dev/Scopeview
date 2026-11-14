"""分析服務（契約 owner=Analysis）：開檔、量測、游標、Marker、數學、FFT、Track RF、匯出。

純 numpy／分析層呼叫，不碰 driver、不拿儀器鎖。工作型方法（契約 job=true）為
同步函式直接回傳結果；由 server 依契約 job 旗標包成 job。
世代 gen：每次開檔 +1，舊檔工作結果一律以 STALE 丟棄；revision：每次 measure 提出時配號，
export_measurements 只認「最新已完成」的快照。
/wave、/fft 的二進位由模組函式 wave_bytes／fft_bytes（第一參數為 Analysis）提供。
"""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from scope_tool.analysis import marker as markermod
from scope_tool.analysis import mathfn
from scope_tool.contracts import ScopeError, Waveform
from scope_tool.storage.reader import read_file_info, read_waveform_file
from scope_tool.web import decimate

from scope_tool.web.analysis_slots import SlotMixin
from scope_tool.web.analysis_decode import DecodeMixin
from scope_tool.web.analysis_export import ExportMixin
from scope_tool.web.analysis_fft import FftMixin
from scope_tool.web.analysis_measure import MeasureMixin
from scope_tool.web.analysis_params import validate_params
from scope_tool.web.analysis_util import BadRequest, StaleError, _clean, _dx, _nearest, _file_rows

__all__ = ["Analysis", "wave_bytes", "fft_bytes", "validate_params"]  # validate_params 供 server 使用


class Analysis(SlotMixin, DecodeMixin, FftMixin, ExportMixin, MeasureMixin):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._gen = 0
        self._rev = 0          # 已配出的最大 revision
        self._reset(None)

    # ---------------------------------------------------------------- 內部狀態
    def _reset(self, path: Path | None) -> None:
        self._dec = None
        self._path, self._waves, self._units = path, [], {}
        self._main, self._slots = [], {}
        self._next_f, self._pyr, self._spec, self._snap = 1, {}, None, None

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

    def _info(self, w: Waveform, units: dict[str, str], gen: int, raw: set[str] | None = None) -> dict:
        v = w.voltage[np.isfinite(w.voltage)]
        return {"name": w.channel, "unit": units[w.channel], "derived": w.channel not in (self._raw_names() if raw is None else raw),
                "points": len(w.time), "t0": float(w.time[0]), "t1": float(w.time[-1]),
                "vmin": float(v.min()) if len(v) else None, "vmax": float(v.max()) if len(v) else None, "gen": gen}

    def _raw_names(self) -> set[str]:
        return set(self._main).union(*self._slots.values())

    # ---------------------------------------------------------------- 開檔
    def open_waveform(self, path: str) -> dict:
        p = Path(path).expanduser()

        def work() -> dict:
            waves = [w for w in read_waveform_file(p) if len(w.time)]
            if not waves:
                raise ScopeError("沒有波形資料可畫。")
            info = read_file_info(p)
            # 重活（金字塔）先建在區域變數；鎖內只換狀態，所以與 close／_reset 不會互相踩
            pyr = {w.channel: decimate.Pyramid(w.voltage) for w in waves if len(w.time) > decimate.PYRAMID_MIN}
            main = [w.channel for w in waves]
            with self._lock:
                self._gen += 1
                self._reset(p)
                self._waves, self._main = list(waves), main
                self._units = {c: "V" for c in main}
                self._pyr.update(pyr)
                gen = self._gen
            big = bool(pyr)
            rows = _file_rows(p, info, waves)
            return _clean({"path": str(p), "gen": gen, "model": info.get("Model"), "series": info.get("Series"),
                           "captured_at": info.get("CapturedAt"), "info": [list(r) for r in rows],
                           "channels": [self._info(w, {c: "V" for c in main}, gen, set(main)) for w in waves], "pyramid": big})

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
        # 追蹤視窗中心：資料含 0 秒（觸發點）用 0（同 Qt）；否則取兩游標中點夾進資料範圍
        trig = 0.0 if w.time[0] <= 0 <= w.time[-1] else float(np.clip((x1 + x2) / 2, w.time[0], w.time[-1]))
        r = markermod.evaluate(mode, markermod.Position(x1, x2, y1, y2), markermod.Source(w.time, w.voltage),
                               screen_width=screen_width, trigger_t=trig, measurements=[tuple(m) for m in measurements or []])
        p = r.position
        return _clean({"position": {"x1": p.x1, "x2": p.x2, "y1": p.y1, "y2": p.y2}, "available": r.available,
                       "reason": r.reason, "read_only": r.read_only, "points": [list(q) for q in r.points],
                       "versus": r.versus, "delta_x": r.delta_x, "inverse_delta_x": r.inverse_delta_x,
                       "delta_y": r.delta_y})

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
                names = {w.channel for w in self._waves}
                while f"F{self._next_f}" in names:
                    self._next_f += 1
                name = f"F{self._next_f}"  # F 編號不重用
                self._next_f += 1
                w = Waveform(name, t, v)
                self._waves.append(w)
                self._units[name] = unit
                return _clean(self._info(w, self._units, gen))

        return work()

    def close_waveform(self) -> None:
        """釋放全部波形、金字塔、頻譜與量測快照；gen 加 1，舊結果之後回 STALE。"""
        with self._lock:
            self._gen += 1
            self._reset(None)
        return None

    def remove_channel(self, name: str) -> None:
        with self._lock:
            names = [w.channel for w in self._waves]
            if name not in names or name in self._raw_names():
                raise ScopeError("只能刪除衍生通道")
            i = names.index(name)
            self._waves.pop(i)
            self._units.pop(name, None)
            self._pyr.pop(name, None)
        return None


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


def wave_bytes(analysis: Analysis, ch: str, t0: float, t1: float, px: int, gen: int) -> bytes:
    """/wave：gen 不符 → StaleError（409）；通道不存在／px 無效 → ValueError（BAD_REQUEST）。"""
    return analysis._wave_bytes(ch, t0, t1, px, gen)


def fft_bytes(analysis: Analysis, spectrum_id: str, f0: float, f1: float, px: int, log: bool) -> bytes:
    """/fft：spectrum_id 不是目前頻譜 → StaleError（409）。"""
    return analysis._fft_bytes(spectrum_id, f0, f1, px, log)


if __name__ == "__main__":
    from scope_tool.web.analysis_check import _self_check

    _self_check()
