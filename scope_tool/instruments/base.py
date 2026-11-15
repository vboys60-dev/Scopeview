"""SCPI 共用邏輯：InfiniiVision 與 Infiniium 都繼承的中介類別。

實際與真機互動的路徑（_write/_query/_query_binary/_check_error）
沒有真機無法驗證，行為只在 docstring 標註處寫明假設。
# 待真機驗證
"""

from __future__ import annotations

import time
import math
from contextlib import contextmanager
from typing import Iterator

import numpy as np
import pyvisa

from scope_tool.contracts import Preamble, RemoteDesktopError, ScopeDriver, ScopeError, ScopeTimeoutError, Waveform


MAX_RECORD_WAIT_S = 30

def _binary_block(data: bytes) -> bytes:
    """自我檢查共用：產生含結尾換行的 IEEE488.2 block。"""
    length = str(len(data)).encode("ascii")
    return b"#" + str(len(length)).encode("ascii") + length + data + b"\n"


def _waveform_from_raw(channel: str, pre: Preamble, raw: np.ndarray,
                       previous: Waveform | None) -> Waveform:
    """相鄰通道的時間參數與點數相同時，共用時間陣列。"""
    old = previous.preamble if previous is not None else None
    if old is not None and (pre.x_increment, pre.x_origin, pre.x_reference, pre.points) == (
            old.x_increment, old.x_origin, old.x_reference, old.points) and len(raw) == len(previous.time):
        return Waveform(channel=channel, time=previous.time, voltage=pre.volts(raw), preamble=pre)
    return Waveform.from_raw(channel, pre, raw)


class SCPIDriver(ScopeDriver):
    """InfiniiVision 與 Infiniium 共用的 SCPI 存取層。

    子類別只需要處理兩家系列在命令字面上的差異，共用的錯誤轉換、
    逾時與擷取前等待都放在這裡。
    """

    def _write(self, cmd: str) -> None:
        """送出寫入型命令，用 `*OPC?` 等待完成。例外一律轉成 ScopeError。"""
        try:
            self.res.write(cmd)
            self.res.query("*OPC?")
        except Exception as exc:
            raise self._wrap(exc, cmd) from exc

    def _write_nowait(self, cmd: str) -> None:
        """送出寫入型命令但不等 `*OPC?`。儀器在等待觸發（Single/Normal）時 `*OPC?` 不會回應。"""
        try:
            self.res.write(cmd)
        except Exception as exc:
            raise self._wrap(exc, cmd) from exc

    def _clear(self) -> bool:
        """VISA device clear，卡住的查詢之後用來恢復通訊；失敗就算了。"""
        try:
            self.res.clear()
            return True
        except Exception:
            return False

    def _query(self, cmd: str) -> str:
        """送出查詢命令，回傳去除頭尾空白的字串。"""
        try:
            return self.res.query(cmd).strip()
        except Exception as exc:
            raise self._wrap(exc, cmd) from exc

    def _query_binary(self, cmd: str, datatype: str) -> np.ndarray:
        """送出回傳 IEEE488.2 binary block 的查詢，回傳 numpy 陣列。"""
        sent = False
        try:
            dtype = {"B": np.dtype("uint8"), "H": np.dtype("<u2")}[datatype]
            self.res.write(cmd)
            sent = True
            header = self.res.read_bytes(2)
            if len(header) != 2 or header[:1] != b"#" or not b"1" <= header[1:] <= b"9":
                raise ValueError("不是 definite-length block")
            total = int(self.res.read_bytes(int(header[1:])))
            data = bytearray(total)
            offset = 0
            while offset < total:
                size = min(4 * 1024 * 1024, total - offset)
                chunk = self.res.read_bytes(size)
                if len(chunk) != size:
                    raise ValueError("binary block 資料不足")
                data[offset:offset + size] = chunk
                offset += size
            if self.res.read_bytes(1) != b"\n":
                raise ValueError("binary block 缺少結尾換行")
            return np.frombuffer(data, dtype=dtype)
        except Exception as exc:
            err = self._wrap(exc, cmd)
            if sent and not self._clear():
                err = type(err)(f"{err}；清除儀器通訊也失敗，請斷線後重新連線")
            raise err from exc

    def _wrap(self, exc: Exception, cmd: str) -> ScopeError:
        """把 pyvisa 例外轉成本工具的 ScopeError 子類別。"""
        if isinstance(exc, pyvisa.errors.VisaIOError) and "timeout" in str(exc).lower():
            return ScopeTimeoutError(f"執行 {cmd!r} 逾時：{exc}")
        return ScopeError(f"執行 {cmd!r} 失敗：{exc}")

    def _check_error(self) -> None:
        """查 `:SYSTem:ERRor?`，273 轉 RemoteDesktopError，其他非 0 轉 ScopeError。"""
        resp = self._query(":SYSTem:ERRor?")
        code_str = resp.split(",", 1)[0].strip()
        try:
            code = int(code_str)
        except ValueError:
            return
        if code == 0:
            return
        if code == 273:
            raise RemoteDesktopError("儀器畫面無法擷取，請關閉遠端桌面連線後重試")
        raise ScopeError(f"儀器回報錯誤：{resp}")

    @contextmanager
    def _timeout(self, ms: int) -> Iterator[None]:
        """暫時改 VISA timeout，離開時（含例外）還原成原本的值。"""
        original = self.res.timeout
        self.res.timeout = ms
        try:
            yield
        finally:
            self.res.timeout = original

    def _is_running(self) -> bool:
        """用操作暫存器的 RUN 位元（bit3，值8）判斷是否在跑。"""
        return bool(int(self._query(":OPERegister:CONDition?")) & 0x8)

    def _record_wait(self) -> float:
        resp = None
        try:
            resp = self._query(":TIMebase:SCALe?")
            scale = float(resp)
            if not math.isfinite(scale) or scale <= 0:
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise ScopeError(f"無法讀取時基：{resp!r}") from exc
        wait = 10 * scale + 1
        if wait > MAX_RECORD_WAIT_S:
            raise ScopeError(f"目前時基 {scale:g} s/div，等待完整記錄約需 {wait:.0f} 秒，超過上限 {MAX_RECORD_WAIT_S} 秒。請先在示波器按 STOP 後再擷取（不勾「重新觸發」），或把時基縮短到約 {(MAX_RECORD_WAIT_S-1)/10:.1f} s/div 以下。")
        return wait

    def _prepare_capture(self, retrigger: bool) -> None:
        """RUN 中先等完整記錄再 STOP；擷取後維持 STOP。Infiniium 待真機驗證。"""
        if retrigger:
            self._record_wait()
            try:
                self._write(":DIGitize")
            except ScopeTimeoutError as exc:
                # DSO-X 3014G 實測：等不到觸發逾時後，須 device clear 才恢復通訊；Infiniium 未測。
                self._clear()
                raise ScopeError(
                    "重新觸發等不到觸發（可能是 Single/Normal 觸發但沒有訊號），已中止。"
                    "請檢查觸發設定，或切到 Auto 觸發再試。"
                ) from exc
        elif self._is_running():
            time.sleep(self._record_wait())
            self._write(":STOP")

    def channels(self) -> list[str]:
        """查 `:CHANnel<n>:DISPlay?` 找出目前開啟中的通道，兩家系列命令相同。

        # 真機驗證（InfiniiVision）：關閉的通道回 "0"；查到不存在的通道會逾時，所以
        # 探測期間 timeout 縮為 1 秒。Infiniium 未測，LAN 較慢時 1 秒可能偏短。
        """
        found: list[str] = []
        with self._timeout(1000):  # 探測不存在的通道會等到逾時，縮短
            for n in range(1, 9):
                try:
                    resp = self._query(f":CHANnel{n}:DISPlay?")
                except ScopeError:
                    break
                if resp.strip() in ("1", "ON"):
                    found.append(f"CHAN{n}")
        # 真機驗證：探測到不存在的通道會逾時並留下 -113，清掉避免污染之後的 _check_error
        self.res.write("*CLS")
        return found


if __name__ == "__main__":
    from scope_tool.instruments.base_check import _self_check; _self_check()
