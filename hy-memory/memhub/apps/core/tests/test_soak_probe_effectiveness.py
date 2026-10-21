"""The soak probe must observe the load it reports on.

The 8h soak drives writes in `soak_load_driver.py` but samples statistics in
`soak_probe.py`. `main_database_stats()` is process-local, so the sampler's
`open_connections` and `writer/reader waits` are always zero when the load
runs in another process — the trend looks healthy while measuring nothing.
These tests pin that the probe can carry its own in-process load, so the wait
figures it reports actually come from the writes it is measuring.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.contract, pytest.mark.serial]


def _probe_module():
    spec = importlib.util.spec_from_file_location(
        "soak_probe_under_test", ROOT / "scripts" / "soak_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_probe_reports_statistics_from_its_own_process(tmp_path) -> None:
    """Sampling an idle database must not itself fabricate wait activity.

    `main_database_stats()` is cumulative for the whole pytest process, so an
    absolute zero is not a valid expectation here. The stable property is that
    taking one sample does not add writer waits by itself.
    """
    module = _probe_module()
    path = tmp_path / "one-memory.sqlite3"
    module._probe_initialize(path)

    before = module._sample(path)["database"]["writer_waits"]
    sample = module._sample(path)

    assert sample["database"]["writer_waits"] == before


def test_probe_can_carry_in_process_load_so_waits_are_real(tmp_path) -> None:
    """With in-process writers, the probe must observe non-zero write volume.

    The load writes through the access layer in this same process, so the
    cumulative checkout counters the probe reads must move. If load is
    delegated to another process again, these counters stay at zero.
    """
    module = _probe_module()
    path = tmp_path / "one-memory.sqlite3"
    module._probe_initialize(path)

    before = module._sample(path)["database"]["writer_checkouts"]
    written = module._run_in_process_load(path, seconds=0.3, every=0.01, batch=4)
    after = module._sample(path)

    assert written >= 1, "the in-process load must actually write"
    assert after["queue"]["memory_write_jobs"].get("pending", 0) >= written
    assert after["database"]["writer_checkouts"] > before, (
        "in-process load must move the sampler's own checkout counter; a load "
        "delegated to another process would leave it unchanged"
    )


def test_probe_refuses_to_overwrite_an_existing_soak_file(tmp_path, capsys) -> None:
    """A duplicate supervisor must not erase an already-complete run.

    launchd restarted the strict soak command after its first eight-hour
    window finished; opening ``--out`` with ``"w"`` replaced 942 valid samples
    with a new run. The default path now has to fail before touching the file.
    """
    module = _probe_module()
    output = tmp_path / "soak-8h.jsonl"
    output.write_text("existing evidence\n", encoding="utf-8")

    code = module.main(
        [
            str(tmp_path / "one-memory.sqlite3"),
            "--seconds",
            "0",
            "--interval",
            "0.01",
            "--out",
            str(output),
        ]
    )

    assert code == 2
    assert output.read_text(encoding="utf-8") == "existing evidence\n"
    assert "soak output/archive already exists" in capsys.readouterr().err


def test_probe_archives_old_evidence_before_starting_fresh(tmp_path) -> None:
    """A fresh run must move the old evidence, never truncate it in place."""
    module = _probe_module()
    output = tmp_path / "soak-8h.jsonl"
    archive = tmp_path / "soak-8h.old.jsonl"
    output.write_text("old evidence\n", encoding="utf-8")

    code = module.main(
        [
            str(tmp_path / "one-memory.sqlite3"),
            "--seconds",
            "0",
            "--interval",
            "0.01",
            "--archive-existing",
            str(archive),
            "--out",
            str(output),
        ]
    )

    assert code == 0
    assert archive.read_text(encoding="utf-8") == "old evidence\n"
    assert output.read_text(encoding="utf-8") == ""


def test_probe_never_overwrites_an_archive_target(tmp_path, capsys) -> None:
    """The archive move is itself fail-closed; it must not replace a prior archive."""
    module = _probe_module()
    output = tmp_path / "soak-8h.jsonl"
    archive = tmp_path / "soak-8h.old.jsonl"
    output.write_text("new evidence\n", encoding="utf-8")
    archive.write_text("already archived\n", encoding="utf-8")

    code = module.main(
        [
            str(tmp_path / "one-memory.sqlite3"),
            "--seconds",
            "0",
            "--interval",
            "0.01",
            "--archive-existing",
            str(archive),
            "--out",
            str(output),
        ]
    )

    assert code == 2
    assert archive.read_text(encoding="utf-8") == "already archived\n"
    assert output.read_text(encoding="utf-8") == "new evidence\n"
    assert "choose a fresh path" in capsys.readouterr().err


def test_in_process_load_can_drive_concurrent_readers(tmp_path) -> None:
    """A writer-only load cannot show reader/writer contention.

    The objective asks whether reads starve under an import peak. One writer
    thread never makes a reader wait, so `reader_waits` would be structurally
    zero. The in-process load must be able to run readers alongside the writer
    so the read path is actually exercised.
    """
    module = _probe_module()
    path = tmp_path / "one-memory.sqlite3"
    module._probe_initialize(path)

    before = module._sample(path)["database"]["reader_checkouts"]
    module._run_in_process_load(
        path,
        seconds=0.4,
        every=0.01,
        batch=4,
        readers=4,
    )
    after = module._sample(path)

    assert after["database"]["reader_checkouts"] > before, (
        "concurrent readers must issue reads in this process, or the soak "
        "cannot observe reader/writer contention"
    )


def test_thread_count_is_retried_before_reporting_unknown(monkeypatch) -> None:
    """A transient `ps` failure must not poison the thread trend.

    macOS `ps -M` occasionally fails under load. Reporting -1 on the first
    failure injects a bogus value into the soak trend (observed once in 101
    samples). The probe retries once before giving up.
    """
    module = _probe_module()
    calls = {"n": 0}

    class _Result:
        stdout = "PID TT ...\n1 ...\n2 ...\n3 ...\n"

    def flaky_run(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient")
        return _Result()

    def no_proc_status(*args, **kwargs):
        raise OSError("synthetic non-Linux host")

    monkeypatch.setattr(module.subprocess, "run", flaky_run)
    # `_threads` opens procfs directly. Override the module's built-in lookup
    # so the macOS `ps` branch is exercised even on this Linux test host.
    monkeypatch.setattr(module, "open", no_proc_status, raising=False)

    assert module._threads() == 3
    assert calls["n"] == 2


def test_thread_count_reports_unknown_only_after_both_attempts(monkeypatch) -> None:
    module = _probe_module()

    def always_fail(*args, **kwargs):
        raise OSError("down")

    def no_proc_status(*args, **kwargs):
        raise OSError("synthetic non-Linux host")

    monkeypatch.setattr(module.subprocess, "run", always_fail)
    monkeypatch.setattr(module, "open", no_proc_status, raising=False)

    assert module._threads() == -1


def test_soak_verdict_is_incomplete_before_eight_hours() -> None:
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "verify_c2_slice", root / "scripts" / "verify_c2_slice.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module._soak_verdict(span_s=60, handle_spread=0, waits_zero=True).startswith(
        "verdict=incomplete"
    )
    assert module._soak_verdict(span_s=29_000, handle_spread=0, waits_zero=True).startswith(
        "verdict=complete-pass"
    )
    attention = module._soak_verdict(span_s=29_000, handle_spread=40, waits_zero=True)
    assert attention.startswith("verdict=complete-attention") and "handle_spread=40" in attention


def _soak_row(*, epoch: float, handles: int, threads: int, connections: int = 1) -> dict:
    return {
        "epoch": epoch,
        "process": {"file_handles": handles, "threads": threads},
        "database": {
            "open_connections": connections,
            "writer_wait_ms_max": 0.0,
            "reader_wait_ms_max": 0.0,
            "writer_checkouts": 1,
            "reader_checkouts": 1,
        },
        "disk": {"directory_bytes": 100},
        "queue": {"memory_write_jobs": {"pending": 1}},
    }


def _run_soak_summary(tmp_path: Path, rows: list[dict], *extra: str) -> subprocess.CompletedProcess:
    sample = tmp_path / "soak.jsonl"
    sample.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_c2_slice.py"),
            "--soak-summary",
            str(sample),
            *extra,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_soak_summary_rejects_negative_probe_values(tmp_path) -> None:
    """A failed probe value must not be reported as a successful summary."""
    result = _run_soak_summary(
        tmp_path,
        [
            _soak_row(epoch=1.0, handles=-1, threads=-1, connections=-1),
            _soak_row(epoch=2.0, handles=-1, threads=-1, connections=-1),
        ],
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "verdict=invalid" in result.stdout
    assert "file_handles" in result.stdout or "threads" in result.stdout


def test_soak_summary_rejects_a_malformed_sample(tmp_path) -> None:
    """A missing field is an invalid run, not a traceback or a green summary."""
    result = _run_soak_summary(
        tmp_path,
        [
            {
                "epoch": 1.0,
                "process": {"threads": 1},
                "database": {},
                "disk": {"directory_bytes": 1},
                "queue": {},
            }
        ],
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "verdict=invalid (malformed soak sample:" in result.stdout


def test_soak_summary_rejects_invalid_json_without_a_traceback(tmp_path) -> None:
    """A truncated JSONL sample is invalid input, not an uncaught parser error."""
    sample = tmp_path / "soak.jsonl"
    sample.write_text('{"epoch": 1.0\n', encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_c2_slice.py"),
            "--soak-summary",
            str(sample),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2, result.stdout + result.stderr
    assert "verdict=invalid (malformed JSONL soak sample:" in result.stdout
    assert "Traceback" not in result.stderr


def test_soak_summary_rejects_empty_and_non_object_samples(tmp_path) -> None:
    sample = tmp_path / "soak.jsonl"
    sample.write_text("", encoding="utf-8")
    empty = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_c2_slice.py"),
            "--soak-summary",
            str(sample),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert empty.returncode == 2
    assert "verdict=invalid (no soak samples)" in empty.stdout

    sample.write_text("[]\n", encoding="utf-8")
    non_object = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_c2_slice.py"),
            "--soak-summary",
            str(sample),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert non_object.returncode == 2
    assert "verdict=invalid (malformed soak sample: row is not an object)" in non_object.stdout


def test_soak_summary_rejects_a_non_integer_probe_value(tmp_path) -> None:
    """A stringly typed probe value is malformed, not a successful run."""
    row = _soak_row(epoch=1.0, handles="25", threads=10)
    result = _run_soak_summary(tmp_path, [row])

    assert result.returncode == 2, result.stdout + result.stderr
    assert "file_handles has a non-integer or negative sample" in result.stdout


def test_soak_summary_requires_a_complete_window_when_asked(tmp_path) -> None:
    """Diagnostic mode stays readable, but acceptance mode must fail short runs."""
    rows = [
        _soak_row(epoch=1.0, handles=5, threads=1),
        _soak_row(epoch=2.0, handles=5, threads=1),
    ]

    diagnostic = _run_soak_summary(tmp_path, rows)
    assert diagnostic.returncode == 0
    assert "verdict=incomplete" in diagnostic.stdout

    required = _run_soak_summary(tmp_path, rows, "--require-complete")
    assert required.returncode == 3, required.stdout + required.stderr
    assert "verdict=incomplete" in required.stdout


def test_soak_summary_can_require_a_recorded_successful_exit(tmp_path) -> None:
    """A completed sample window is not proof that the soak process exited 0."""
    rows = [
        _soak_row(epoch=1.0, handles=5, threads=1),
        _soak_row(epoch=28_802.0, handles=5, threads=1),
    ]
    exit_code = tmp_path / "soak.exit"

    missing = _run_soak_summary(
        tmp_path,
        rows,
        "--require-complete",
        "--exit-code-file",
        str(exit_code),
    )
    assert missing.returncode == 2
    assert "missing soak exit code" in missing.stdout

    exit_code.write_text("9\n", encoding="utf-8")
    failed = _run_soak_summary(
        tmp_path,
        rows,
        "--require-complete",
        "--exit-code-file",
        str(exit_code),
    )
    assert failed.returncode == 2
    assert "soak process exited 9" in failed.stdout

    exit_code.write_text("0\n", encoding="utf-8")
    passed = _run_soak_summary(
        tmp_path,
        rows,
        "--require-complete",
        "--exit-code-file",
        str(exit_code),
    )
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert "verdict=complete-pass" in passed.stdout


def test_exit_code_file_without_complete_mode_is_a_usage_error(tmp_path) -> None:
    """Silently ignoring the exit-code input would make the CLI look stronger."""
    result = _run_soak_summary(
        tmp_path,
        [_soak_row(epoch=1.0, handles=5, threads=1)],
        "--exit-code-file",
        str(tmp_path / "soak.exit"),
    )

    assert result.returncode == 2
    assert "--exit-code-file requires --require-complete" in (result.stdout + result.stderr)


def test_reader_wait_counter_is_not_a_blind_zero(tmp_path, monkeypatch) -> None:
    """The soak's `reader_waits=0` must be falsifiable.

    The 8h soak reports the cumulative reader-wait counter. If that counter
    cannot become non-zero when a reader is genuinely held out of a pool of
    one, a healthy zero is indistinguishable from a broken probe and the soak
    proves nothing about read starvation. This is the positive control for
    that metric, exercised through the same `MainDatabase.stats()` the probe
    reads.
    """
    from one_memory.database_access import close_main_databases, main_database

    monkeypatch.setenv("ONE_MEMORY_READER_POOL_SIZE", "1")
    close_main_databases()
    database = main_database(tmp_path / "one-memory.sqlite3")
    with database.write() as connection, connection:
        connection.execute("CREATE TABLE t (value INTEGER)")
        connection.execute("INSERT INTO t VALUES (1)")

    holding = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def hold_the_only_reader() -> None:
        with database.read() as connection:
            connection.execute("SELECT value FROM t").fetchone()
            holding.set()
            release.wait(10)

    def wait_for_a_reader() -> None:
        with database.read() as connection:
            connection.execute("SELECT value FROM t").fetchone()
        finished.set()

    holder = threading.Thread(target=hold_the_only_reader, daemon=True)
    holder.start()
    assert holding.wait(10)

    waiter = threading.Thread(target=wait_for_a_reader, daemon=True)
    waiter.start()
    deadline = time.monotonic() + 5
    while database.stats().readers_waiting == 0 and time.monotonic() < deadline:
        time.sleep(0.001)
    assert database.stats().readers_waiting > 0, "the second reader never queued"

    release.set()
    assert finished.wait(10)
    holder.join(10)
    waiter.join(10)
    stats = database.stats()
    assert stats.reader_waits > 0, "a queued reader was never counted as a wait"
    assert stats.reader_wait_ms_max > 0.0
    close_main_databases()


def test_soak_sample_exposes_the_nonzero_reader_wait(tmp_path, monkeypatch) -> None:
    """The probe's JSON, not only the access layer, must carry the real wait."""
    from one_memory.database_access import close_main_databases, main_database

    probe = _probe_module()
    monkeypatch.setenv("ONE_MEMORY_READER_POOL_SIZE", "1")
    close_main_databases()
    database = main_database(tmp_path / "one-memory.sqlite3")
    with database.write() as connection, connection:
        connection.execute("CREATE TABLE t (value INTEGER)")
        connection.execute("INSERT INTO t VALUES (1)")

    holding = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def hold() -> None:
        with database.read() as connection:
            connection.execute("SELECT value FROM t").fetchone()
            holding.set()
            release.wait(10)

    def wait() -> None:
        with database.read() as connection:
            connection.execute("SELECT value FROM t").fetchone()
        finished.set()

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    assert holding.wait(10)
    waiter = threading.Thread(target=wait, daemon=True)
    waiter.start()
    deadline = time.monotonic() + 5
    while database.stats().readers_waiting == 0 and time.monotonic() < deadline:
        time.sleep(0.001)
    assert database.stats().readers_waiting > 0
    release.set()
    assert finished.wait(10)
    holder.join(10)
    waiter.join(10)

    sample = probe._sample(tmp_path / "one-memory.sqlite3")

    assert int(sample["database"]["reader_waits"]) > 0
    assert float(sample["database"]["reader_wait_ms_max"]) > 0.0
    close_main_databases()
