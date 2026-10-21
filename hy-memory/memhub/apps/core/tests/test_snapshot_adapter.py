"""Selection-only binding reopens checksum-verified frozen copies.

The tests use the real readers and runner with temporary native-format fixtures.
No private history, models, or host installations are used.
"""

import asyncio
import json
import os
import shutil
import sqlite3
import stat
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from one_memory.imports.access import (
    AuthorizedSourceFile,
    SourceAccessError,
    SourceAccessErrorCode,
)
from one_memory.imports.adapters import (
    ScanFailure,
    ScanIssueCode,
    ScannedEvidence,
    ScanOptions,
    ScanSkip,
)
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.models import EvidenceOrigin, WrittenBy
from one_memory.imports.runner import ImportRunner
from one_memory.imports.snapshot_adapter import create_snapshot_adapter
from one_memory.imports.snapshots import (
    SnapshotError,
    SnapshotErrorCode,
    SnapshotLimits,
    SnapshotManifest,
    SourceSnapshotStore,
)
from one_memory.imports.sources.common import JsonlSourceAdapter, ParsedSkip
from one_memory.imports.sources.registry import build_source_catalog
from one_memory.imports.storage import EvidenceStore


@pytest.fixture(autouse=True)
def cleanup_readonly_fixtures(tmp_path):
    yield
    for directory, _, files, descriptor in os.fwalk(tmp_path, follow_symlinks=False):
        os.fchmod(descriptor, 0o700)
        for filename in files:
            path = Path(directory) / filename
            details = path.lstat()
            if stat.S_ISREG(details.st_mode) and details.st_nlink == 1:
                os.chmod(path, 0o600)
    shutil.rmtree(tmp_path)


class Fixture:
    def __init__(self, tmp_path, source="claude-code", *, operation="history"):
        home = tmp_path / "home"
        (home / ".cursor").mkdir(parents=True)
        self.registration = build_source_catalog(
            home=home, environment={}, import_root=tmp_path / "exports"
        )[source]
        self.root = self.registration.candidate.path
        self.root.mkdir(parents=True, exist_ok=True)
        self.directory = tmp_path / "snapshots"
        self.directory.mkdir(mode=0o700)
        database = tmp_path / "core.sqlite3"
        self.jobs = ImportJobStore(database)
        self.evidence = EvidenceStore(database)
        self.grants = SourceGrantStore(database, home=home)
        self.grants.grant(
            user_id="local",
            source_id=source,
            root=self.root,
            candidate_kind=self.registration.candidate.kind,
        )
        self.grant = self.grants.authorized_root(user_id="local", source_id=source)
        assert self.grant is not None
        self.job = self.jobs.create(
            user_id="local",
            source_id=source,
            operation=operation,
        )
        self.path = self.root / (
            "projects/acme/agent-transcripts/session/session.jsonl"
            if source == "cursor"
            else "project/rollout-session.jsonl"
        )

    def adapter(self, **kwargs):
        return create_snapshot_adapter(
            registration=self.registration,
            grant=self.grant,
            job=self.job,
            job_store=self.jobs,
            snapshot_directory=self.directory,
            **kwargs,
        )

    def manifest(self):
        return SnapshotManifest.model_validate_json(
            (self.directory / self.job.job_id / "manifest.json").read_bytes()
        )

    def binding(self):
        with self.jobs._connect() as connection:
            return connection.execute(
                "SELECT job_id, selection_id FROM import_job_snapshots WHERE job_id=?",
                (self.job.job_id,),
            ).fetchone()

    def append(self, text, *, role="user", path=None):
        source = self.job.source_id
        if source == "codex":
            record = {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": role,
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        elif source == "cursor":
            record = {"role": role, "message": {"content": [{"type": "text", "text": text}]}}
        elif source.endswith("-export"):
            record = {
                "conversation_id": "exported",
                "message_id": text,
                "role": role,
                "written_by": "person" if role == "user" else "agent",
                "verbatim": text,
                "record_type": "exported_message",
            }
        else:
            record = {"type": role, "message": {"content": text}}
        path = path or self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")


async def scan(adapter, options=None):
    return [event async for event in adapter.scan(options or ScanOptions())]


def test_cursor_ignores_out_of_scope_skill_symlinks_but_not_history_links(tmp_path):
    fixture = Fixture(tmp_path, "cursor")
    fixture.append("selected history")
    outside = fixture.root / "skills-src/vendor/.opencode"
    outside.mkdir(parents=True)
    (outside / "skills").symlink_to(fixture.root / "outside-secret", target_is_directory=True)
    events = asyncio.run(scan(fixture.adapter()))
    assert [event.evidence.verbatim for event in evidence(events)] == ["selected history"]
    assert all(entry.relative_path.startswith("projects/") for entry in fixture.manifest().files)


def evidence(events):
    return [event for event in events if isinstance(event, ScannedEvidence)]


@pytest.mark.parametrize("source", ["claude-code", "codex", "cursor", "workbuddy"])
def test_normal_readers_get_only_frozen_bytes_and_preserve_origin(tmp_path, monkeypatch, source):
    fixture = Fixture(tmp_path, source)
    fixture.append("First human text")
    fixture.append("Agent proposal", role="assistant")
    expected = evidence(asyncio.run(scan(fixture.registration.create_adapter(fixture.grant))))
    original = fixture.grant.authorize_file(fixture.path)
    real_capture = SourceSnapshotStore.capture

    def append_after_capture(store, **kwargs):
        result = real_capture(store, **kwargs)
        fixture.append("Outside the approved extent")
        fixture.append(
            "New file outside the manifest", path=fixture.path.with_name("rollout-new.jsonl")
        )
        return result

    monkeypatch.setattr(SourceSnapshotStore, "capture", append_after_capture)
    result = evidence(asyncio.run(scan(fixture.adapter())))

    assert len(result) == 2
    assert [item.evidence for item in result] == [item.evidence for item in expected]
    assert [item.evidence.written_by for item in result] == [WrittenBy.PERSON, WrittenBy.AGENT]
    assert [item.cursor for item in result] == [item.cursor for item in expected]
    assert all(item.cursor.file_key == original.safe_id for item in result)
    assert all(item.cursor.file_identity == original.file_identity for item in result)
    assert all(item.cursor.observed_size == original.size for item in result)
    assert str(fixture.directory) not in repr(result)
    manifest = fixture.manifest()
    assert manifest.snapshot_id == fixture.job.job_id
    assert [item.relative_path for item in manifest.files] == [original.relative_path.as_posix()]
    assert manifest.files[0].source_size < fixture.path.stat().st_size
    assert fixture.binding()["selection_id"]


@pytest.mark.parametrize("source", ["claude-code", "codex", "cursor", "workbuddy"])
def test_restart_maps_original_cursors_and_reopens_without_reading_or_copying_live_source(
    tmp_path, monkeypatch, source
):
    fixture = Fixture(tmp_path, source)
    fixture.append("Already processed")
    fixture.append("Still pending", role="assistant")
    first = evidence(asyncio.run(scan(fixture.adapter(), ScanOptions(max_messages=1))))[0]
    selection_id = fixture.binding()["selection_id"]
    fixture.append("Appended later")
    fixture.jobs = ImportJobStore(fixture.jobs.database_path)
    fixture.grant = fixture.grants.authorized_root(user_id="local", source_id=source)
    original_open = AuthorizedSourceFile.open_binary

    def snapshot_only(source_file):
        assert source_file.root != fixture.root, "Restart reopened live history"
        return original_open(source_file)

    def no_recapture(*args, **kwargs):
        pytest.fail("Committed job must call reopen, not capture")

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", snapshot_only)
    monkeypatch.setattr(SourceSnapshotStore, "capture", no_recapture)
    options = ScanOptions(cursors={first.cursor.file_key: first.cursor})
    remaining = evidence(asyncio.run(scan(fixture.adapter(), options)))
    assert [item.evidence.verbatim for item in remaining] == ["Still pending"]
    assert fixture.binding()["selection_id"] == selection_id
    last = remaining[0].cursor
    assert (
        evidence(asyncio.run(scan(fixture.adapter(), ScanOptions(cursors={last.file_key: last}))))
        == []
    )


def test_selectors_use_codex_predicate_and_workbuddy_metadata_without_opening_configs(
    tmp_path, monkeypatch
):
    fixture = Fixture(tmp_path, "workbuddy")
    fixture.append("Metadata must preserve project")
    metadata = fixture.path.with_suffix(".meta.json")
    metadata.write_text(
        json.dumps({"sourceConversationId": "rollout-session", "cwd": "/fixture/acme"})
    )
    for name in ("credentials.json", "settings.json", "config.toml", "archive.zip"):
        (fixture.root / name).write_text("must-not-open")
    opened = set()
    original_open = AuthorizedSourceFile.open_binary

    def observe(source_file):
        if source_file.root == fixture.root:
            opened.add(source_file.relative_path.as_posix())
        return original_open(source_file)

    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", observe)
    rows = evidence(asyncio.run(scan(fixture.adapter())))
    assert rows[0].evidence.project == "acme"
    assert rows[0].evidence.workspace is not None
    assert opened == {
        fixture.path.relative_to(fixture.root).as_posix(),
        metadata.relative_to(fixture.root).as_posix(),
    }


def test_codex_copies_only_its_original_suffixes_and_filename_predicate(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path, "codex")
    fixture.append("Selected")
    fixture.append("Rejected", path=fixture.root / "not-a-rollout.jsonl")
    (fixture.root / "rollout-credentials.json").write_text("must-not-open")
    original_open = AuthorizedSourceFile.open_binary
    predicates = []
    real_factory = fixture.registration.create_adapter

    def create(grant):
        adapter = real_factory(grant)
        assert isinstance(adapter, JsonlSourceAdapter)
        predicates.append(adapter.file_predicate)
        return adapter

    fixture.registration = replace(fixture.registration, create_adapter=create)
    real_capture = SourceSnapshotStore.capture

    def capture(store, **kwargs):
        assert kwargs["file_predicate"] is predicates[0]
        assert set(kwargs["suffix_modes"]) == {".jsonl"}
        return real_capture(store, **kwargs)

    def observe(source_file):
        if source_file.root == fixture.root:
            assert source_file.path == fixture.path
        return original_open(source_file)

    monkeypatch.setattr(SourceSnapshotStore, "capture", capture)
    monkeypatch.setattr(AuthorizedSourceFile, "open_binary", observe)
    assert [item.evidence.verbatim for item in evidence(asyncio.run(scan(fixture.adapter())))] == [
        "Selected"
    ]


def test_cursor_exact_project_root_includes_native_transcripts_without_sibling_projects(tmp_path):
    fixture = Fixture(tmp_path, "cursor")
    selected = fixture.root / "agent-transcripts/native/native.jsonl"
    fixture.append("Only this project's native text", path=selected)
    fixture.append("Unrelated JSONL", path=fixture.root / "notes/other.jsonl")
    outside = tmp_path / "another-project"
    outside.mkdir()
    (outside / "secret.jsonl").write_text("not authorized")
    (fixture.root / "skills").symlink_to(outside, target_is_directory=True)
    original_hash = selected.read_bytes()
    actual = evidence(asyncio.run(scan(fixture.adapter())))
    assert [item.evidence.verbatim for item in actual] == ["Only this project's native text"]
    assert selected.read_bytes() == original_hash
    assert [item.relative_path for item in fixture.manifest().files] == [
        "agent-transcripts/native/native.jsonl"
    ]
    fixture.append("Later native text", path=selected)
    resumed = evidence(asyncio.run(scan(fixture.adapter())))
    assert [item.evidence.verbatim for item in resumed] == ["Only this project's native text"]


@pytest.mark.parametrize("storage", ["store", "legacy"])
def test_cursor_native_sqlite_resume_and_later_rows_stay_outside_snapshot(tmp_path, storage):
    fixture = Fixture(tmp_path, "cursor")
    database = fixture.root / (
        "chats/acme/native/store.db" if storage == "store" else "User/globalStorage/state.vscdb"
    )
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        if storage == "store":
            connection.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
            connection.execute("CREATE TABLE meta (key TEXT, value TEXT)")
            connection.execute(
                "INSERT INTO meta VALUES (?, ?)",
                ("0", json.dumps({"agentId": "stable-snapshot-agent"}).encode().hex()),
            )
            for index in (1, 2):
                connection.execute(
                    "INSERT INTO blobs VALUES (?,?)",
                    (str(index), json.dumps({"role": "user", "content": f"Text {index}"})),
                )
        else:
            connection.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
            connection.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
            connection.execute(
                "INSERT INTO ItemTable VALUES (?,?)",
                (
                    "composer.composerHeaders",
                    json.dumps({"allComposers": [{"composerId": "native", "isSubagent": False}]}),
                ),
            )
            for index in (1, 2):
                connection.execute(
                    "INSERT INTO cursorDiskKV VALUES (?,?)",
                    (f"bubbleId:native:{index}", json.dumps({"type": 1, "text": f"Text {index}"})),
                )
    (fixture.root / "unrelated.db").write_bytes(b"must not back up")
    (fixture.root / "settings.json").write_bytes(b"must not copy")
    fixture.append("Non-native JSONL", path=fixture.root / "unrelated.jsonl")
    expected = evidence(asyncio.run(scan(fixture.registration.create_adapter(fixture.grant))))
    if storage == "store":
        assert {item.evidence.conversation_id for item in expected} == {"stable-snapshot-agent"}
    first = evidence(asyncio.run(scan(fixture.adapter(), ScanOptions(max_messages=1))))[0]
    assert first == expected[0]
    with sqlite3.connect(database) as connection:
        if storage == "store":
            connection.execute(
                "INSERT INTO blobs VALUES (?,?)",
                ("3", json.dumps({"role": "user", "content": "Later"})),
            )
        else:
            connection.execute(
                "INSERT INTO cursorDiskKV VALUES (?,?)",
                ("bubbleId:native:3", json.dumps({"type": 1, "text": "Later"})),
            )
    remaining = evidence(
        asyncio.run(
            scan(fixture.adapter(), ScanOptions(cursors={first.cursor.file_key: first.cursor}))
        )
    )
    assert remaining == expected[1:]
    assert [entry.relative_path for entry in fixture.manifest().files] == [
        database.relative_to(fixture.root).as_posix()
    ]


def test_capture_failure_is_an_issue_and_failed_job_never_successful_empty_import(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.append("Too large for the configured snapshot limit")
    runner = ImportRunner(evidence_store=fixture.evidence, job_store=fixture.jobs)
    with pytest.raises(SnapshotError) as failure:
        asyncio.run(
            runner.run(
                adapter=fixture.adapter(limits=SnapshotLimits(max_file_bytes=1)),
                job_id=fixture.job.job_id,
            )
        )
    assert failure.value.code is SnapshotErrorCode.FILE_LIMIT
    assert fixture.jobs.require(fixture.job.job_id).status is ImportStatus.FAILED
    assert fixture.jobs.list_issues(fixture.job.job_id)[-1].reason == SnapshotErrorCode.FILE_LIMIT
    assert fixture.evidence.count() == 0
    assert fixture.binding()["selection_id"]
    assert not (fixture.directory / fixture.job.job_id).exists()
    fixture.append("Must not be silently included on retry")
    with pytest.raises(SnapshotError) as retry:
        asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert retry.value.code is SnapshotErrorCode.INCOMPLETE
    assert fixture.jobs.require(fixture.job.job_id).status is ImportStatus.FAILED
    assert fixture.evidence.count() == 0
    fixture.jobs.transition(fixture.job.job_id, ImportStatus.CANCELLED)
    fixture.job = fixture.jobs.create(
        user_id="local",
        source_id=fixture.job.source_id,
    )
    completed = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert completed.status is ImportStatus.COMPLETED
    assert completed.stored == 2


def test_modified_or_missing_committed_snapshot_never_recaptures(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    fixture.append("Captured")
    asyncio.run(scan(fixture.adapter()))
    copied = (
        fixture.directory / fixture.job.job_id / "files" / fixture.path.relative_to(fixture.root)
    )
    original = copied.read_bytes()
    modified_ns = copied.stat().st_mtime_ns
    corrupted = bytes([original[0] ^ 1]) + original[1:]
    copied.chmod(0o600)
    copied.write_bytes(corrupted)
    os.utime(copied, ns=(modified_ns, modified_ns))
    copied.chmod(0o400)

    def never_recapture(*args, **kwargs):
        pytest.fail("A committed selection binding must reopen, not recapture")

    monkeypatch.setattr(SourceSnapshotStore, "capture", never_recapture)
    with pytest.raises(SnapshotError) as changed:
        asyncio.run(scan(fixture.adapter()))
    assert changed.value.code is SnapshotErrorCode.CHECKSUM_MISMATCH
    (fixture.directory / fixture.job.job_id / "manifest.json").unlink()
    with pytest.raises(SnapshotError) as missing:
        asyncio.run(scan(fixture.adapter()))
    assert missing.value.code is SnapshotErrorCode.INCOMPLETE


def test_revoke_after_capture_allows_bound_job_to_finish_but_blocks_new_binding(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.append("Authorized")
    fixture.append("Do not emit after revocation")

    async def scenario():
        stream = fixture.adapter().scan(ScanOptions())
        async for event in stream:
            if isinstance(event, ScannedEvidence):
                break
        fixture.grants.revoke(user_id="local", source_id=fixture.job.source_id)
        remaining = [event async for event in stream]
        assert any(
            isinstance(event, ScannedEvidence)
            and event.evidence.verbatim == "Do not emit after revocation"
            for event in remaining
        )
        assert (
            fixture.grants.authorized_root(user_id="local", source_id=fixture.job.source_id) is None
        )

    asyncio.run(scenario())


def test_async_cancellation_waits_for_capture_cleanup_even_when_cancelled_twice(
    tmp_path, monkeypatch
):
    import one_memory.imports.snapshots as snapshots

    fixture = Fixture(tmp_path)
    fixture.append("Text" * (snapshots._CHUNK_BYTES // 2))
    partial_written, allow_cleanup, worker_stopped = Event(), Event(), Event()
    real_copy = snapshots._copy_extent
    real_write = snapshots._write_chunk

    def hold_partial(sink, chunk):
        real_write(sink, chunk)
        if len(chunk) == snapshots._CHUNK_BYTES:
            partial_written.set()
            assert allow_cleanup.wait(10)

    def observe_worker(*args, **kwargs):
        try:
            return real_copy(*args, **kwargs)
        finally:
            worker_stopped.set()

    monkeypatch.setattr(snapshots, "_write_chunk", hold_partial)
    monkeypatch.setattr(snapshots, "_copy_extent", observe_worker)

    async def scenario():
        task = asyncio.create_task(scan(fixture.adapter()))
        try:
            assert await asyncio.to_thread(partial_written.wait, 10)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0.03)
            assert not task.done(), "Cancellation returned before the writer stopped"
            assert not worker_stopped.is_set()
        finally:
            allow_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert worker_stopped.is_set()
        assert not list(fixture.directory.glob("*.pending"))
        assert not (fixture.directory / fixture.job.job_id).exists()

    asyncio.run(scenario())
    with pytest.raises(SnapshotError) as retry:
        asyncio.run(scan(fixture.adapter()))
    assert retry.value.code is SnapshotErrorCode.INCOMPLETE


def test_sync_job_uses_original_live_adapter_and_existing_runner_is_only_evidence_writer(tmp_path):
    fixture = Fixture(tmp_path, operation="sync")
    fixture.append("Initial")
    adapter = fixture.adapter()
    assert isinstance(adapter, JsonlSourceAdapter)
    fixture.append("Added after adapter creation")
    seen = []
    runner = ImportRunner(
        evidence_store=fixture.evidence, job_store=fixture.jobs, on_evidence=seen.append
    )
    completed = asyncio.run(runner.run(adapter=adapter, job_id=fixture.job.job_id))
    assert completed.stored == 2
    assert len(seen) == fixture.evidence.count() == 2
    assert not list(fixture.directory.iterdir())
    with fixture.jobs._connect() as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='import_job_snapshots'"
            ).fetchone()
            is None
        )


def test_history_returns_only_existing_evidence_and_scan_does_not_write_memory(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.append("Raw person turn")
    fixture.append("Raw agent proposal", role="assistant")
    result = evidence(asyncio.run(scan(fixture.adapter())))
    assert fixture.evidence.count() == 0
    assert len(result) == 2
    assert (
        result[0].evidence.origin_meta[EvidenceOrigin.FILE].raw_meta["file_key"]
        == result[0].cursor.file_key
    )
    seen = []
    runner = ImportRunner(
        evidence_store=fixture.evidence, job_store=fixture.jobs, on_evidence=seen.append
    )
    completed = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert completed.stored == len(seen) == fixture.evidence.count() == 2
    assert [row.verbatim for row in seen] == [row.evidence.verbatim for row in result]


@pytest.mark.parametrize(
    "source", ["chatgpt-export", "claude-export", "generic-export", "memory-content-export"]
)
def test_normalized_export_jsonl_uses_existing_reader(tmp_path, source):
    fixture = Fixture(tmp_path, source)
    fixture.append("Exported text")
    result = evidence(asyncio.run(scan(fixture.adapter())))
    assert len(result) == 1
    assert result[0].evidence.verbatim == "Exported text"


def test_skip_cursors_are_restored_as_well_as_evidence(tmp_path):
    fixture = Fixture(tmp_path, "codex")
    fixture.append("Visible")
    with fixture.path.open("a") as stream:
        stream.write(json.dumps({"type": "response_item", "payload": {"type": "reasoning"}}) + "\n")
    result = asyncio.run(scan(fixture.adapter()))
    skipped = next(event for event in result if isinstance(event, ScanSkip))
    original = fixture.grant.authorize_file(fixture.path)
    assert skipped.cursor.file_identity == original.file_identity
    assert skipped.cursor.observed_size == original.size
    assert (
        evidence(
            asyncio.run(
                scan(
                    fixture.adapter(),
                    ScanOptions(cursors={skipped.cursor.file_key: skipped.cursor}),
                )
            )
        )
        == []
    )


def test_cancellation_during_cursor_discovery_awaits_internal_reader_thread(tmp_path, monkeypatch):
    import one_memory.imports.sources.cursor_unified as cursor

    fixture = Fixture(tmp_path, "cursor")
    fixture.append("Captured text")
    entered, release, stopped = Event(), Event(), Event()
    real_select = cursor._select_transcript_files

    def blocked_select(grant):
        entered.set()
        try:
            assert release.wait(10)
            return real_select(grant)
        finally:
            stopped.set()

    monkeypatch.setattr(cursor, "_select_transcript_files", blocked_select)

    async def scenario():
        task = asyncio.create_task(scan(fixture.adapter()))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            task.cancel()
            await asyncio.sleep(0.03)
            assert not task.done(), "Wrapper released a still-active internal reader"
            assert not stopped.is_set()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert stopped.is_set()

    asyncio.run(scenario())


def test_unsupported_source_keeps_exact_live_adapter_and_primary_mismatch_fails_closed(tmp_path):
    fixture = Fixture(tmp_path, "codex")
    fixture.append("Private bytes must not reach the wrong reader")

    class UnrecognizedAdapter:
        descriptor = fixture.registration.descriptor

        async def detect(self):
            return True

        async def scan(self, options):
            pytest.fail("A primary source must never fall back to an unrecognized reader")
            yield

    unknown = UnrecognizedAdapter()
    fixture.registration = replace(fixture.registration, create_adapter=lambda _: unknown)
    adapter = fixture.adapter()
    runner = ImportRunner(evidence_store=fixture.evidence, job_store=fixture.jobs)
    with pytest.raises(SnapshotError) as failed:
        asyncio.run(runner.run(adapter=adapter, job_id=fixture.job.job_id))
    assert failed.value.code is SnapshotErrorCode.UNSUPPORTED_MODE
    assert fixture.jobs.require(fixture.job.job_id).status is ImportStatus.FAILED
    assert fixture.evidence.count() == 0
    assert not list(fixture.directory.iterdir())

    unsupported = Fixture(tmp_path / "unsupported", "pi")
    legacy = unsupported.registration.create_adapter(unsupported.grant)
    unsupported.registration = replace(unsupported.registration, create_adapter=lambda _: legacy)
    assert unsupported.adapter() is legacy


def test_cursor_captures_only_native_metadata_sidecars_without_inspecting_their_body(tmp_path):
    fixture = Fixture(tmp_path, "cursor")
    fixture.append("Native transcript")
    metadata = fixture.path.with_suffix(".meta.json")
    metadata.write_text('{"nativeMetadata": true}')
    (fixture.root / "config.meta.json").write_text("must-not-copy")
    (fixture.root / "credentials.json").write_text("must-not-copy")
    evidence(asyncio.run(scan(fixture.adapter())))
    assert {entry.relative_path for entry in fixture.manifest().files} == {
        fixture.path.relative_to(fixture.root).as_posix(),
        metadata.relative_to(fixture.root).as_posix(),
    }


@pytest.mark.parametrize("source", ["workbuddy", "claude-code", "codex", "cursor"])
def test_live_history_and_sync_share_persisted_cursors_without_replay(tmp_path, source):
    fixture = Fixture(tmp_path, source)
    fixture.append("Previously imported live")
    runner = ImportRunner(evidence_store=fixture.evidence, job_store=fixture.jobs)
    first = asyncio.run(
        runner.run(
            adapter=fixture.registration.create_adapter(fixture.grant),
            job_id=fixture.job.job_id,
        )
    )
    assert first.stored == 1
    fixture.append("Snapshot addition")
    fixture.job = fixture.jobs.create(user_id="local", source_id=source)
    history = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert (history.stored, history.merged, history.emitted) == (1, 0, 1)
    copied = fixture.manifest()
    fixture.append("Live sync addition")
    fixture.job = fixture.jobs.create(
        user_id="local",
        source_id=source,
        operation="sync",
    )
    synced = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert (synced.stored, synced.merged, synced.emitted) == (1, 0, 1)
    assert fixture.evidence.count() == 3
    assert (
        SnapshotManifest.model_validate_json(
            (fixture.directory / history.job_id / "manifest.json").read_bytes()
        )
        == copied
    )


def test_cursor_wal_capture_uses_copy_size_for_incoming_and_original_size_for_outgoing(tmp_path):
    from tests.test_import_snapshots import host_sqlite_writer

    fixture = Fixture(tmp_path, "cursor")
    database = fixture.root / "chats/acme/native/store.db"
    database.parent.mkdir(parents=True)
    with host_sqlite_writer(database) as execute:
        execute("PRAGMA journal_mode=WAL")
        execute("PRAGMA wal_autocheckpoint=0")
        execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        execute("PRAGMA wal_checkpoint(TRUNCATE)")
        execute("INSERT INTO blobs VALUES ('opaque-non-message', zeroblob(32768))")
        for index in (1, 2):
            payload = json.dumps({"role": "user", "content": f"WAL text {index}"})
            execute(f"INSERT INTO blobs VALUES ('message-{index}', '{payload}')")
        source_bytes = database.stat().st_size
        original_main = database.read_bytes()
        original_wal = database.with_name("store.db-wal").read_bytes()
        original_shm = database.with_name("store.db-shm").read_bytes()
        first = evidence(asyncio.run(scan(fixture.adapter(), ScanOptions(max_messages=1))))[0]
        entry = fixture.manifest().files[0]
        assert entry.captured_size > entry.source_size == source_bytes
        assert first.cursor.observed_size == source_bytes
        assert database.read_bytes() == original_main
        assert database.with_name("store.db-wal").read_bytes() == original_wal
        assert database.with_name("store.db-shm").read_bytes() == original_shm
        payload = json.dumps({"role": "user", "content": "Committed too late"})
        execute(f"INSERT INTO blobs VALUES ('message-3', '{payload}')")
        remaining = evidence(
            asyncio.run(
                scan(fixture.adapter(), ScanOptions(cursors={first.cursor.file_key: first.cursor}))
            )
        )
        assert [item.evidence.verbatim for item in remaining] == ["WAL text 2"]
        assert remaining[0].cursor.observed_size == source_bytes


@pytest.mark.parametrize("changed", ["file_identity", "size", "anchor"])
def test_mapping_does_not_make_invalid_original_checkpoints_valid(tmp_path, changed):
    fixture = Fixture(tmp_path, "codex")
    fixture.append("First")
    fixture.append("Second")
    first = evidence(asyncio.run(scan(fixture.adapter(), ScanOptions(max_messages=1))))[0].cursor
    update = {
        "file_identity": {"file_identity": "a-different-original-file"},
        "size": {"observed_size": first.observed_size + 1},
        "anchor": {"checkpoint_anchor": "0" * 64},
    }[changed]
    invalid = first.model_copy(update=update)
    rows = evidence(
        asyncio.run(scan(fixture.adapter(), ScanOptions(cursors={invalid.file_key: invalid})))
    )
    assert [item.evidence.verbatim for item in rows] == ["First", "Second"]


def test_published_snapshot_reopens_after_adapter_failure_without_recapture(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    fixture.append("Committed snapshot")
    original_capture = SourceSnapshotStore.capture

    def crash_after_publish(store, **kwargs):
        original_capture(store, **kwargs)
        raise OSError("Simulated failure after atomic publication")

    monkeypatch.setattr(SourceSnapshotStore, "capture", crash_after_publish)
    with pytest.raises(SnapshotError) as failed:
        asyncio.run(scan(fixture.adapter()))
    assert failed.value.code == SnapshotErrorCode.IO_ERROR
    selection_id = fixture.binding()["selection_id"]
    fixture.append("Outside committed snapshot")

    def never_capture(*args, **kwargs):
        pytest.fail("A pre-existing binding is never fresh confirmation")

    monkeypatch.setattr(SourceSnapshotStore, "capture", never_capture)
    rows = evidence(asyncio.run(scan(fixture.adapter())))
    assert [item.evidence.verbatim for item in rows] == ["Committed snapshot"]
    assert fixture.binding()["selection_id"] == selection_id


def test_original_root_replacement_fails_after_capture_before_parser(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    fixture.append("Old authorized root")
    original_capture = SourceSnapshotStore.capture

    def replace_root(store, **kwargs):
        snapshot = original_capture(store, **kwargs)
        fixture.root.rename(fixture.root.with_name("previous-root"))
        fixture.root.mkdir()
        fixture.append("New unauthorized root")
        return snapshot

    monkeypatch.setattr(SourceSnapshotStore, "capture", replace_root)
    runner = ImportRunner(evidence_store=fixture.evidence, job_store=fixture.jobs)
    with pytest.raises(SourceAccessError) as failed:
        asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert failed.value.code == SourceAccessErrorCode.SOURCE_IDENTITY_CHANGED
    assert fixture.jobs.require(fixture.job.job_id).status == ImportStatus.FAILED
    assert fixture.evidence.count() == 0


def test_selection_identity_conflict_cannot_fall_back_to_live_reader(tmp_path):
    fixture = Fixture(tmp_path, "codex")
    fixture.append("Original selection")
    asyncio.run(scan(fixture.adapter()))
    with fixture.jobs._connect(writing=True) as connection:
        connection.execute(
            "UPDATE import_job_snapshots SET selection_id=? WHERE job_id=?",
            ("codex:other-files:v2", fixture.job.job_id),
        )
    with pytest.raises(SnapshotError) as failed:
        asyncio.run(scan(fixture.adapter()))
    assert failed.value.code == SnapshotErrorCode.CONFLICT


def test_constructor_never_captures_or_builds_a_history_reader(tmp_path):
    fixture = Fixture(tmp_path)

    def not_yet(_):
        pytest.fail("History reader must not be created until scan()")

    fixture.registration = replace(fixture.registration, create_adapter=not_yet)
    assert fixture.adapter().descriptor == fixture.registration.descriptor
    assert not list(fixture.directory.iterdir())
    with fixture.jobs._connect() as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='import_job_snapshots'"
            ).fetchone()
            is None
        )


@pytest.mark.parametrize(
    "content",
    [b"\0" * 13_738, b'{"type":"user","message":', b'{"type":"user","message":"\xff"}'],
    ids=["f06-nul-only", "partial-json", "invalid-utf8"],
)
def test_frozen_nonempty_invalid_eof_becomes_persisted_import_issue(tmp_path, content):
    fixture = Fixture(tmp_path)
    fixture.path.parent.mkdir(parents=True)
    fixture.path.write_bytes(content)
    original = fixture.grant.authorize_file(fixture.path)
    runner = ImportRunner(evidence_store=fixture.evidence, job_store=fixture.jobs)

    completed = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))

    # Existing runner semantics permit completed-with-errors, never clean success.
    assert completed.status is ImportStatus.COMPLETED
    assert completed.errors == 1
    assert completed.stored == completed.skipped == fixture.evidence.count() == 0
    issues = fixture.jobs.list_issues(fixture.job.job_id)
    assert len(issues) == 1
    assert issues[0].reason == "invalid_json"
    cursors = fixture.jobs.get_source_cursors(user_id="local", source_id="claude-code")
    assert set(cursors) == {original.safe_id}
    cursor = cursors[original.safe_id]
    assert cursor.file_identity == original.file_identity
    assert cursor.observed_size == len(content)
    assert cursor.checkpoint == f"byte:{len(content)}"
    assert fixture.path.read_bytes() == content
    assert (
        fixture.directory / fixture.job.job_id / "files" / original.relative_path
    ).read_bytes() == content
    assert len(fixture.manifest().files) == 1


@pytest.mark.parametrize("source", ["claude-code", "codex", "cursor", "workbuddy"])
def test_frozen_valid_eof_is_stored_once_across_restart_history_and_live_sync(tmp_path, source):
    fixture = Fixture(tmp_path, source)
    fixture.append("First complete line")
    fixture.append("Complete at frozen EOF", role="assistant")
    content = fixture.path.read_bytes().removesuffix(b"\n")
    fixture.path.write_bytes(content)
    first = evidence(asyncio.run(scan(fixture.adapter(), ScanOptions(max_messages=1))))[0]
    fixture.jobs = ImportJobStore(fixture.jobs.database_path)
    remaining = evidence(
        asyncio.run(
            scan(fixture.adapter(), ScanOptions(cursors={first.cursor.file_key: first.cursor}))
        )
    )
    assert [event.evidence.verbatim for event in remaining] == ["Complete at frozen EOF"]
    last = remaining[0].cursor
    assert last.checkpoint == f"byte:{len(content)}"
    assert (
        evidence(asyncio.run(scan(fixture.adapter(), ScanOptions(cursors={last.file_key: last}))))
        == []
    )

    runner = ImportRunner(evidence_store=fixture.evidence, job_store=fixture.jobs)
    imported = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert (imported.stored, imported.emitted, imported.merged, imported.errors) == (2, 2, 0, 0)
    fixture.job = fixture.jobs.create(user_id="local", source_id=source)
    repeated = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert (repeated.stored, repeated.emitted, repeated.merged, repeated.errors) == (0, 0, 0, 0)
    assert fixture.path.read_bytes() == content

    with fixture.path.open("ab") as stream:
        stream.write(b"\n")
    fixture.append("New live line")
    fixture.job = fixture.jobs.create(
        user_id="local",
        source_id=source,
        operation="sync",
    )
    synced = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert (synced.stored, synced.emitted, synced.merged, synced.errors) == (1, 1, 0, 0)
    assert fixture.evidence.count() == 3


@pytest.mark.parametrize("source", ["claude-code", "codex", "cursor", "workbuddy"])
def test_sync_still_defers_valid_and_partial_live_eof(tmp_path, source):
    fixture = Fixture(tmp_path, source, operation="sync")
    fixture.append("Unterminated live message")
    content = fixture.path.read_bytes().removesuffix(b"\n")
    fixture.path.write_bytes(content)
    runner = ImportRunner(evidence_store=fixture.evidence, job_store=fixture.jobs)
    deferred = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert (deferred.stored, deferred.emitted, deferred.errors) == (0, 0, 0)
    assert [
        cursor.checkpoint
        for cursor in fixture.jobs.get_source_cursors(user_id="local", source_id=source).values()
    ] == ["byte:0"]
    assert not list(fixture.directory.iterdir())
    fixture.path.write_bytes(content + b'\n{"partial":')
    fixture.job = fixture.jobs.create(
        user_id="local",
        source_id=source,
        operation="sync",
    )
    synced = asyncio.run(runner.run(adapter=fixture.adapter(), job_id=fixture.job.job_id))
    assert (synced.stored, synced.emitted, synced.errors) == (1, 1, 0)
    cursor = next(iter(fixture.jobs.get_source_cursors(user_id="local", source_id=source).values()))
    assert cursor.checkpoint == f"byte:{len(content) + 1}"


def test_capture_during_partial_append_reports_only_frozen_bytes(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    fixture.path.parent.mkdir(parents=True)
    partial = b'{"type":"user","message":{"content":"part'
    fixture.path.write_bytes(partial)
    real_capture = SourceSnapshotStore.capture

    def complete_after_capture(store, **kwargs):
        snapshot = real_capture(store, **kwargs)
        with fixture.path.open("ab") as stream:
            stream.write(b'ial message"}}\n')
        return snapshot

    monkeypatch.setattr(SourceSnapshotStore, "capture", complete_after_capture)
    events = asyncio.run(scan(fixture.adapter()))
    assert not evidence(events)
    failures = [event for event in events if isinstance(event, ScanFailure)]
    assert len(failures) == 1
    assert failures[0].reason_code is ScanIssueCode.INVALID_JSON
    assert failures[0].cursor.checkpoint == f"byte:{len(partial)}"
    cursor = failures[0].cursor
    # A later explicitly authorized live reader can reread the now-complete
    # original; the frozen error must not make its completed message disappear.
    live = evidence(
        asyncio.run(
            scan(
                fixture.registration.create_adapter(fixture.grant),
                ScanOptions(cursors={cursor.file_key: cursor}),
            )
        )
    )
    assert [event.evidence.verbatim for event in live] == ["partial message"]


def test_frozen_eof_header_uses_the_same_immutable_reader_mode(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.path.parent.mkdir(parents=True)
    fixture.path.write_bytes(b'{"header":true,"cwd":"fixture"}')
    seen_headers = []

    def parse(record, context):
        seen_headers.append(context.header)
        return ParsedSkip(ScanIssueCode.UNKNOWN_RECORD)

    fixture.registration = replace(
        fixture.registration,
        create_adapter=lambda grant: JsonlSourceAdapter(
            descriptor=fixture.registration.descriptor,
            grant=grant,
            parser=parse,
            header_selector=lambda record: record.get("header") is True,
        ),
    )
    events = asyncio.run(scan(fixture.adapter()))
    assert seen_headers == [{"header": True, "cwd": "fixture"}]
    assert len([event for event in events if isinstance(event, ScanSkip)]) == 1


def test_snapshot_reader_does_not_mutate_the_callers_live_options(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.append("Complete frozen EOF")
    fixture.path.write_bytes(fixture.path.read_bytes().removesuffix(b"\n"))
    options = ScanOptions()
    assert len(evidence(asyncio.run(scan(fixture.adapter(), options)))) == 1
    assert options.immutable is False
    assert (
        evidence(asyncio.run(scan(fixture.registration.create_adapter(fixture.grant), options)))
        == []
    )
