"""A Core that outlives its launcher makes the next launch impossible.

The lock on the data directory is held for as long as Core runs, so a Core
left behind by a Force Quit blocks every later start of the app. These pin the
rule that decides when Core gives up its own process.
"""

import os
import subprocess
import sys

from one_memory.parent_watchdog import ParentWatchdog
from one_memory.runtime import parent_pid, process_is_alive


def test_shutdown_is_requested_once_the_launcher_is_gone() -> None:
    requests: list[str] = []
    watchdog = ParentWatchdog(
        4242,
        is_alive=lambda _pid: False,
        request_shutdown=lambda: requests.append("shutdown"),
    )

    assert watchdog.check_once() is True
    # Asked for a second time, because the server takes a moment to unwind and
    # a repeated SIGTERM during that window would be an unclean exit.
    assert watchdog.check_once() is True
    assert requests == ["shutdown"]


def test_nothing_happens_while_the_launcher_lives() -> None:
    requests: list[str] = []
    watchdog = ParentWatchdog(
        4242,
        is_alive=lambda _pid: True,
        request_shutdown=lambda: requests.append("shutdown"),
    )

    assert watchdog.check_once() is False
    assert requests == []


def test_the_thread_fires_without_being_polled() -> None:
    fired = []
    watchdog = ParentWatchdog(
        4242,
        interval_seconds=0.01,
        is_alive=lambda _pid: False,
        request_shutdown=lambda: fired.append(True),
    )
    watchdog.start()
    try:
        deadline = 2.0
        waited = 0.0
        while not fired and waited < deadline:
            import time

            time.sleep(0.02)
            waited += 0.02
    finally:
        watchdog.stop()
    assert fired == [True]


def test_a_real_dead_process_is_seen_as_dead() -> None:
    finished = subprocess.Popen([sys.executable, "-c", ""])
    finished.wait()
    # A pid that has been reaped: the exact case a crashed app leaves behind.
    assert process_is_alive(finished.pid) is False
    assert process_is_alive(os.getpid()) is True


def test_only_a_launcher_named_by_the_app_is_used() -> None:
    # `os.getppid()` is useless here: the shipped Core is a PyInstaller binary,
    # so Python's parent is the bootloader, which survives the app's death.
    assert parent_pid({}) is None
    assert parent_pid({"ONE_MEMORY_PARENT_PID": ""}) is None
    assert parent_pid({"ONE_MEMORY_PARENT_PID": "not-a-pid"}) is None
    # 1 is launchd, which a Core is never a child of in the sense meant here;
    # accepting it would tie Core's life to a process that never exits.
    assert parent_pid({"ONE_MEMORY_PARENT_PID": "1"}) is None
    assert parent_pid({"ONE_MEMORY_PARENT_PID": "4242"}) == 4242
