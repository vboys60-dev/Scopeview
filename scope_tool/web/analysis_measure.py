"""Analysis 的量測部分（mixin）。"""
from __future__ import annotations

import numpy as np

from scope_tool.analysis.measure import DUAL, INTERVAL, MEASUREMENTS, SLOPED, THRESHOLDS, measure_event, measure2, stats as _stats, unit_of, current_index
from scope_tool.analysis.measure_marks import marks
from scope_tool.analysis.measure_extra import EXTRA, measure_extra, delta_time
from scope_tool.contracts import ScopeError
from scope_tool.web.analysis_util import BadRequest, StaleError, _clean, _dx, _range


class MeasureMixin:
    # ---------------------------------------------------------------- 量測
    def measure(self, entries: list, range: list, dx: dict, threshold: str) -> dict:
        rng, dx = _range(range), _dx(dx)
        if threshold not in THRESHOLDS:
            raise BadRequest(f"未知閾值：{threshold}")
        for e in entries:
            for key in ("edge_num", "edge_num2"):
                if key in e and (type(e[key]) is not int or not 1 <= e[key] <= 65534):
                    raise BadRequest(f"{key} 必須為 1–65534 的整數")
            if any(e.get(k, "middle") not in ("lower", "middle", "upper") for k in ("edge_level", "edge_level2")):
                raise BadRequest("未知閾值層")
            if ("channel2" in e and not isinstance(e["channel2"], str)) or ("rising2" in e and not isinstance(e["rising2"], bool)):
                raise BadRequest("channel2 必須為字串，rising2 必須為布林值")
            if "track" in e and not isinstance(e["track"], bool):
                raise BadRequest("track 必須為布林值")
            if "all_edges" in e and not isinstance(e["all_edges"], bool):
                raise BadRequest("all_edges 必須為布林值")
            if e.get("mode", "full") not in ("full", "cycles", "cycle"):
                raise BadRequest("未知區間模式")
            if (e.get("name") in DUAL or e.get("name") == "Delta Time") and "channel2" not in e:
                raise BadRequest("雙來源量測必須指定 channel2")
            if e.get("name") not in MEASUREMENTS and e.get("name") not in DUAL and e.get("name") not in EXTRA and e.get("name") != "Delta Time":
                raise BadRequest(f"未知量測：{e.get('name')}")
        gen, waves, units = self._need()
        with self._lock:
            self._rev += 1
            rev = self._rev
        pct = THRESHOLDS[threshold]
        meta = [("Measure Range", "All" if rng is None else f"Cursors t1={rng[0]!r} s, t2={rng[1]!r} s"),
                ("Threshold", threshold)]

        def work() -> dict:
            by = {w.channel: w for w in waves}
            out = []
            for e in entries:
                ch, name, rising = e["channel"], e["name"], bool(e.get("rising", True))
                cycles = name in INTERVAL and e.get("mode") == "cycles"
                cycle = name in INTERVAL and e.get("mode") == "cycle"
                suffix = (" ↑" if rising else " ↓") if (name in SLOPED and e.get("all_edges", True)) or cycles else ""
                dual, ch2 = name in DUAL or name == "Delta Time", e.get("channel2")
                if dual:
                    suffix = (" ↑" if rising else " ↓") + ("↑" if e.get("rising2", rising) else "↓") if name != "電壓比" else ""
                w = by.get(ch)
                row = {"channel": ch, "name": name, "unit": EXTRA[name][1].replace("{u}", units.get(ch, "V")) if name in EXTRA else "s" if name == "Delta Time" else unit_of(name, units.get(ch, "V")), "ok": False,
                       "stats": None, "reason": None, "gen": gen, "revision": rev,
                       "_label": f"{name}({ch + ('→' + str(ch2) if dual else '')}{' 整數週期' if cycles else ' 單週期' if cycle else ''}{suffix}{' 全部邊緣' if name == '相位' and not e.get('all_edges', True) else ' 單一事件' if not e.get('all_edges', True) else ''})"}
                if name == "Delta Time":
                    lev = {"lower": "下", "middle": "中", "upper": "上"}
                    row["_label"] = f"Delta Time({ch}#{e.get('edge_num', 1)}{'↑' if rising else '↓'}→{ch2}#{e.get('edge_num2', 1)}{'↑' if e.get('rising2', rising) else '↓'} {lev[e.get('edge_level', 'middle')]}／{lev[e.get('edge_level2', 'middle')]})"
                if e.get("track", False):
                    row["marks"] = None
                if dual:
                    row["channel2"] = ch2
                if w is None or (dual and ch2 not in by):
                    row["reason"] = "來源通道已刪除"
                else:
                    t, v = self._cut(w, rng, dx)
                    if not len(t) or not np.isfinite(v).any():
                        row["reason"] = ("來源 1：" if dual else "") + "所選範圍內沒有資料"
                    else:
                        try:
                            d = dx.get(ch, 0.0)
                            start, end = float(t[0]) + d, float(t[-1]) + d
                            ref = 0.0 if start <= 0 <= end else (start + end) / 2
                            if dual:
                                # _cut 保留來源時間（供 FFT）；配對前加各自 dx 換成顯示時間。
                                t2, v2 = self._cut(by[ch2], rng, dx)
                                if not len(t2) or not np.isfinite(v2).any():
                                    raise ScopeError("來源 2：所選範圍內沒有資料")
                                if name == "Delta Time":
                                    values = delta_time(t + dx.get(ch, 0), v, t2 + dx.get(ch2, 0), v2, pct, rising, e.get("rising2", rising), e.get("edge_num", 1), e.get("edge_num2", 1), e.get("edge_level", "middle"), e.get("edge_level2", "middle"))
                                else:
                                    values = measure2(name, t + dx.get(ch, 0), v, t2 + dx.get(ch2, 0), v2,
                                                  pct, rising, e.get("rising2", rising))
                            elif name in EXTRA:
                                values = measure_extra(name, t, v, pct)
                            else:
                                values = measure_event(name, t, v, pct, rising, e.get("mode", "full"),
                                                       ref_time=ref, dx=d, meas_all_edges=e.get("all_edges", True))
                            # 參考與事件皆以顯示時間比較，避免反向平移的浮點誤差破壞同距規則。
                            if not dual and getattr(values, "at", None) is not None:
                                values.at = values.at + d
                            s = _stats(values, ref, meas_all_edges=e.get("all_edges", True) or name == "相位")
                            if getattr(values, "bound", None):
                                row["bound"] = values.bound
                            if e.get("track", False):
                                i = current_index(values, ref)
                                tracked_values = values
                                if not dual and getattr(values, "at", None) is not None:
                                    tracked_values = values.view(type(values))
                                    tracked_values.at = values.at - d
                                pts = marks(name, t + d if dual else t, v, pct, tracked_values, i, rising, e.get("mode", "full"), ref if dual else ref-d,
                                            t2 + dx.get(ch2, 0) if dual else None, v2 if dual else None, e.get("rising2", rising),
                                            e.get("edge_num", 1), e.get("edge_num2", 1), e.get("edge_level", "middle"), e.get("edge_level2", "middle"))
                                if pts is not None:
                                    row["marks"] = [[float(x), float(y), c] for group, c in zip(pts, (ch, ch2)) for x, y in group] if dual else [[float(x+d), float(y), ch] for x, y in pts]
                            row["ok"] = True
                            row["stats"] = dict(zip(("current", "mean", "min", "max", "range", "std", "count"), s))
                        except ScopeError as exc:
                            row["reason"] = str(exc)
                out.append(row)
            with self._lock:
                self._alive(gen)
                used = {e[k] for e in entries for k in ("channel", "channel2") if k in e and e[k] in by}
                if any(next((w for w in self._waves if w.channel == ch), None) is not by[ch] for ch in used):
                    raise StaleError("量測來源已變更，請重新量測")
                if self._snap is None or rev > self._snap["revision"]:
                    self._snap = {"gen": gen, "revision": rev, "results": out, "meta": meta}
            return _clean({"gen": gen, "revision": rev,
                           "results": [{k: v for k, v in r.items() if k != "_label"} for r in out]})

        return work()


if __name__ == "__main__":
    from scope_tool.web.analysis_check import _self_check

    _self_check()
    print("analysis_measure self-check OK")
