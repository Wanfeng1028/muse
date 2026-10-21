from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from one_memory.imports.access import AuthorizedSourceFile, AuthorizedSourceRoot
from one_memory.imports.adapters import (
    ScannedEvidence,
    ScanOptions,
    ScanPhase,
    ScanProgressEvent,
    SourceCapabilities,
    SourceCursor,
    SourceDescriptor,
    StorageKind,
)
from one_memory.imports.discovery import discover_source_files
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.live_sync import PollingLiveSyncSupervisor
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.sources import openclaw as openclaw_module
from one_memory.imports.sources.openclaw import (
    OPENCLAW_DESCRIPTOR,
    OpenClawSourceAdapter,
)
from one_memory.imports.sources.workbuddy import create_workbuddy_adapter
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor

_DESCRIPTOR = SourceDescriptor(
    source_id="fixture",
    display_name="Fixture",
    storage_kinds=frozenset({StorageKind.JSONL}),
    capabilities=SourceCapabilities(
        can_append=True,
        can_observe_edits=False,
        can_observe_deletes=False,
        can_reconcile_complete_set=False,
    ),
)


class MetadataProbedAdapter:
    descriptor = _DESCRIPTOR

    def __init__(self, *, changed: bool) -> None:
        self.changed = changed
        self.probes = 0
        self.scans = 0

    async def detect(self) -> bool:
        return True

    async def has_changes(self, options: ScanOptions) -> bool:
        self.probes += 1
        return self.changed

    async def scan(self, options: ScanOptions):
        self.scans += 1
        yield ScannedEvidence(
            evidence=EvidenceInput(
                source_id="fixture",
                conversation_id="conversation",
                message_id="message",
                role="user",
                written_by=WrittenBy.PERSON,
                verbatim="one new turn",
                origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
            ),
            cursor=SourceCursor(
                file_key="a" * 64,
                file_identity="fixture.jsonl",
                checkpoint="byte:12",
                checkpoint_anchor="b" * 64,
                observed_size=12,
                observed_modified_ns=1,
                read_to_end=True,
            ),
        )
        yield ScanProgressEvent(phase=ScanPhase.DONE)


def _build(
    tmp_path: Path, adapter
) -> tuple[ImportJobStore, ImportSupervisor, PollingLiveSyncSupervisor]:
    database = tmp_path / "one-memory.sqlite3"
    jobs = ImportJobStore(database)
    imports = ImportSupervisor(
        adapters={adapter.descriptor.source_id: adapter},
        evidence_store=EvidenceStore(database),
        job_store=jobs,
    )
    live = PollingLiveSyncSupervisor(
        source_ids=(adapter.descriptor.source_id,),
        import_supervisor=imports,
        job_store=jobs,
    )
    return jobs, imports, live


def test_unchanged_file_metadata_avoids_a_job_and_content_read(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = MetadataProbedAdapter(changed=False)
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            assert await live.trigger("fixture") is None
        finally:
            await imports.shutdown()

        assert adapter.probes == 1
        assert adapter.scans == 0
        assert jobs.list_jobs() == []

    asyncio.run(scenario())


def test_changed_file_content_is_read_once_by_the_import_job(tmp_path: Path) -> None:
    async def scenario() -> None:
        adapter = MetadataProbedAdapter(changed=True)
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            completed = await live.trigger("fixture")
        finally:
            await imports.shutdown()

        assert completed is not None and completed.status is ImportStatus.COMPLETED
        assert adapter.probes == 1
        assert adapter.scans == 1
        assert len(jobs.list_jobs()) == 1

    asyncio.run(scenario())


def test_workbuddy_first_live_poll_baselines_history_then_imports_only_append(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        root = tmp_path / ".codebuddy" / "projects" / "qa"
        root.mkdir(parents=True)
        transcript = root / "session.jsonl"
        historical = [
            f'{{"type":"user","sessionId":"history","id":"h-{index}",'
            f'"content":"historical {index}"}}\n'
            for index in range(100_000)
        ]
        transcript.write_text("".join(historical))
        grant = AuthorizedSourceRoot.grant(
            source_id="workbuddy",
            root=tmp_path / ".codebuddy",
            user_confirmed=True,
            home=tmp_path,
        )
        adapter = create_workbuddy_adapter(grant)
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            history_job = jobs.create(user_id="local", source_id="workbuddy")
            baseline = next(iter((await adapter.live_baseline()).values()))
            with sqlite3.connect(jobs.database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO source_cursors (
                        user_id,source_id,file_key,file_identity,checkpoint,
                        checkpoint_anchor,observed_size,observed_modified_ns,updated_at,read_to_end
                    ) VALUES (?,?,?,?,?,?,?,?,?,0)
                    """,
                    (
                        "local",
                        "workbuddy",
                        baseline.file_key,
                        baseline.file_identity,
                        "byte:1",
                        None,
                        baseline.observed_size,
                        baseline.observed_modified_ns,
                        "2026-10-04T00:00:00+00:00",
                    ),
                )
            await live.initialize_source("workbuddy")
            baseline_sync = await live.trigger("workbuddy")
            assert baseline_sync is None or baseline_sync.stored == 0
            assert EvidenceStore(jobs.database_path).count() == 0
            with transcript.open("a") as stream:
                stream.write(
                    '{"type":"user","sessionId":"live","id":"live-1",'
                    '"content":"QA realtime append"}\n'
                )
            completed = await asyncio.wait_for(live.trigger("workbuddy"), timeout=10)
            assert completed is not None and completed.status is ImportStatus.COMPLETED
            assert completed.stored == 1
            assert EvidenceStore(jobs.database_path).count() == 1
            history = jobs.get_source_cursors(
                user_id="local", source_id="workbuddy", operation="history"
            )
            assert next(iter(history.values())).checkpoint == "byte:1"
            assert jobs.require(history_job.job_id).status is ImportStatus.PENDING
        finally:
            await imports.shutdown()

    asyncio.run(scenario())


def test_cursor_rewind_emits_diagnostic(tmp_path: Path, monkeypatch) -> None:
    """A rewound live cursor must leave a trace naming which branch moved it."""
    from one_memory.imports.sources.common import (
        SourceCursor,
        _emit_cursor_rewound,
    )

    projects = tmp_path / ".codebuddy" / "projects" / "qa"
    projects.mkdir(parents=True)
    transcript = projects / "session.jsonl"
    transcript.write_text('{"type":"user","sessionId":"s","content":"x"}\n')
    grant = AuthorizedSourceRoot.grant(
        source_id="workbuddy",
        root=tmp_path / ".codebuddy",
        user_confirmed=True,
        home=tmp_path,
    )
    source_file = next(
        item
        for item in discover_source_files(grant, suffixes=frozenset({".jsonl"}), max_targets=10)
        if isinstance(item, AuthorizedSourceFile)
    )
    previous = SourceCursor(
        file_key=source_file.safe_id,
        file_identity=source_file.file_identity,
        checkpoint=f"byte:{source_file.size}",
        checkpoint_anchor=None,
        observed_size=source_file.size,
        observed_modified_ns=source_file.modified_ns,
        read_to_end=True,
    )
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "one_memory.imports.sources.common.diagnostic_event",
        lambda **fields: events.append(fields),
    )

    _emit_cursor_rewound(
        source_file,
        previous=previous,
        new_checkpoint="byte:0",
        branch="touched_cursor_no_records",
        previous_checkpoint=previous.checkpoint,
        read_to_end=previous.read_to_end,
    )

    assert len(events) == 1
    event = events[0]
    assert event["event"] == "live_sync.cursor_rewound"
    details = event["details"]
    assert details["cursor_rewind_branch"] == "touched_cursor_no_records"
    assert details["cursor_old"] == source_file.size
    assert details["cursor_new"] == 0
    assert details["cursor_read_to_end"] is True
    assert details["file_size"] == source_file.size
    # No file content: the path hash itself is all the identity the log carries.
    assert len(str(details.get("reason", ""))) <= 16


def test_appended_file_with_stable_identity_does_not_report_a_rewind(
    tmp_path: Path, monkeypatch
) -> None:
    """Keep wins: an append-only file never reports a cursor rewind.

    WorkBuddy only appends (Kristin 10/06). A batch whose records were all
    skipped still ends with `last is None`; the old cursor must be kept
    (`keep` branch), so no `live_sync.cursor_rewound` event may fire.
    """

    async def scenario() -> None:
        root = tmp_path / ".codebuddy" / "projects" / "qa"
        root.mkdir(parents=True)
        transcript = root / "session.jsonl"
        transcript.write_text(
            '{"type":"user","sessionId":"history","id":"h-0","content":"one"}\n'
            '{"type":"user","sessionId":"history","id":"h-1","content":"two"}\n'
        )
        grant = AuthorizedSourceRoot.grant(
            source_id="workbuddy",
            root=tmp_path / ".codebuddy",
            user_confirmed=True,
            home=tmp_path,
        )
        adapter = create_workbuddy_adapter(grant)
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            await live.initialize_source("workbuddy")
            first = await live.trigger("workbuddy")
            assert first is None or first.status is ImportStatus.COMPLETED
            with transcript.open("a") as stream:
                stream.write(
                    '{"type":"system","sessionId":"history","id":"tool-1",'
                    '"content":"excluded tool record"}\n'
                )
            events: list[dict[str, object]] = []
            monkeypatch.setattr(
                "one_memory.imports.runner.diagnostic_event",
                lambda **fields: events.append(fields),
            )
            completed = await live.trigger("workbuddy")
            assert completed is None or completed.status is ImportStatus.COMPLETED
            rewound = [
                event for event in events if event.get("event") == "live_sync.cursor_rewound"
            ]
            assert rewound == [], "a kept cursor is not a rewind"
            cursor = next(
                iter(
                    jobs.get_source_cursors(
                        user_id="local", source_id="workbuddy", operation="sync"
                    ).values()
                )
            )
            assert cursor.read_to_end is True
        finally:
            await imports.shutdown()

    asyncio.run(scenario())


def test_openclaw_unsupported_state_db_is_a_persistent_aggregated_skip(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "openclaw"
    root.mkdir()
    for name in ("state.db", "cache.db"):
        connection = sqlite3.connect(root / name)
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
        connection.close()

    grant = AuthorizedSourceRoot.grant(
        source_id="openclaw",
        root=root,
        user_confirmed=True,
        home=tmp_path,
    )
    # This test covers the retained reader's skip behavior. The product factory
    # is intentionally paused and is covered by test_c1_openclaw_paused.py.
    adapter = OpenClawSourceAdapter(OPENCLAW_DESCRIPTOR, grant)
    opened = 0
    original_open = openclaw_module.open_sqlite_readonly

    def counted_open(*args, **kwargs):
        nonlocal opened
        opened += 1
        return original_open(*args, **kwargs)

    summaries: list[dict[str, object]] = []

    def capture_summary(**fields) -> None:
        if fields.get("event") == "import.parse.issue_summary":
            summaries.append(fields)

    monkeypatch.setattr(openclaw_module, "open_sqlite_readonly", counted_open)
    monkeypatch.setattr("one_memory.imports.runner.diagnostics_enabled", lambda: True)
    monkeypatch.setattr("one_memory.imports.runner.diagnostic_event", capture_summary)

    async def scenario() -> None:
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            first = await live.trigger("openclaw")
            assert first is not None and first.status is ImportStatus.COMPLETED
            assert jobs.skip_reason_counts(first.job_id) == {"unsupported_schema": 2}

            restarted = PollingLiveSyncSupervisor(
                source_ids=("openclaw",),
                import_supervisor=imports,
                job_store=jobs,
            )
            assert await restarted.trigger("openclaw") is None
            assert [job.job_id for job in jobs.list_jobs()] == [first.job_id]

            replacement = root / "replacement.tmp"
            connection = sqlite3.connect(replacement)
            connection.executescript(
                """
                CREATE TABLE conversations (
                    id TEXT PRIMARY KEY, workspace_path TEXT, git_root TEXT
                );
                CREATE TABLE messages (
                    id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT,
                    content TEXT, created_at TEXT
                );
                INSERT INTO conversations VALUES ('conversation', NULL, NULL);
                INSERT INTO messages VALUES (
                    'message', 'conversation', 'assistant', 'new schema', '2026-09-25'
                );
                """
            )
            connection.close()
            replacement.replace(root / "state.db")

            changed_identity = await restarted.trigger("openclaw")
            assert changed_identity is not None
            assert changed_identity.status is ImportStatus.COMPLETED
            assert changed_identity.stored == 1
            assert len(jobs.list_jobs()) == 2
        finally:
            await imports.shutdown()

    asyncio.run(scenario())

    assert opened == 3, "unchanged skipped databases must not be reopened"
    assert len(summaries) == 1
    assert summaries[0]["error_code"] == "unsupported_schema"
    assert summaries[0]["details"] == {
        "source_id": "openclaw",
        "reason": "unsupported_schema",
        "count": 2,
    }
