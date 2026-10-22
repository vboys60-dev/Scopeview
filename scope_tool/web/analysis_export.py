"""Analysis 的匯出部分（mixin）：export_csv、export_measurements。"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from scope_tool.contracts import ScopeError
from scope_tool.storage import csv_export
from scope_tool.storage.writer import timestamped
from scope_tool.web.analysis_util import BadRequest, StaleError, _range


class ExportMixin:
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
