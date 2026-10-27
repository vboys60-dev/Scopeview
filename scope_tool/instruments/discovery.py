"""儀器搜尋：VISA 列表 + mDNS + 手動輸入，三個來源合併去重。不掃網段（見 docs/adr/0002）。"""

from __future__ import annotations

import socket
import time

from scope_tool.contracts import FoundInstrument

_MDNS_SERVICE_TYPES = ("_hislip._tcp.local.", "_lxi._tcp.local.", "_scpi-raw._tcp.local.")


def _visa_list() -> list[FoundInstrument]:
    """列出本機 VISA 資源（USB／序列埠，LAN 上的儀器不會出現在這裡）。"""
    try:
        import pyvisa

        resources = pyvisa.ResourceManager().list_resources()
    except Exception:
        return []
    return [FoundInstrument(resource=r, source="visa", label=r) for r in resources]


def _mdns_scan(timeout: float) -> list[FoundInstrument]:
    """查 zeroconf 的 _hislip._tcp / _lxi._tcp / _scpi-raw._tcp。

    zeroconf 沒裝或掃描過程出任何錯，一律回空 list，不拋例外。
    """
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError:
        return []

    class _Listener(ServiceListener):
        def __init__(self) -> None:
            self.found: list[tuple[str, str]] = []

        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            if info and info.addresses:
                ip = socket.inet_ntoa(info.addresses[0])
                self.found.append((name, ip))

        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            pass

        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            pass

    try:
        zc = Zeroconf()
        listener = _Listener()
        browsers = [ServiceBrowser(zc, t, listener) for t in _MDNS_SERVICE_TYPES]
        time.sleep(timeout)
        zc.close()
        del browsers
    except Exception:
        return []

    return [
        FoundInstrument(resource=f"TCPIP0::{ip}::hislip0::INSTR", source="mdns", label=f"{name} ({ip})")
        for name, ip in listener.found
    ]


def _manual_list(manual: list[str]) -> list[FoundInstrument]:
    """把使用者手動輸入的 IP 字串組成 VISA 資源字串。"""
    return [
        FoundInstrument(resource=f"TCPIP0::{ip}::inst0::INSTR", source="manual", label=ip)
        for ip in manual
    ]


def _idn_label(item: FoundInstrument) -> FoundInstrument:
    """開一次短連線問 *IDN?，label 改成「型號 · S/N 序號 — 資源」；任何失敗（被佔用、逾時）維持原 label。"""
    try:
        import pyvisa

        inst = pyvisa.ResourceManager().open_resource(item.resource, open_timeout=2000)
        try:
            inst.timeout = 2000
            parts = [p.strip() for p in inst.query("*IDN?").split(",")]
        finally:
            inst.close()
        if len(parts) >= 3 and parts[1]:
            return FoundInstrument(resource=item.resource, source=item.source,
                                   label=f"{parts[1]} · S/N {parts[2]} — {item.resource}")
    except Exception:
        pass
    return item


def find_all(manual: list[str], timeout: float = 3.0, enrich: bool = True) -> list[FoundInstrument]:
    """合併 VISA + mDNS + 手動輸入三個來源，依資源字串去重（保留先出現的那筆）。"""
    combined = _visa_list() + _mdns_scan(timeout) + _manual_list(manual)
    seen: set[str] = set()
    result: list[FoundInstrument] = []
    for item in combined:
        if item.resource in seen:
            continue
        seen.add(item.resource)
        result.append(item)
    if result and enrich:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(min(8, len(result))) as ex:
            result = list(ex.map(_idn_label, result))
    return result


if __name__ == "__main__":
    result = find_all([], timeout=1.0, enrich=False)
    assert isinstance(result, list)

    result2 = find_all(["1.2.3.4"], enrich=False)
    manual_hits = [f for f in result2 if f.source == "manual"]
    assert len(manual_hits) == 1
    assert manual_hits[0].resource == "TCPIP0::1.2.3.4::inst0::INSTR"

    print("discovery self-check OK")
