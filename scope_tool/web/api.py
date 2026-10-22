"""Api：暴露給前端的後端方法（契約 owner=Api）。

驅動器（VISA）呼叫一律包在交給 `jobs.submit` 的函式裡，由儀器工作執行緒執行；
HTTP 執行緒與 pywebview 主執行緒不做 VISA I/O。
公開方法集合與參數名必須等於 api_contract.json（見 contract_check）；
輔助方法一律以底線開頭。
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from scope_tool import config as config_mod
from scope_tool.contracts import (
    CaptureArea, FoundInstrument, ImageFormat, ScopeDriver, ScopeError, ScreenshotOptions,
    Series, WaveformFormat,
)
from scope_tool.web.jobs import BadRequestError, Jobs

for _m in ("infiniivision", "infiniium"):  # 註冊 driver；缺相依時略過（同 ui/main_window）
    try:
        __import__(f"scope_tool.instruments.{_m}")
    except Exception:  # noqa: BLE001
        pass

CONTRACT_PATH = Path(__file__).parent / "static" / "api_contract.json"
_PATH_KEYS = ("screenshot_dir", "waveform_dir")
_IP_RE = re.compile(r"^[\w.\-:]+$")


def _path(s: str) -> Path:
    return Path(s).expanduser()


def _asdict(f: FoundInstrument) -> dict[str, str]:
    return {"resource": f.resource, "source": f.source, "label": f.label}


def _enum(cls: Any, value: Any, what: str) -> Any:
    try:
        return cls(value)
    except ValueError:
        raise BadRequestError(f"{what} 不合法：{value!r}") from None


def _filename(name: str) -> str:
    if not name or any(c in name for c in "/\\") or name in (".", ".."):
        raise BadRequestError(f"檔名不合法：{name!r}")
    return name


class Api:
    def __init__(self, jobs: Jobs, cfg: dict[str, Any] | None = None, persist: bool = True) -> None:
        self._jobs = jobs
        self._cfg = cfg if cfg is not None else config_mod.load()
        self._persist = persist
        self._drv: ScopeDriver | None = None
        self._window: Any = None
        self._shot: tuple[int, bytes] | None = None  # (序號, 位元組)
        self._shot_n = 0
        self._lock = threading.Lock()  # 保護 _cfg／_shot
        self._catalog: dict[str, Any] | None = None

    # ------------------------------------------------------------ 內部輔助
    def _attach_window(self, window: Any) -> None:
        self._window = window

    def _shutdown(self) -> None:
        """程式結束時盡力關閉連線。"""
        d, self._drv = self._drv, None
        try:
            if d is not None and d.res is not None:
                d.res.close()
        except Exception:  # noqa: BLE001
            pass
        self._save()

    def _save(self) -> None:
        if self._persist:
            config_mod.save(self._cfg)

    def _config_view(self) -> dict[str, Any]:
        c = json.loads(json.dumps(self._cfg))
        for k in _PATH_KEYS:  # 前端不自行展開 ~，一律回絕對路徑
            c[k] = str(_path(c[k]).absolute())
        return c

    def _emit_driver(self) -> None:
        d = self._drv
        self._jobs.events.emit({"type": "driver", "connected": d is not None,
                                "model": d.model if d else None,
                                "series": d.series.value if d else None})

    def _need_drv(self) -> ScopeDriver:
        if self._drv is None:
            raise ScopeError("尚未連線儀器")
        return self._drv

    def _close_old(self) -> None:
        old, self._drv = self._drv, None
        if old is not None:
            try:
                if old.res is not None:
                    old.res.close()
            except Exception:  # noqa: BLE001
                pass
            self._emit_driver()

    # ------------------------------------------------------------ 狀態與設定
    def get_state(self) -> dict[str, Any]:
        if self._catalog is None:
            self._catalog = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))["catalog"]
        d = self._drv
        return {"config": self._config_view(), "connected": d is not None,
                "model": d.model if d else None, "series": d.series.value if d else None,
                "catalog": self._catalog, "native_dialogs": self._window is not None,
                "seq": self._jobs.events.seq}

    def save_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        bad = set(patch) - set(config_mod.DEFAULTS)
        if bad:
            raise BadRequestError(f"未知的設定鍵：{sorted(bad)}")
        with self._lock:
            for k, v in patch.items():
                self._cfg[k] = str(_path(v)) if k in _PATH_KEYS and isinstance(v, str) else v
            self._save()
        return self._config_view()

    def _pick(self, kind: str, initial: str | None) -> str | None:
        """原生對話框；視窗未建立（--browser）時回 None（前端應已改走 ui.prompt）。"""
        w = self._window
        if w is None:
            return None
        import webview
        fd = getattr(webview, "FileDialog", None)
        mode = (fd.FOLDER if kind == "folder" else fd.OPEN) if fd else \
            (webview.FOLDER_DIALOG if kind == "folder" else webview.OPEN_DIALOG)
        types = () if kind == "folder" else ("波形檔 (*.h5;*.hdf5;*.csv)", "所有檔案 (*.*)")
        d = str(_path(initial)) if initial else ""
        r = w.create_file_dialog(mode, directory=d, file_types=types)  # 待真機／桌面環境驗證
        return str(r[0]) if r else None

    def pick_folder(self, initial: str | None) -> str | None:
        return self._pick("folder", initial)

    def pick_waveform_file(self, initial: str | None) -> str | None:
        return self._pick("file", initial)

    # ------------------------------------------------------------ 搜尋與連線
    def search(self) -> dict[str, Any]:
        def work() -> list[dict[str, str]]:
            from scope_tool.instruments import discovery
            return [_asdict(f) for f in discovery.find_all(list(self._cfg.get("manual_resources", [])))]
        return self._jobs.submit("search", work, lock=True)

    def add_manual_ip(self, ip: str) -> list[dict[str, str]]:
        ip = ip.strip()
        if not _IP_RE.match(ip):
            raise BadRequestError(f"IP 格式不合法：{ip!r}")
        with self._lock:
            m = list(self._cfg.get("manual_resources", []))
            if ip not in m:
                m.append(ip)
            self._cfg["manual_resources"] = m
            self._save()
        from scope_tool.instruments import discovery
        return [_asdict(f) for f in discovery._manual_list(m)]

    def connect(self, resource: str, series_override: str | None) -> dict[str, Any]:
        override = _enum(Series, series_override, "series_override") if series_override else None

        def work() -> dict[str, str]:
            import pyvisa
            from scope_tool.instruments import registry
            self._close_old()  # 先關舊連線再連
            res = pyvisa.ResourceManager().open_resource(resource)
            res.timeout = 5000
            try:
                idn = res.query("*IDN?")
                model = registry.parse_idn(idn)[1]
                ov = override
                if ov is None and self._cfg.get("series_overrides", {}).get(model):
                    ov = Series(self._cfg["series_overrides"][model])
                d = registry.driver_for(res, idn, override=ov)
            except Exception:
                res.close()
                raise
            with self._lock:
                if override is not None:  # 成功連線才回寫手選系列
                    self._cfg.setdefault("series_overrides", {})[d.model] = override.value
                self._cfg["last_resource"] = resource
                self._save()
            self._drv = d
            self._emit_driver()  # driver 事件早於本工作的 job 事件
            return {"model": d.model, "series": d.series.value}
        return self._jobs.submit("connect", work, lock=True)

    def connect_fake(self) -> dict[str, str]:
        from scope_tool.instruments.fake import FakeDriver
        with self._jobs.try_lock():  # 非工作型，但不可與進行中的儀器工作交錯
            if self._drv is not None and self._drv.res is not None:
                raise ScopeError("請先斷線真機再切換到模擬儀器")
            self._close_old()
            self._drv = FakeDriver()
            self._emit_driver()
        return {"model": self._drv.model, "series": self._drv.series.value}

    def disconnect(self) -> dict[str, Any]:
        def work() -> None:
            self._close_old()
        return self._jobs.submit("disconnect", work, lock=True)

    # ------------------------------------------------------------ 儀器操作
    def capture_info(self) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            d = self._need_drv()
            return {"channels": d.channels(), "max_points": d.max_points()}
        return self._jobs.submit("capture_info", work, lock=True)

    def screenshot(self, directory: str, name: str, image_format: str, inverted: bool,
                   area: str) -> dict[str, Any]:
        from scope_tool.storage import writer
        fmt = _enum(ImageFormat, image_format, "image_format")
        opts = ScreenshotOptions(fmt, bool(inverted), _enum(CaptureArea, area, "area"))
        out, base = _path(directory), _filename(name)

        def work() -> dict[str, Any]:
            d = self._need_drv()
            data = d.screenshot(opts)
            path = writer.write_screenshot(out, base, data, fmt)
            with self._lock:
                self._shot_n += 1
                self._shot = (self._shot_n, data)
                return {"path": str(path), "preview": self._shot_n}
        return self._jobs.submit("screenshot", work, lock=True)

    def capture(self, directory: str, name: str, channels: list[str], points: int,
                retrigger: bool) -> dict[str, Any]:
        from scope_tool.storage import writer
        if not channels or not all(isinstance(c, str) for c in channels):
            raise BadRequestError("channels 不可為空")
        if isinstance(points, bool) or not isinstance(points, int) or points <= 0:
            raise BadRequestError("points 必須是正整數")
        out, base = _path(directory), _filename(name)

        def work() -> dict[str, Any]:
            d = self._need_drv()
            result = d.capture(list(channels), points, bool(retrigger))
            path = writer.write_waveform(out, base, result, WaveformFormat.HDF5)  # 規則：擷取一律 HDF5
            return {"path": str(path), "requested": points,
                    "got_points": min(len(w.voltage) for w in result.waveforms)}
        return self._jobs.submit("capture", work, lock=True)

    # ------------------------------------------------------------ 供 server 使用
    def _last_screenshot(self) -> bytes | None:
        s = self._shot
        return s[1] if s else None


def contract_check() -> str:
    """Api（與 analysis_api.Analysis，若已存在）的公開方法與參數名須等於契約。"""
    import inspect
    methods = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))["methods"]
    classes: dict[str, Any] = {"Api": Api}
    note = ""
    try:
        from scope_tool.web.analysis_api import Analysis
        classes["Analysis"] = Analysis
    except ImportError:
        note = "（analysis_api 尚未存在，僅檢查 Api）"
    for owner, cls in classes.items():
        want = {n: [p["name"] for p in m["params"]] for n, m in methods.items() if m["owner"] == owner}
        got = {n: [p for p in inspect.signature(f).parameters if p != "self"]
               for n, f in inspect.getmembers(cls, inspect.isfunction) if not n.startswith("_")}
        assert set(got) == set(want), (owner, sorted(set(got) ^ set(want)))
        for n in want:
            assert got[n] == want[n], (owner, n, got[n], want[n])
    return "contract check OK" + note


if __name__ == "__main__":
    print(contract_check())
