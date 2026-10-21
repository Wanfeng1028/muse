"""R-29：Windows 上 `os.kill` 不是发信号，是无条件杀进程。

CPython 官方文档（os.kill）：

    Windows: The `signal.CTRL_C_EVENT` and `signal.CTRL_BREAK_EVENT` signals
    are special signals which can only be sent to console processes which
    share a common console window... Any other value for sig will cause the
    process to be unconditionally killed by the TerminateProcess API, and the
    exit code will be set to sig.

于是 `parent_watchdog` 这个专门用来避免残留 Core 的模块，在 Windows 上会变成
它自己要防的那个故障：

- `process_is_alive(pid)` 用 `os.kill(pid, 0)` 探活,那一句会 TerminateProcess
  掉桌面 app 本身，而且退出码被设成 sig（0），在 app 侧看着像用户正常退出。
  看门狗每 2 秒查一次，Core 起来两秒后 app 就没了。
- `_terminate_self()` 用 `os.kill(os.getpid(), SIGTERM)`,同样走
  TerminateProcess，uvicorn 的 SIGTERM 处理器不跑，而按模块开头那段注释，
  正是那个处理器负责释放数据目录锁、删掉 runtime 回执。残留锁之后下次启动
  直接报「another MemHub Core owns this directory」。

这台机器是 macOS，所以两条都按「平台可注入」来断言,验的是分支选择而不是
Windows 的系统调用本身。系统调用那一侧只能等真机，已记在
`docs/mvp/2026-09-08-r29-windows-survey.md` 的待实测项里。
"""

import os
import signal
import threading
import time

from one_memory.parent_watchdog import ParentWatchdog, _terminate_self
from one_memory.runtime import (
    _ERROR_INVALID_PARAMETER,
    _STILL_ACTIVE,
    _windows_process_is_alive,
    process_is_alive,
)


def test_probing_a_pid_on_windows_does_not_go_through_os_kill() -> None:
    """探活不能在 Windows 上落到 `os.kill`,那一句会把被探的进程杀掉。"""
    calls: list[tuple[int, int]] = []

    def recording_kill(pid: int, sig: int) -> None:
        calls.append((pid, sig))

    probed: list[int] = []

    def fake_windows_probe(pid: int) -> bool:
        probed.append(pid)
        return True

    alive = process_is_alive(
        4321,
        platform="win32",
        kill=recording_kill,
        windows_probe=fake_windows_probe,
    )

    assert alive is True
    assert probed == [4321]
    assert calls == [], "Windows 上探活一旦落到 os.kill，被探的就是宿主 app"


def test_probing_a_pid_still_uses_os_kill_everywhere_else() -> None:
    """绿对照：POSIX 上 `os.kill(pid, 0)` 是正确且最便宜的探活，别顺手改掉。"""
    calls: list[tuple[int, int]] = []

    def recording_kill(pid: int, sig: int) -> None:
        calls.append((pid, sig))

    def unreachable_probe(pid: int) -> bool:  # pragma: no cover - 不该被调到
        raise AssertionError("POSIX 上不该走 Windows 分支")

    alive = process_is_alive(
        4321,
        platform="darwin",
        kill=recording_kill,
        windows_probe=unreachable_probe,
    )

    assert alive is True
    assert calls == [(4321, 0)]


def test_a_real_dead_pid_is_reported_dead_on_this_machine() -> None:
    """绿对照：真实语义不能在重构里丢掉。"""
    # 自己一定活着；一个绝不可能存在的 pid 一定死了。
    assert process_is_alive(os.getpid()) is True
    assert process_is_alive(2**31 - 1) is False


def test_asking_for_shutdown_on_windows_keeps_the_signal_handler_in_play() -> None:
    """自杀不能走 `os.kill`,否则 uvicorn 的处理器不跑，锁和回执都留下。

    `signal.raise_signal` 在进程内触发处理器，不经 TerminateProcess，
    两个平台上都是同一条路径,所以这里断言的是「不再有人对自己 os.kill」。
    """
    kills: list[tuple[int, int]] = []
    raised: list[int] = []

    _terminate_self(
        kill=lambda pid, sig: kills.append((pid, sig)),
        raise_signal=lambda sig: raised.append(sig),
    )

    assert raised == [signal.SIGTERM]
    assert kills == [], "对自己 os.kill 在 Windows 上等于放弃优雅退出"


def test_the_watchdog_still_fires_once_and_only_once() -> None:
    """绿对照：上面两处都在看门狗的路径上，它本身的行为不许被带偏。"""
    shutdowns: list[str] = []
    watchdog = ParentWatchdog(
        parent_pid=4321,
        is_alive=lambda pid: False,
        request_shutdown=lambda: shutdowns.append("asked"),
    )

    assert watchdog.check_once() is True
    assert watchdog.check_once() is True
    assert shutdowns == ["asked"]


def test_the_handler_runs_even_though_the_watchdog_is_on_another_thread() -> None:
    """看门狗跑在自己的线程上,信号得真的把处理器带起来才算数。

    `raise_signal` 的 C 层处理器在调用线程执行，Python 侧的回调由主线程跑。
    这条测的正是「从看门狗线程要求关闭，主线程的处理器会被调到」,否则换成
    raise_signal 只是把一处不生效换成另一处不生效。
    """
    seen: list[int] = []
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda number, frame: seen.append(number))
    try:
        thread = threading.Thread(target=_terminate_self)
        thread.start()
        thread.join(timeout=5)
        # Python 只在主线程跑信号回调，所以这里必须把时间片让出去等它。
        deadline = time.monotonic() + 5
        while not seen and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert seen == [signal.SIGTERM]


class FakeWin32:
    """够回答四个问题就行：能不能开、错误码是什么、退出码是什么、关没关。"""

    def __init__(
        self,
        *,
        handle: int,
        last_error: int = 0,
        exit_code: int | None = _STILL_ACTIVE,
    ) -> None:
        self._handle = handle
        self._last_error = last_error
        self._exit_code = exit_code
        self.closed: list[int] = []

    def open_process(self, pid: int) -> int:
        return self._handle

    def last_error(self) -> int:
        return self._last_error

    def exit_code(self, handle: int) -> int | None:
        return self._exit_code

    def close(self, handle: int) -> None:
        self.closed.append(handle)


def test_a_windows_process_that_already_exited_is_not_read_as_alive() -> None:
    """退出的进程句柄仍然打得开,只看「开成功了」会把死的报成活的。

    这条是变异跑出来的：去掉退出码判断时，前一版测试全绿。而这里报错就等于
    看门狗永远不开火,Windows 上残留 Core 的场景一个都接不住。
    """
    api = FakeWin32(handle=99, exit_code=0)

    assert _windows_process_is_alive(4321, api) is False
    assert api.closed == [99], "句柄必须关，否则探活自己会漏句柄"


def test_a_windows_process_still_running_is_read_as_alive() -> None:
    api = FakeWin32(handle=99, exit_code=_STILL_ACTIVE)

    assert _windows_process_is_alive(4321, api) is True
    assert api.closed == [99]


def test_a_pid_windows_says_is_not_a_pid_is_read_as_gone() -> None:
    api = FakeWin32(handle=0, last_error=_ERROR_INVALID_PARAMETER)

    assert _windows_process_is_alive(4321, api) is False
    assert api.closed == [], "没开成的句柄不该被关"


def test_a_process_we_are_not_allowed_to_open_is_read_as_there() -> None:
    """与 POSIX 分支把 PermissionError 读成「它在」是同一口径。"""
    _ERROR_ACCESS_DENIED = 5
    api = FakeWin32(handle=0, last_error=_ERROR_ACCESS_DENIED)

    assert _windows_process_is_alive(4321, api) is True


def test_an_exit_code_we_cannot_read_is_not_taken_as_death() -> None:
    """句柄开成了就说明进程对象在;读不到退出码不构成「它死了」的证据。"""
    api = FakeWin32(handle=99, exit_code=None)

    assert _windows_process_is_alive(4321, api) is True
    assert api.closed == [99]
