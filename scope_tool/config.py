"""使用者設定的讀寫。存在家目錄，不進專案。"""

from __future__ import annotations

import json
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


def load() -> dict[str, Any]:
    """讀設定。檔案壞掉或不存在都回預設值，不拋例外。"""
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict[str, Any]) -> None:
    """寫設定。寫不進去就算了，不要因為設定存不了而讓程式當掉。"""
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":
    c = load()
    assert set(DEFAULTS) <= set(c)
    assert isinstance(c["points"], int)
    print("config self-check OK")
