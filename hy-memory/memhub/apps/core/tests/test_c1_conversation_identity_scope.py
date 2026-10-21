"""Same-named source sessions must stay separate through the read path.

Cursor's on-disk session identity is project + session name. Two projects can
both contain ``same.jsonl``; discovery keeps both, but reads, seed selection
and dispatch hydration must not merge them back into one conversation. The
workspace column is already part of the imported row, so this is an owned
query-level identity guard rather than a schema change.
"""

from datetime import UTC, datetime

from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore


def _cursor_record(
    *,
    conversation_id: str,
    workspace: str,
    ordinal: str,
    verbatim: str,
    message_id: str | None = None,
    role: str = "user",
    written_by: WrittenBy = WrittenBy.PERSON,
    created_at: datetime | None = None,
) -> EvidenceInput:
    return EvidenceInput(
        source_id="cursor",
        workspace=workspace,
        project=workspace.rsplit(":", 1)[-1],
        conversation_id=conversation_id,
        message_id=message_id,
        source_ordinal=ordinal,
        role=role,
        written_by=written_by,
        created_at=created_at,
        verbatim=verbatim,
        origin_meta={EvidenceOrigin.FILE: OriginMetadata(raw_meta={})},
    )


def test_same_message_id_in_two_workspaces_produces_two_evidence_rows(tmp_path):
    store = EvidenceStore(tmp_path / "core.sqlite3")
    first_input = _cursor_record(
        conversation_id="same-conversation",
        workspace="workspace:v1:project-a",
        ordinal="a:byte:1",
        message_id="same-message",
        verbatim="project A",
    )
    second_input = _cursor_record(
        conversation_id="same-conversation",
        workspace="workspace:v1:project-b",
        ordinal="b:byte:1",
        message_id="same-message",
        verbatim="project B",
    )

    first = store.put(first_input).record
    second = store.put(second_input).record

    assert first_input.idempotency_key != second_input.idempotency_key
    assert first.evidence_id != second.evidence_id
    assert store.count() == 2
    assert {
        (record.workspace, record.verbatim) for record in store.list_conversation(first.evidence_id)
    } == {("workspace:v1:project-a", "project A")}
    assert {
        (record.workspace, record.verbatim)
        for record in store.list_conversation(second.evidence_id)
    } == {("workspace:v1:project-b", "project B")}


def test_same_message_id_in_one_workspace_replays_idempotently(tmp_path):
    store = EvidenceStore(tmp_path / "core.sqlite3")
    original = _cursor_record(
        conversation_id="same-conversation",
        workspace="workspace:v1:project-a",
        ordinal="a:byte:1",
        message_id="same-message",
        verbatim="project A",
    )

    first = store.put(original).record
    replay = store.put(original)

    assert replay.was_created is False
    assert replay.was_revised is False
    assert replay.record.evidence_id == first.evidence_id
    assert replay.record.revision == 1
    assert store.count() == 1


def test_correlation_bridge_does_not_guess_between_two_workspaces(tmp_path):
    store = EvidenceStore(tmp_path / "core.sqlite3")
    for workspace, text in (
        ("workspace:v1:project-a", "project A"),
        ("workspace:v1:project-b", "project B"),
    ):
        store.put(
            _cursor_record(
                conversation_id="same-conversation",
                workspace=workspace,
                ordinal=f"{workspace}:byte:1",
                message_id="same-message",
                verbatim=text,
            ).model_copy(update={"correlation_id": "same-correlation"})
        )

    unscoped = _cursor_record(
        conversation_id="same-conversation",
        workspace="workspace:v1:project-c",
        ordinal="c:byte:1",
        message_id="same-message",
        verbatim="project C",
    ).model_copy(
        update={
            "workspace": None,
            "project": None,
            "message_id": None,
            "correlation_id": "same-correlation",
        }
    )
    result = store.put(unscoped)

    assert result.was_created is True
    assert store.count() == 3


def test_explicit_workspace_a_then_b_does_not_anchor_by_message_id(tmp_path):
    store = EvidenceStore(tmp_path / "core.sqlite3")
    first = store.put(
        _cursor_record(
            conversation_id="same-conversation",
            workspace="workspace:v1:A",
            ordinal="a:byte:1",
            message_id="same-message",
            verbatim="A",
        )
    ).record
    second = store.put(
        _cursor_record(
            conversation_id="same-conversation",
            workspace="workspace:v1:B",
            ordinal="b:byte:1",
            message_id="same-message",
            verbatim="B",
        )
    ).record

    assert first.evidence_id != second.evidence_id
    assert store.count() == 2


def test_explicit_workspace_a_then_b_does_not_anchor_by_correlation_id(tmp_path):
    store = EvidenceStore(tmp_path / "core.sqlite3")
    base = _cursor_record(
        conversation_id="same-conversation",
        workspace="workspace:v1:A",
        ordinal="a:byte:1",
        verbatim="A",
        message_id=None,
    ).model_copy(update={"correlation_id": "same-correlation"})
    first = store.put(base).record
    second = store.put(base.model_copy(update={"workspace": "workspace:v1:B"})).record

    assert first.evidence_id != second.evidence_id
    assert store.count() == 2


def test_explicit_workspace_a_then_b_does_not_anchor_hook_to_file(tmp_path):
    store = EvidenceStore(tmp_path / "core.sqlite3")
    hook = _cursor_record(
        conversation_id="same-conversation",
        workspace="workspace:v1:A",
        ordinal="a:byte:1",
        verbatim="same hook text",
        message_id=None,
    ).model_copy(
        update={
            "correlation_id": "same-correlation",
            "origin_meta": {EvidenceOrigin.HOOK: OriginMetadata()},
        }
    )
    first = store.put(hook).record
    file_row = _cursor_record(
        conversation_id="same-conversation",
        workspace="workspace:v1:B",
        ordinal="b:byte:1",
        verbatim="same hook text",
        message_id="same-message",
    )
    second = store.put(file_row).record

    assert first.evidence_id != second.evidence_id
    assert store.count() == 2


def test_explicit_workspace_a_then_b_does_not_anchor_legacy_v1(tmp_path):
    store = EvidenceStore(tmp_path / "core.sqlite3")
    first = store.put(
        _cursor_record(
            conversation_id="same-conversation",
            workspace="workspace:v1:A",
            ordinal="a:byte:1",
            message_id="same-message",
            verbatim="A",
        )
    ).record
    legacy = _cursor_record(
        conversation_id="same-conversation",
        workspace="workspace:v1:B",
        ordinal="b:byte:1",
        message_id="same-message",
        verbatim="B",
    )
    with store._connect(writing=True) as connection:
        connection.execute(
            "UPDATE evidence SET idempotency_key = ? WHERE evidence_id = ?",
            (legacy.legacy_message_idempotency_key, first.evidence_id),
        )
    second = store.put(legacy).record

    assert second.evidence_id != first.evidence_id
    assert store.count() == 2


def test_same_cursor_conversation_name_in_two_workspaces_stays_separate(tmp_path):
    store = EvidenceStore(tmp_path / "core.sqlite3")
    first = store.put(
        _cursor_record(
            conversation_id="same",
            workspace="workspace:v1:project-a",
            ordinal="a:byte:1",
            verbatim="project A question",
        )
    ).record
    second = store.put(
        _cursor_record(
            conversation_id="same",
            workspace="workspace:v1:project-b",
            ordinal="b:byte:1",
            verbatim="project B question",
        )
    ).record
    first_answer = store.put(
        _cursor_record(
            conversation_id="same",
            workspace="workspace:v1:project-a",
            ordinal="a:byte:2",
            verbatim="project A answer",
            role="assistant",
            written_by=WrittenBy.AGENT,
        )
    ).record

    # The old shape grouped by (user, source, conversation_id), so this
    # returned two seeds for one conversation and each read merged A and B.
    assert store.list_conversation_seed_ids() == [first.evidence_id, second.evidence_id]
    assert [record.evidence_id for record in store.list_conversation(first.evidence_id)] == [
        first.evidence_id,
        first_answer.evidence_id,
    ]
    assert [record.evidence_id for record in store.list_conversation(second.evidence_id)] == [
        second.evidence_id
    ]


def test_pending_dispatch_keeps_same_named_workspaces_separate(tmp_path):
    store = EvidenceStore(tmp_path / "core.sqlite3")
    a_old = store.put(
        _cursor_record(
            conversation_id="same",
            workspace="workspace:v1:project-a",
            ordinal="a:byte:1",
            verbatim="older A",
            created_at=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
        )
    ).record
    b_old = store.put(
        _cursor_record(
            conversation_id="same",
            workspace="workspace:v1:project-b",
            ordinal="b:byte:1",
            verbatim="older B",
            created_at=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
        )
    ).record
    a_latest = store.put(
        _cursor_record(
            conversation_id="same",
            workspace="workspace:v1:project-a",
            ordinal="a:byte:2",
            verbatim="latest A",
            created_at=datetime(2026, 9, 28, 11, 0, tzinfo=UTC),
        )
    ).record
    b_latest = store.put(
        _cursor_record(
            conversation_id="same",
            workspace="workspace:v1:project-b",
            ordinal="b:byte:2",
            verbatim="latest B",
            created_at=datetime(2026, 9, 28, 11, 0, tzinfo=UTC),
        )
    ).record
    with store._connect(writing=True) as connection:
        store.stage_memory_dispatch(a_old, file_key="a", connection=connection)
        store.stage_memory_dispatch(b_old, file_key="b", connection=connection)

    assert [
        record.evidence_id
        for record in store.take_stable_file_records(
            user_id="local", source_id="cursor", file_key="a"
        )
    ] == [a_latest.evidence_id]
    assert [
        record.evidence_id
        for record in store.take_stable_file_records(
            user_id="local", source_id="cursor", file_key="b"
        )
    ] == [b_latest.evidence_id]


def test_claude_code_same_session_id_in_two_projects_is_not_merged(tmp_path):
    """A reused Claude session id must follow the same workspace scope as Cursor."""
    import asyncio
    import json

    from one_memory.imports.grants import SourceGrantStore
    from one_memory.imports.jobs import ImportJobStore, ImportStatus
    from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
    from one_memory.imports.supervisor import ImportSupervisor

    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    catalog = build_source_catalog(home=home, environment={})
    root = catalog["claude-code"].candidate.path
    for project, text in (("project-a", "claude A"), ("project-b", "claude B")):
        path = root / project / "same.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "same",
                    "uuid": f"{project}-message",
                    "cwd": f"/private/{project}",
                    "message": {"content": text},
                }
            )
            + "\n",
            encoding="utf-8",
        )

    database = tmp_path / "core.sqlite3"
    jobs = ImportJobStore(database)
    store = EvidenceStore(database)
    grants = SourceGrantStore(database, home=home)
    grants.grant(
        user_id="local",
        source_id="claude-code",
        root=root,
        candidate_kind=RootCandidateKind.DEFAULT,
    )

    async def run():
        supervisor = ImportSupervisor(
            adapters={
                "claude-code": catalog["claude-code"].create_adapter(
                    grants.authorized_root(user_id="local", source_id="claude-code")
                )
            },
            evidence_store=store,
            job_store=jobs,
        )
        job = supervisor.create_job("claude-code")
        supervisor.enqueue(job.job_id)
        return await supervisor.wait(job.job_id)

    assert asyncio.run(run()).status is ImportStatus.COMPLETED
    seeds = store.list_conversation_seed_ids()
    assert len(seeds) == 2, "two projects sharing a Claude session id are two conversations"
    assert {
        tuple(record.verbatim for record in store.list_conversation(seed)) for seed in seeds
    } == {("claude A",), ("claude B",)}
