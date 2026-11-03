"""Exit when the app that launched this Core is gone.

Without this, Core outlives the desktop app whenever the app dies without
getting to run its shutdown — Force Quit, a crash, `kill -9`. The leftover
Core keeps the data directory's lock, so the *next* launch of the app fails
immediately with "another MemHub Core owns this directory" and quits.
Observed on this machine: an app killed with SIGKILL left a Core running for
65 minutes, still holding the lock and still calling the local model, and the
app could not be started again until the invisible process was found by hand.

`os.getppid()` cannot be used for this. The shipped Core is a PyInstaller
binary, so the process tree is app -> bootloader -> Python, and the parent
Python sees is the bootloader, which is still alive precisely when the app is
not. The launcher therefore names the pid it wants us tied to.

Shutdown goes through SIGTERM to our own process rather than `sys.exit`: the
watchdog runs on its own thread, uvicorn installs a SIGTERM handler that
drains connections and unwinds the lifespan, and that is what releases the
lock and removes the receipt. Exiting the thread's stack would leave both.
"""

import os
import signal
import threading
from collections.abc import Callable

from one_memory.runtime import process_is_alive

#: Two seconds is short enough that a relaunch a person triggers by hand
#: finds the lock free, and long enough to cost nothing.
DEFAULT_INTERVAL_SECONDS = 2.0


class ParentWatchdog:
    def __init__(
        self,
        parent_pid: int,
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        is_alive: Callable[[int], bool] = process_is_alive,
        request_shutdown: Callable[[], None] | None = None,
    ) -> None:
        self.parent_pid = parent_pid
        self.interval_seconds = interval_seconds
        self._is_alive = is_alive
        self._request_shutdown = request_shutdown or _terminate_self
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        #: Read by tests and by the shutdown path; not part of the API.
        self.fired = False

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("parent watchdog already started")
        # A daemon thread so that a Core shutting down for any other reason is
        # never held open by this.
        self._thread = threading.Thread(
            target=self._run,
            name="one-memory-parent-watchdog",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self.interval_seconds + 1)
        self._thread = None

    def check_once(self) -> bool:
        """Returns whether the parent is gone, asking for shutdown if it is."""
        if self._is_alive(self.parent_pid):
            return False
        if not self.fired:
            self.fired = True
            self._request_shutdown()
        return True

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            if self.check_once():
                return


def _terminate_self(
    *,
    kill: Callable[[int, int], None] = os.kill,
    raise_signal: Callable[[int], None] = signal.raise_signal,
) -> None:
    """Ask ourselves to shut down, in-process.

    This used to be `os.kill(os.getpid(), SIGTERM)`, which on Windows is not a
    signal at all: per CPython's documentation, any sig other than
    `CTRL_C_EVENT` / `CTRL_BREAK_EVENT` there goes through `TerminateProcess`.
    That kills this process outright, so uvicorn's SIGTERM handler never runs
    — and per the note at the top of this module, that handler is the thing
    that releases the data directory's lock and removes the receipt. On
    Windows the fix for a leftover Core would have produced exactly the
    leftover lock it exists to prevent.

    `raise_signal` runs the handler in this process on both platforms. It is
    called from the watchdog's own thread; Python runs the Python-level
    handler on the main thread, which is where uvicorn installed it.

    `kill` stays a parameter only so a test can prove nobody reaches for it.
    """
    del kill
    raise_signal(signal.SIGTERM)
