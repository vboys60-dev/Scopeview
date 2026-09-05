"""背景執行緒：把會卡住 UI 的呼叫（尤其是 VISA I/O）丟到這裡跑。

只有 `Job` 這一個類別，不做 thread pool、不做任務佇列——
UI 需要幾個工作就開幾個 `Job`，用完即丟。
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from scope_tool.contracts import ScopeError


class Job(QThread):
    """在背景執行緒跑一個 callable，結果或錯誤都用 signal 回傳給 UI 執行緒。

    用法：
        job = Job(driver.screenshot, opts)
        job.done.connect(on_done)
        job.failed.connect(on_failed)
        job.start()
    呼叫端要自己保留 `job` 的參照（例如存在 self 上），否則 QThread
    物件被 GC 掉會導致執行緒被砍斷。
    """

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except ScopeError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 — 背景執行緒裡任何例外都不能讓程式當掉
            self.failed.emit(f"未預期錯誤：{exc}")
        else:
            self.done.emit(result)


def _self_check() -> None:
    import time

    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])

    results: list[Any] = []

    def ok_fn(x: int) -> int:
        return x * 2

    job1 = Job(ok_fn, 21)
    job1.done.connect(lambda v: results.append(("done", v)))
    job1.failed.connect(lambda m: results.append(("failed", m)))
    job1.start()
    job1.wait(2000)
    app.processEvents()

    def scope_error_fn() -> None:
        raise ScopeError("測試用錯誤")

    job2 = Job(scope_error_fn)
    job2.done.connect(lambda v: results.append(("done", v)))
    job2.failed.connect(lambda m: results.append(("failed", m)))
    job2.start()
    job2.wait(2000)
    app.processEvents()

    def boom_fn() -> None:
        raise RuntimeError("炸了")

    job3 = Job(boom_fn)
    job3.done.connect(lambda v: results.append(("done", v)))
    job3.failed.connect(lambda m: results.append(("failed", m)))
    job3.start()
    job3.wait(2000)
    app.processEvents()

    # 等待所有背景執行緒真的結束，signal 才會確實送達
    for _ in range(50):
        if len(results) >= 3:
            break
        time.sleep(0.05)
        app.processEvents()

    assert ("done", 42) in results, results
    assert any(kind == "failed" and msg == "測試用錯誤" for kind, msg in results), results
    assert any(kind == "failed" and msg.startswith("未預期錯誤：") for kind, msg in results), results

    print("worker self-check OK")


if __name__ == "__main__":
    import os

    os.environ.setdefault("QT_API", "pyside6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _self_check()
