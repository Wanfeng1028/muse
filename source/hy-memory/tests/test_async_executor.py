"""Completed executor tasks must return or propagate their own exceptions."""

import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    "outcome",
    ["success", "value_error", "builtin_timeout", "asyncio_timeout",
     "concurrent_timeout", "cancelled"],
)
def test_guarded_future_completion(mode, outcome):
    # A regression can loop forever on an already-failed Future. Isolate each
    # case so the parent can stop it without leaving a busy thread in pytest.
    script = textwrap.dedent(
        """
        import asyncio
        import concurrent.futures
        import sys
        import time

        from hy_memory.utils.async_executor import (
            await_concurrent_future_guarded,
            concurrent_result_guarded,
        )

        mode, outcome = sys.argv[1:]
        errors = {
            "value_error": ValueError,
            "builtin_timeout": TimeoutError,
            "asyncio_timeout": asyncio.TimeoutError,
            "concurrent_timeout": concurrent.futures.TimeoutError,
        }

        def work():
            # Exceed several guard intervals: a wait timeout must not cancel
            # or resubmit the underlying task.
            time.sleep(0.08)
            if outcome in errors:
                raise errors[outcome]("task failed")
            return "completed"

        async def check():
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                if outcome == "cancelled":
                    future = concurrent.futures.Future()
                    assert future.cancel()
                else:
                    future = pool.submit(work)
                try:
                    if mode == "sync":
                        result = concurrent_result_guarded(
                            future, loop, guard_seconds=0.01,
                        )
                    else:
                        result = await await_concurrent_future_guarded(
                            future, loop, guard_seconds=0.01,
                        )
                except BaseException as exc:
                    if outcome == "cancelled":
                        expected = (concurrent.futures.CancelledError
                                    if mode == "sync" else asyncio.CancelledError)
                        assert isinstance(exc, expected), repr(exc)
                    else:
                        assert outcome in errors, repr(exc)
                        # wrap_future translates concurrent.futures.TimeoutError
                        # to asyncio.TimeoutError (distinct before Python 3.11).
                        expected = (asyncio.TimeoutError
                                    if mode == "async" and outcome == "concurrent_timeout"
                                    else errors[outcome])
                        assert isinstance(exc, expected), repr(exc)
                        assert str(exc) == "task failed"
                else:
                    assert outcome == "success"
                    assert result == "completed"

        asyncio.run(check())
        """
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, mode, outcome],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        pytest.fail(
            f"{mode}/{outcome}: completed task did not reach caller; "
            f"stdout={stdout!r}, stderr={stderr!r}"
        )
    assert process.returncode == 0, stderr
