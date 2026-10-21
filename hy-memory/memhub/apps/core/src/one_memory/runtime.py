import json
import os
import sys
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol

from filelock import FileLock, Timeout

from one_memory.config import Settings


class CoreAlreadyRunningError(RuntimeError):
    """Raised when another Core owns the same data directory."""


#: Set by the desktop launcher to the pid it wants this Core tied to.
PARENT_PID_VARIABLE = "ONE_MEMORY_PARENT_PID"


def parent_pid(environment: Mapping[str, str] | None = None) -> int | None:
    raw = (environment if environment is not None else os.environ).get(PARENT_PID_VARIABLE)
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 1 else None


#: Win32 constants, spelled out rather than imported: `ctypes.wintypes` does
#: not carry them and importing anything Windows-only would break every other
#: platform at import time.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_INVALID_PARAMETER = 87


class WindowsProcessApi(Protocol):
    """The four Win32 calls the probe needs, so the decisions can be tested.

    This machine is macOS: `ctypes.WinDLL` does not exist here, so binding the
    calls inside the probe would leave every branch in it unreachable by any
    test. A mutation proved that was not hypothetical — dropping the exit-code
    check below passed the whole suite.
    """

    def open_process(self, pid: int) -> int: ...

    def last_error(self) -> int: ...

    def exit_code(self, handle: int) -> int | None: ...

    def close(self, handle: int) -> None: ...


def _windows_process_is_alive(pid: int, api: WindowsProcessApi | None = None) -> bool:
    """Ask Windows whether a pid exists, without signalling it.

    There is no cheap "signal 0" on Windows — see `process_is_alive`. Opening
    a handle answers the same question: a pid that never existed or has been
    reaped fails with `ERROR_INVALID_PARAMETER`, and anything else that stops
    us opening it (access denied on a process owned by someone else) means it
    is there, which matches what the POSIX branch concludes from
    `PermissionError`.
    """
    current = api if api is not None else _kernel32()
    handle = current.open_process(pid)
    if not handle:
        return current.last_error() != _ERROR_INVALID_PARAMETER
    try:
        code = current.exit_code(handle)
        if code is None:
            # The handle opened, so the process object is there; failing to
            # read its exit code is not evidence that it is gone.
            return True
        # A process that has exited keeps a queryable handle until the last
        # one is closed, so "open succeeded" alone would report the dead as
        # alive — the exit code is what distinguishes them.
        return code == _STILL_ACTIVE
    finally:
        current.close(handle)


def _kernel32() -> WindowsProcessApi:
    """Bind the Win32 calls. Only ever reached on Windows.

    Imported here rather than at module scope: `ctypes.WinDLL` exists on no
    other platform, and this module is imported everywhere.
    """
    import ctypes

    library = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

    class Kernel32:
        def open_process(self, pid: int) -> int:
            return int(library.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid))

        def last_error(self) -> int:
            # `get_last_error` exists only on Windows, so the checker running
            # on this machine cannot see it.
            return int(ctypes.get_last_error())  # type: ignore[attr-defined]

        def exit_code(self, handle: int) -> int | None:
            code = ctypes.c_ulong()
            if not library.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            return int(code.value)

        def close(self, handle: int) -> None:
            library.CloseHandle(handle)

    return Kernel32()


def process_is_alive(
    pid: int,
    *,
    platform: str | None = None,
    kill: Callable[[int, int], None] = os.kill,
    windows_probe: Callable[[int], bool] = _windows_process_is_alive,
) -> bool:
    """Whether the process exists.

    A live process owned by another user would raise `PermissionError`, which
    still answers the question asked: it is there.

    `os.kill(pid, 0)` cannot be used on Windows. Per CPython's documentation,
    every sig other than `CTRL_C_EVENT` / `CTRL_BREAK_EVENT` there "will cause
    the process to be unconditionally killed by the TerminateProcess API" —
    so the probe would kill what it is probing. The pid this is asked about is
    the desktop app's, and the watchdog asks every two seconds: on Windows the
    module written to stop a Core outliving its app would instead have killed
    the app, with the exit code set to sig, which is 0 — indistinguishable
    from the person quitting.

    The platform and both calls are injectable because this machine is macOS:
    the branch can be tested, the Win32 calls in it cannot.
    """
    current = platform or sys.platform
    if current == "win32":
        return windows_probe(pid)
    try:
        kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class CoreRuntime:
    def __init__(self, settings: Settings, *, publish_receipt: bool = True) -> None:
        self.settings = settings
        self._publish_receipt = publish_receipt
        self._lock = FileLock(settings.data_dir / "core.lock", timeout=0)
        self._receipt_path = settings.data_dir / "runtime.json"
        self._token_path = settings.data_dir / "runtime-token"

    def __enter__(self) -> "CoreRuntime":
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire()
        except Timeout as error:
            raise CoreAlreadyRunningError(
                f"Another MemHub Core owns {self.settings.data_dir}"
            ) from error

        if not self._publish_receipt:
            return self

        # The parent is recorded so that a later Core can tell an orphan from a
        # genuine second instance. Under PyInstaller `os.getppid()` is the
        # bootloader, which outlives the app that launched it, so only the pid
        # the launcher names is any use here.
        receipt = {
            "schema_version": 1,
            "service": "one-memory-core",
            "instance_id": self.settings.instance_id,
            "pid": os.getpid(),
            "parent_pid": parent_pid(),
            "host": self.settings.host,
            "port": self.settings.port,
            "started_at": datetime.now(UTC).isoformat(),
        }
        try:
            if os.name == "posix":
                _write_private_file(
                    self._token_path,
                    self.settings.api_token.get_secret_value(),
                )
            else:
                # Windows attach remains disabled until the token is protected
                # by a verified current-user SID/DACL implementation.
                self._token_path.unlink(missing_ok=True)
            _write_private_file(
                self._receipt_path,
                json.dumps(receipt, ensure_ascii=False, indent=2),
            )
        except Exception:
            self._receipt_path.unlink(missing_ok=True)
            self._token_path.unlink(missing_ok=True)
            self._lock.release()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._publish_receipt:
            self._receipt_path.unlink(missing_ok=True)
            self._token_path.unlink(missing_ok=True)
        self._lock.release()


def _write_private_file(path: os.PathLike[str], content: str) -> None:
    """Replace a local runtime control file without inheriting a permissive umask."""
    target = os.fspath(path)
    temporary = f"{target}.{os.getpid()}.{time.time_ns()}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        if os.name == "posix":
            os.chmod(target, 0o600)
    except Exception:
        with suppress(OSError):
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary)
        raise
