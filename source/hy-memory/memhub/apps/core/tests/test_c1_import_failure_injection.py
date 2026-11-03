"""C1 failure injection: atomic receipt, disk-full, read-only source, rotation.

Evidence and its cursor must move together. A failure that lands between them has
to leave nothing behind, so a rerun can only merge, never duplicate. Source files
are opened read-only and never written; a rotated file is re-read without creating
a second copy of what was already committed.
"""

import sqlite3

import pytest

from one_memory.imports.access import (
    AuthorizedSourceFile,
    SourceAccessError,
    SourceAccessErrorCode,
)
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.runner import ImportRunner
from one_memory.imports.storage import EvidenceStore
from tests.test_c1_import_event_matrix import MatrixSource


def test_evidence_and_cursor_roll_back_together_on_write_failure(tmp_path, monkeypatch):
    """A failed Evidence commit must leave no Evidence and no cursor behind.

    sqlite3.Connection cannot be patched, so the injection is at the store's own
    write entry point, which is where a real disk-full/commit failure surfaces.
    """
    fixture = MatrixSource(tmp_path, "codex")
    fixture.write("session", ["alpha", "beta", "gamma"])

    original_put = EvidenceStore.put
    calls = {"count": 0}

    def failing_put(self, evidence, **kwargs):
        calls["count"] += 1
        if calls["count"] > 1:
            raise sqlite3.OperationalError("disk or write failure on the second row")
        return original_put(self, evidence, **kwargs)

    monkeypatch.setattr(EvidenceStore, "put", failing_put)
    failed = fixture.run()
    assert failed.status is ImportStatus.FAILED
    assert calls["count"] > 1, "the injection must actually reach a second evidence write"

    stored = fixture.evidence.count()
    cursors = fixture.jobs.get_source_cursors(user_id="local", source_id="codex")
    assert (stored, cursors) == (0, {}), "a failed commit must leave no evidence and no cursor"


def test_after_a_failed_commit_the_rerun_stores_each_record_once(tmp_path, monkeypatch):
    fixture = MatrixSource(tmp_path, "codex")
    fixture.write("session", ["alpha", "beta"])

    original_put = EvidenceStore.put
    state = {"armed": True}

    def failing_once(self, evidence, **kwargs):
        if state["armed"]:
            raise sqlite3.OperationalError("one synthetic write failure")
        return original_put(self, evidence, **kwargs)

    monkeypatch.setattr(EvidenceStore, "put", failing_once)
    assert fixture.run().status is ImportStatus.FAILED

    state["armed"] = False
    completed = fixture.run()
    assert completed.status is ImportStatus.COMPLETED
    assert completed.stored == 2
    assert fixture.evidence.count() == 2
    texts = {record.verbatim for record in fixture.evidence.list_extractable(limit=50)}
    assert texts == {"alpha", "beta"}


def test_a_read_only_source_file_is_imported_without_being_written(tmp_path):
    fixture = MatrixSource(tmp_path, "codex")
    path = fixture.write("session", ["readonly one", "readonly two"])
    before = path.stat()
    path.chmod(0o400)
    try:
        result = fixture.run()
    finally:
        path.chmod(0o600)
    assert result.status is ImportStatus.COMPLETED and result.stored == 2
    after = path.stat()
    assert (after.st_size, after.st_mtime_ns) == (
        before.st_size,
        before.st_mtime_ns,
    ), "importing must never write to a source file"


def test_a_rotated_file_is_reimported_without_duplicating_committed_records(tmp_path):
    fixture = MatrixSource(tmp_path, "codex")
    path = fixture.write("session", ["old one", "old two"])
    assert fixture.run().stored == 2

    rotated = path.with_name("rollout-session.jsonl.1")
    path.rename(rotated)
    fixture.write("session", ["new one"])
    after = fixture.run()

    assert after.stored == 1
    assert fixture.evidence.count() == 3
    texts = {record.verbatim for record in fixture.evidence.list_extractable(limit=50)}
    assert texts == {"old one", "old two", "new one"}


def test_a_removed_and_recreated_file_does_not_revive_as_new_evidence(tmp_path):
    fixture = MatrixSource(tmp_path, "codex")
    path = fixture.write("session", ["same text"])
    assert fixture.run().stored == 1

    path.unlink()
    fixture.write("session", ["same text"])
    rebuilt = fixture.run()
    assert fixture.evidence.count() == 1
    assert rebuilt.stored in (0, 1)


def test_evidence_and_job_stores_must_share_one_database(tmp_path):
    """Evidence and its cursor can only be atomic when they share one database."""
    fixture = MatrixSource(tmp_path, "codex")
    other = ImportJobStore(tmp_path / "other.sqlite3")

    with pytest.raises(ValueError):
        ImportRunner(evidence_store=fixture.evidence, job_store=other)


def test_a_full_disk_fails_the_job_and_keeps_the_cursor_replayable(tmp_path, monkeypatch):
    """ENOSPC during the commit must fail loudly, not look like a clean import.

    A job that reports success while nothing was written is the worst outcome:
    the cursor would then move past rows nobody ever stored.
    """
    fixture = MatrixSource(tmp_path, "codex")
    fixture.write("session", ["alpha", "beta", "gamma"])

    def full_disk(self, evidence, **kwargs):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(EvidenceStore, "put", full_disk)
    failed = fixture.run()
    monkeypatch.undo()

    assert failed.status is ImportStatus.FAILED
    assert fixture.evidence.count() == 0
    assert fixture.jobs.get_source_cursors(user_id="local", source_id="codex") == {}

    # The tail is still replayable: once space exists, every record lands once.
    recovered = fixture.run()
    assert recovered.status is ImportStatus.COMPLETED
    assert recovered.stored == 3
    assert fixture.evidence.count() == 3


def test_unavailable_source_file_is_reported_not_silently_dropped(tmp_path, monkeypatch):
    fixture = MatrixSource(tmp_path, "codex")
    path = fixture.write("session", ["alpha"])
    assert fixture.run().stored == 1
    fixture.write("session", ["new unreadable row"])

    original_open = AuthorizedSourceFile.open_binary

    def unavailable(source_file):
        if source_file.path == path:
            raise SourceAccessError(SourceAccessErrorCode.SOURCE_UNAVAILABLE)
        return original_open(source_file)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", unavailable)
    result = fixture.run()
    assert result.status is ImportStatus.COMPLETED
    assert result.errors >= 1, "an unreadable file must surface as a recorded error"
    assert fixture.evidence.count() == 1
