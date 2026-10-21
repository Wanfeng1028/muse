"""Explicit ownership of one admitted index worker; no migration or resource close."""

import asyncio
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from one_memory.retrieval.index_worker import IndexWorkResult
from one_memory.service_levels import ServiceLevel, service_level_context


class IndexWorker(Protocol):
    def run_once(self, *, cancel: threading.Event | None = None) -> IndexWorkResult: ...


@dataclass(frozen=True)
class IndexSupervisorSnapshot:
    state: Literal["new", "running", "stopping", "stopped"]
    last_result: str | None
    error_code: str | None
    slices: int
    failures: int
    thread_alive: bool


class RetrievalIndexSupervisor:
    """Single-use supervisor. Caller owns admission and closes vectors only after stop.

    Cancellation is cooperative: stop/wait cannot finish until a blocking native
    run_once returns. The lifecycle owner must drain before shutting its event loop.
    """

    def __init__(
        self,
        worker: IndexWorker,
        *,
        idle_wait_seconds: float = 5,
        failure_wait_seconds: float = 5,
        yield_wait_seconds: float = 0.05,
        max_consecutive_slices: int = 8,
        background_should_yield: Callable[[], bool] | None = None,
    ):
        for interval in (idle_wait_seconds, failure_wait_seconds, yield_wait_seconds):
            if (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not math.isfinite(interval)
                or not 0.001 <= interval <= 300
            ):
                raise ValueError("index_supervisor_invalid_config")
        if type(max_consecutive_slices) is not int or not 1 <= max_consecutive_slices <= 256:
            raise ValueError("index_supervisor_invalid_config")
        self._worker = worker
        self._idle_wait = idle_wait_seconds
        self._failure_wait = failure_wait_seconds
        self._yield_wait = yield_wait_seconds
        self._max_slices = max_consecutive_slices
        self._background_should_yield = background_should_yield or (lambda: False)
        self._condition = threading.Condition()
        self._cancel = threading.Event()
        self._wake = False
        self._thread: threading.Thread | None = None
        self._state: Literal["new", "running", "stopping", "stopped"] = "new"
        self._last_result: str | None = None
        self._error_code: str | None = None
        self._slices = self._failures = 0

    def start(self) -> None:
        with self._condition:
            if self._state != "new":
                raise RuntimeError("index_supervisor_already_started")
            thread = threading.Thread(target=self._run, name="retrieval-index", daemon=False)
            self._thread = thread
            self._state = "running"
            try:
                thread.start()
            except Exception:
                self._thread = None
                self._state = "stopped"
                self._error_code = "index_supervisor_start_failed"
                raise RuntimeError("index_supervisor_start_failed") from None

    def trigger(self) -> bool:
        with self._condition:
            if self._state != "running":
                return False
            self._wake = True
            self._condition.notify_all()
            return True

    def snapshot(self) -> IndexSupervisorSnapshot:
        with self._condition:
            return IndexSupervisorSnapshot(
                self._state,
                self._last_result,
                self._error_code,
                self._slices,
                self._failures,
                self._thread is not None and self._thread.is_alive(),
            )

    def _request_stop(self) -> None:
        with self._condition:
            self._cancel.set()
            self._wake = False
            if self._state == "new":
                self._state = "stopped"
            elif self._state == "running":
                self._state = "stopping"
            self._condition.notify_all()

    async def stop(self) -> None:
        self._request_stop()
        await self.wait()

    async def wait(self) -> None:
        """Cancellation requests shutdown, drains the real thread, then propagates."""
        cancelled = False
        while True:
            with self._condition:
                thread = self._thread
            if thread is None or not thread.is_alive():
                if thread is not None:
                    thread.join()
                break
            try:
                # No executor waiter or to_thread future to orphan on cancellation.
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                cancelled = True
                self._request_stop()
        if cancelled:
            raise asyncio.CancelledError

    def _pause(self, seconds: float, *, wakeable: bool) -> None:
        deadline = time.monotonic() + seconds
        with self._condition:
            while not self._cancel.is_set():
                if wakeable and self._wake:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            self._wake = False

    def _run(self) -> None:
        consecutive = 0
        try:
            while not self._cancel.is_set():
                if self._background_should_yield():
                    self._pause(self._yield_wait, wakeable=False)
                    continue
                result: str | None = None
                error: str | None = None
                try:
                    with service_level_context(ServiceLevel.BACKGROUND):
                        value = self._worker.run_once(cancel=self._cancel)
                    if not isinstance(value, IndexWorkResult) or value.state not in {
                        "idle",
                        "ready",
                        "excluded",
                        "blocked",
                        "cancelled",
                        "deferred",
                    }:
                        error = "index_worker_invalid_result"
                    else:
                        result = value.state
                        if result == "blocked":
                            error = "index_worker_blocked"
                except BaseException:
                    # Worker/provider exceptions must never escape via thread stderr.
                    error = "index_worker_failed"
                with self._condition:
                    self._last_result, self._error_code = result, error
                    self._slices += 1
                    if error is not None:
                        self._failures += 1
                if self._cancel.is_set():
                    break
                if error is not None:
                    consecutive = 0
                    self._pause(self._failure_wait, wakeable=False)
                elif result in {"ready", "excluded"}:
                    consecutive += 1
                    if consecutive >= self._max_slices:
                        consecutive = 0
                        self._pause(self._yield_wait, wakeable=False)
                else:
                    consecutive = 0
                    self._pause(self._idle_wait, wakeable=True)
        finally:
            with self._condition:
                self._state = "stopped"
                self._wake = False
                self._condition.notify_all()
