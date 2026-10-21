"""Bug 2 real branch: an in-place same-length rewrite invalidates the anchor.

Three cases required with the approval: (a) recover instead of resetting to 0,
(b) real truncation / identity change / out-of-range still reset to 0, (c) the
recovered read must not duplicate stored evidence.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from one_memory.imports.access import AuthorizedSourceFile, AuthorizedSourceRoot
from one_memory.imports.adapters import ScanOptions
from one_memory.imports.discovery import discover_source_files
from one_memory.imports.grants import RootCandidateKind, SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.sources.common import jsonl_complete_tail, resume_checkpoint
from one_memory.imports.sources.workbuddy import create_workbuddy_adapter
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor


def _record(content: str) -> str:
    return json.dumps({"type": "user", "sessionId": "probe", "content": content}) + "\n"


def _write_fixture(root: Path) -> Path:
    projects = root / ".codebuddy" / "projects" / "qa"
    projects.mkdir(parents=True, exist_ok=True)
    transcript = projects / "session.jsonl"
    transcript.write_text(_record("alpha") + _record("bravo"))
    return transcript


def _entry(root: Path) -> AuthorizedSourceFile:
    grant = AuthorizedSourceRoot.grant(
        source_id="workbuddy", root=root / ".codebuddy", user_confirmed=True, home=root
    )
    return next(
        item
        for item in discover_source_files(grant, suffixes=frozenset({".jsonl"}), max_targets=10)
        if isinstance(item, AuthorizedSourceFile)
    )


def test_same_length_in_place_rewrite_recovers_instead_of_resetting_to_zero(tmp_path):
    transcript = _write_fixture(tmp_path)
    entry = _entry(tmp_path)
    checkpoint, anchor = jsonl_complete_tail(entry)
    from one_memory.imports.adapters import SourceCursor

    cursor = SourceCursor(
        file_key=entry.safe_id,
        file_identity=entry.file_identity,
        checkpoint=checkpoint,
        checkpoint_anchor=anchor,
        observed_size=entry.size,
        observed_modified_ns=entry.modified_ns,
        read_to_end=True,
    )

    before = transcript.stat()
    body = transcript.read_text()
    rewritten = body.replace("bravo", "braVo")
    assert len(rewritten) == len(body)
    transcript.write_text(rewritten)
    os.utime(transcript, ns=(before.st_atime_ns, before.st_mtime_ns))

    entry_after = _entry(tmp_path)
    assert entry_after.size == cursor.observed_size

    recovered = resume_checkpoint(entry_after, ScanOptions(cursors={entry_after.safe_id: cursor}))

    assert recovered is not None, "same-length rewrite must not reset to 0"
    assert recovered != "byte:0"
    offset = int(recovered.removeprefix("byte:"))
    assert 0 < offset <= entry_after.size
    # The recovered boundary must itself be a record boundary.
    with entry_after.admit().open_binary() as source:
        source.seek(offset - 1)
        assert source.read(1) == b"\n"


@pytest.mark.parametrize("case", ["truncated", "identity_changed", "checkpoint_past_file"])
def test_real_truncation_identity_change_and_out_of_range_still_reset(tmp_path, case):
    transcript = _write_fixture(tmp_path)
    entry = _entry(tmp_path)
    checkpoint, anchor = jsonl_complete_tail(entry)
    from one_memory.imports.adapters import SourceCursor

    cursor = SourceCursor(
        file_key=entry.safe_id,
        file_identity=entry.file_identity,
        checkpoint=checkpoint,
        checkpoint_anchor=anchor,
        observed_size=entry.size,
        observed_modified_ns=entry.modified_ns,
        read_to_end=True,
    )

    if case == "truncated":
        transcript.write_text(_record("alpha"))
    elif case == "checkpoint_past_file":
        cursor = cursor.model_copy(update={"checkpoint": f"byte:{entry.size + 9999}"})

    entry_after = _entry(tmp_path)
    if case == "identity_changed":
        cursor = cursor.model_copy(update={"file_identity": "different-inode"})

    assert (
        resume_checkpoint(entry_after, ScanOptions(cursors={entry_after.safe_id: cursor})) is None
    )


def test_recovered_read_does_not_duplicate_stored_evidence(tmp_path):
    root = tmp_path
    transcript = _write_fixture(root)
    database = root / "data" / "core.sqlite3"
    jobs = ImportJobStore(database)
    evidence = EvidenceStore(database)
    grants = SourceGrantStore(database, home=root)
    grants.grant(
        user_id="local",
        source_id="workbuddy",
        root=root / ".codebuddy",
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    source_root = grants.authorized_root(user_id="local", source_id="workbuddy")
    assert source_root is not None
    adapter = create_workbuddy_adapter(source_root)

    imports = ImportSupervisor(
        adapters={"workbuddy": adapter},
        evidence_store=evidence,
        job_store=jobs,
    )

    async def scenario():
        job = imports.create_job("workbuddy", operation="history")
        imports.enqueue(job.job_id)
        first = await imports.wait(job.job_id)
        assert first.status is ImportStatus.COMPLETED
        baseline = evidence.count()

        # Same-length in-place rewrite of the last line, then a second run.
        before = transcript.stat()
        body = transcript.read_text()
        rewritten = body.replace("bravo", "braVo")
        assert len(rewritten) == len(body)
        transcript.write_text(rewritten)
        os.utime(transcript, ns=(before.st_atime_ns, before.st_mtime_ns))

        job2 = imports.create_job("workbuddy", operation="history")
        imports.enqueue(job2.job_id)
        second = await imports.wait(job2.job_id)
        assert second.status is ImportStatus.COMPLETED
        return baseline, evidence.count()

    baseline, after = asyncio.run(scenario())

    # The rewritten tail is one record; dedupe must keep the total unchanged or
    # add at most that one changed record, never re-import the whole file.
    assert after - baseline <= 1, f"recovered read duplicated records: {baseline} -> {after}"
    print(f"DEDUP_EVIDENCE baseline={baseline} after={after} delta={after - baseline}")


@pytest.mark.parametrize(
    "payload,expected_boundaries",
    [
        (b'{"a":1}\n{"b":2}\n{"c":3}\n', {0, 8, 16}),
        (b'{"a":1}\r\n{"b":2}\r\n{"c":3}\r\n', {0, 9, 18}),
        (b'{"a":1}\n\n{"b":2}\n', {0, 8, 9}),
    ],
)
def test_rewind_lands_on_record_boundaries_for_lf_crlf_and_blank_lines(
    tmp_path, payload, expected_boundaries
):
    from one_memory.imports.sources.common import _rewind_to_line_start

    projects = tmp_path / ".codebuddy" / "projects" / "qa"
    projects.mkdir(parents=True, exist_ok=True)
    transcript = projects / "session.jsonl"
    transcript.write_bytes(payload)
    entry = _entry(tmp_path)

    seen = set()
    for offset in range(1, entry.size + 1):
        value = _rewind_to_line_start(entry, offset=offset)
        if value is None:
            continue
        offset_value = int(value.removeprefix("byte:"))
        seen.add(offset_value)
        if offset_value:
            assert entry.path.read_bytes()[offset_value - 1 : offset_value] == b"\n"

    assert seen == expected_boundaries
    assert _rewind_to_line_start(entry, offset=0) is None
    assert _rewind_to_line_start(entry, offset=entry.size + 1) is None


def test_rewind_backs_off_when_the_file_ends_mid_line(tmp_path):
    from one_memory.imports.sources.common import _rewind_to_line_start

    projects = tmp_path / ".codebuddy" / "projects" / "qa"
    projects.mkdir(parents=True, exist_ok=True)
    transcript = projects / "session.jsonl"
    transcript.write_bytes(b'{"a":1}\n{"b":2}\n{"c":3}')
    entry = _entry(tmp_path)

    assert _rewind_to_line_start(entry, offset=entry.size) == "byte:8"


def test_rewrite_then_append_never_resets_to_zero_and_stores_each_record_once(tmp_path):
    """The reviewer's sequence: rewrite -> sync -> append -> sync.

    A fix that only helps until the next append is not a fix, and a recovered
    re-read must not duplicate stored evidence.
    """
    transcript = _write_fixture(tmp_path)
    database = tmp_path / "data" / "core.sqlite3"
    jobs = ImportJobStore(database)
    evidence = EvidenceStore(database)
    grants = SourceGrantStore(database, home=tmp_path)
    grants.grant(
        user_id="local",
        source_id="workbuddy",
        root=tmp_path / ".codebuddy",
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    source_root = grants.authorized_root(user_id="local", source_id="workbuddy")
    assert source_root is not None

    imports = ImportSupervisor(
        adapters={"workbuddy": create_workbuddy_adapter(source_root)},
        evidence_store=evidence,
        job_store=jobs,
    )

    seen: list[str] = []

    async def sync_once():
        job = imports.create_job("workbuddy", operation="sync")
        imports.enqueue(job.job_id)
        result = await imports.wait(job.job_id)
        assert result.status is ImportStatus.COMPLETED
        stored = jobs.get_source_cursors(user_id="local", source_id="workbuddy", operation="sync")
        for value in stored.values():
            seen.append(value.checkpoint)
        return result

    async def scenario():
        await sync_once()
        baseline = evidence.count()

        before = transcript.stat()
        body = transcript.read_text()
        rewritten = body.replace("bravo", "braVo")
        assert len(rewritten) == len(body)
        transcript.write_text(rewritten)
        os.utime(transcript, ns=(before.st_atime_ns, before.st_mtime_ns))
        await sync_once()

        with transcript.open("a") as stream:
            stream.write(_record("charlie"))
        await sync_once()
        return baseline, evidence.count()

    baseline, after = asyncio.run(scenario())

    assert "byte:0" not in seen, f"cursor reset to 0 after a same-length rewrite: {seen}"
    # The rewritten tail is new content, so it is stored once more, and the
    # appended record once: two new rows, never a whole-file replay.
    assert after == baseline + 2, f"unexpected stored delta: {baseline} -> {after}"


def test_a_checkpoint_ahead_of_the_listed_size_still_resumes(tmp_path):
    """A host append leaves the cached listing size behind.

    A checkpoint after that stale size is not past the file, so it must resume
    instead of resetting to 0 (which would re-read the whole file).
    """
    from one_memory.imports.adapters import ScanOptions, SourceCursor
    from one_memory.imports.sources.common import jsonl_complete_tail, resume_checkpoint

    transcript = _write_fixture(tmp_path)
    entry = _entry(tmp_path)

    # The file grows after the listing captured its size.
    with transcript.open("a") as stream:
        stream.write(_record("appended later"))
    grown = _entry(tmp_path)
    checkpoint, anchor = jsonl_complete_tail(grown)

    # A cursor stored against the smaller, listed size.
    stale = SourceCursor(
        file_key=entry.safe_id,
        file_identity=entry.file_identity,
        checkpoint=checkpoint,
        checkpoint_anchor=anchor,
        observed_size=entry.size,
        observed_modified_ns=entry.modified_ns,
        read_to_end=True,
    )

    result = resume_checkpoint(entry, ScanOptions(cursors={stale.file_key: stale}))
    assert result == checkpoint, "a checkpoint ahead of the listed size must resume, not reset"


def test_truncation_and_identity_change_still_reset_with_the_new_view(tmp_path):
    from one_memory.imports.adapters import ScanOptions, SourceCursor
    from one_memory.imports.sources.common import jsonl_complete_tail, resume_checkpoint

    transcript = _write_fixture(tmp_path)
    entry = _entry(tmp_path)
    checkpoint, anchor = jsonl_complete_tail(entry)
    base = dict(
        file_key=entry.safe_id,
        file_identity=entry.file_identity,
        checkpoint=checkpoint,
        checkpoint_anchor=anchor,
        observed_size=entry.size,
        observed_modified_ns=entry.modified_ns,
        read_to_end=True,
    )
    # A real truncation must still reset to 0.
    transcript.write_text(_record("only one"))
    truncated = _entry(tmp_path)
    cursor = SourceCursor(**base)
    assert resume_checkpoint(truncated, ScanOptions(cursors={cursor.file_key: cursor})) is None
    # A changed identity must still reset to 0.
    moved = SourceCursor(**{**base, "file_identity": "different"})
    assert resume_checkpoint(entry, ScanOptions(cursors={moved.file_key: moved})) is None
