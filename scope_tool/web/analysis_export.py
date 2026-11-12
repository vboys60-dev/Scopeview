"""Analysis 的匯出部分（mixin）：export_csv、export_measurements、export_report。"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from scope_tool.contracts import ScopeError
from scope_tool.storage import csv_export
from scope_tool.storage.writer import timestamped
from scope_tool.web.analysis_util import BadRequest, StaleError, _range


# 量測 CSV 的名詞顯示用英文（key 仍是中文，與前端 terms.js 同譯名）
EN = {"上升時間": "Rise Time", "下降時間": "Fall Time", "上升斜率": "Rise Slew", "下降斜率": "Fall Slew",
      "週期": "Period", "頻率": "Frequency", "+寬度": "+Width", "-寬度": "-Width", "工作週期": "+Duty Cycle",
      "-工作週期": "-Duty Cycle", "過衝": "Overshoot", "前衝": "Preshoot", "延遲": "Delay", "相位": "Phase",
      "電壓比": "Gain"}


def _en_label(label: str) -> str:
    name, _, rest = label.partition("(")
    return EN.get(name, name) + ("(" + rest if rest else "").replace(" 整數週期", " N Cycles").replace(" 單週期", " One Cycle").replace(" 單一事件", " Single Event").replace(" 全部邊緣", " All Edges")


class ExportMixin:
    def export_csv(self, range: list, max_points: int, directory: str) -> dict:
        rng = _range(range)
        if max_points is not None and not max_points >= 1:
            raise BadRequest("max_points 必須 ≥ 1 或 null")
        _, waves, _ = self._need()
        with self._lock:
            raw, path = [w for w in waves if w.channel in self._main], self._path
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
        meta = [("Source File", str(path or "(unsaved)")), *snap["meta"],
                ("Exported At", dt.datetime.now().isoformat(" ", "seconds"))]
        p = timestamped(out_dir, f"{stem}_量測", "csv")
        try:
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerows(meta)
                w.writerow([])
                w.writerow(["Measure", "Unit", "Current", "Mean", "Min", "Max", "Range", "Std Dev", "Count", "Note"])
                # 雙來源的 channel2 與兩個方向併入 _label，與畫面一致。
                for r in snap["results"]:
                    s = r["stats"]
                    prefix = r["bound"] + " " if r.get("bound") else ""
                    w.writerow([_en_label(r["_label"]), r["unit"], *((prefix if k != "count" else "") + repr(s[k]) for k in
                                ("current", "mean", "min", "max", "range", "std", "count"))] + [""] if s
                               else [_en_label(r["_label"]), r["unit"], *[""] * 7, r["reason"] or ""])
        except OSError as e:
            raise ScopeError(f"匯出量測結果失敗：{e}") from e
        return {"path": str(p)}

    def export_report(self, html: str, directory: str) -> dict:
        """前端組好的自包含 HTML 報告，照來源檔資料夾與時間戳規則寫檔。"""
        if not isinstance(html, str) or not html:
            raise BadRequest("html 必須是非空字串")
        with self._lock:
            path = self._path
        out_dir = Path(directory).expanduser() if directory else (path.parent if path else None)
        if out_dir is None:
            raise ScopeError("沒有來源檔資料夾，請指定輸出資料夾")
        try:
            p = timestamped(out_dir, f"{path.stem if path else 'waveform'}_報告", "html")
            p.write_text(html, encoding="utf-8")
        except OSError as e:
            raise ScopeError(f"匯出報告失敗：{e}") from e
        return {"path": str(p)}
