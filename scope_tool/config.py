"""使用者設定的讀寫。存在家目錄，不進專案。"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".scope_tool.json"

DEFAULTS: dict[str, Any] = {
    "screenshot_dir": str(Path.home() / "Desktop"),
    "screenshot_name": "scope",
    "image_format": "PNG",
    "inverted": False,
    "area": "full",
    "waveform_dir": str(Path.home() / "Desktop"),
    "waveform_name": "wave",
    "waveform_format": "CSV",
    "points": 10000,
    "retrigger": False,
    "last_resource": "",
    "manual_resources": [],      # 使用者手動輸入過的 IP
    "series_overrides": {},      # {型號: "InfiniiVision"|"Infiniium"}，自動判不出來時記住手選結果
}


def _type_ok(v: Any, d: Any) -> bool:
    if isinstance(d, bool) or isinstance(v, bool):
        return isinstance(d, bool) and isinstance(v, bool)
    return isinstance(v, type(d))


def load() -> dict[str, Any]:
    """讀設定。檔案壞掉或不存在都回預設值，不拋例外；型別不符的鍵逐一退回預設。"""
    cfg = dict(DEFAULTS)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if isinstance(raw, dict):
        cfg.update({k: v for k, v in raw.items() if k not in DEFAULTS or _type_ok(v, DEFAULTS[k])})
    return cfg


def save(cfg: dict[str, Any], strict: bool = False) -> None:
    """原子寫設定（tmp＋replace）。預設寫不進去就算了（Qt 舊版不處理例外）；strict=True 則拋 OSError。"""
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    try:
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, CONFIG_PATH)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        if strict:
            raise


if __name__ == "__main__":
    c = load()
    assert set(DEFAULTS) <= set(c)
    assert isinstance(c["points"], int)
    import tempfile
    CONFIG_PATH = Path(tempfile.mkdtemp()) / "c.json"
    CONFIG_PATH.write_text('{"points":"x","retrigger":1,"area":"full","extra":1}')
    c = load()
    assert c["points"] == 10000 and c["retrigger"] is False and c["extra"] == 1
    CONFIG_PATH.write_text("[1]")
    assert load() == DEFAULTS
    save({"points": 5}, strict=True)
    assert load()["points"] == 5 and not CONFIG_PATH.with_name("c.json.tmp").exists()
    CONFIG_PATH = CONFIG_PATH.parent / "no" / "c.json"
    save({})  # 不拋
    try:
        save({}, strict=True); raise SystemExit("應拋 OSError")
    except OSError:
        pass
    print("config self-check OK")
