"""Isolated metadata receipts; never use a user database or start recording."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

import one_memory.call_event_store as module
from one_memory.call_event_store import (
    CallEvent,
    CallEventConflict,
    CallEventReference,
    CallEventStore,
    CallEventStoreUnavailable,
    CallReference,
)
from one_memory.context_feedback import FeedbackReference, make_offline_feedback
from one_memory.database import enable_write_ahead_log
from one_memory.database_access import close_main_databases

NOW = datetime(2026, 9, 20, 12, tzinfo=UTC)


def event(**changes):
    values = dict(
        event_id=uuid4(),
        occurred_at=NOW,
        host_id="codex",
        installation_id=uuid4(),
        tool="om_recall",
        state="grounded",
        stage="core_result",
        delivery="unknown",
        adoption="unknown",
        host_session_id=None,
        injection_elapsed_ms=None,
        elapsed_ms=1.5,
        raw_count=1,
        memory_count=1,
        references=(
            CallEventReference(kind="raw", id="evidence-1", revision=1, source_id="codex"),
            CallEventReference(kind="memory", id="memory-1", revision=2, source_id=None),
        ),
    )
    values.update(changes)
    return CallEvent(**values)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "one-memory.sqlite3"
    with closing(sqlite3.connect(path)) as db, db:
        enable_write_ahead_log(db)
        db.execute("CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY, verbatim TEXT NOT NULL)")
        db.execute("INSERT INTO evidence VALUES ('sentinel', 'preserve this Evidence')")
    return path


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(module, "_now", lambda: NOW)


@pytest.fixture
def store(database):
    result = CallEventStore(database, retention_days=30, max_events=10000)
    result.initialize()
    return result


@pytest.mark.parametrize(
    "field,value",
    [
        ("query", "private text"),
        ("content", "private text"),
        ("content_hash", "not permitted"),
        ("path", "/private/example"),
        ("endpoint", "https://example.invalid"),
        ("api_key", "synthetic-secret"),
        ("user_id", "other-owner"),
        ("event_id", "not-a-uuid"),
        ("installation_id", "not-a-uuid"),
        ("host_id", "unknown"),
        ("host_id", "arbitrary-host"),
        ("tool", "arbitrary-tool"),
        ("state", "adopted"),
        ("stage", "host_adoption"),
        ("delivery", "adopted"),
        ("adoption", "adopted"),
        ("host_session_id", "x\nprivate"),
        ("host_session_id", "/Users/private/session.jsonl"),
        ("host_session_id", "x" * 129),
        ("injection_elapsed_ms", -1),
        ("injection_elapsed_ms", "1.5"),
        ("occurred_at", datetime(2026, 9, 20)),
        ("occurred_at", 1789905600),
        ("elapsed_ms", float("nan")),
        ("elapsed_ms", float("inf")),
        ("elapsed_ms", float("-inf")),
        ("elapsed_ms", -1.0),
        ("elapsed_ms", "1.5"),
        ("elapsed_ms", True),
        ("raw_count", -1),
        ("raw_count", 21),
        ("memory_count", 21),
        ("memory_count", -1),
        ("raw_count", True),
        ("memory_count", "1"),
        ("memory_count", 1.0),
    ],
)
def test_event_is_strict_metadata_only(field, value):
    with pytest.raises(ValidationError):
        event(**{field: value})


def feedback(source, **changes):
    values = {
        "search_event_id": str(source.event_id),
        "feedback_kind": "relevant",
        "selected_refs": (FeedbackReference(kind="raw", reference_id="evidence-1", revision=1),),
        "actor": "user",
        "signal": "explicit_feedback",
        "consent_version": 1,
        "retention_until": NOW + timedelta(days=30),
        "now": NOW,
    }
    return make_offline_feedback(**(values | changes))


def test_explicit_feedback_is_a_versioned_local_label_not_a_memory(store):
    source = event()
    assert store.record(source)

    assert store.record_feedback(source.event_id, feedback(source)) is True
    assert store.record_feedback(source.event_id, feedback(source)) is False

    labels = store.list()
    assert labels.total == 2
    label = next(item for item in labels.items if item.stage == "feedback")
    assert label.stage == "feedback"
    assert label.adoption == "unknown"
    assert label.feedback is not None
    assert label.feedback.actor == "user_explicit"
    assert label.feedback.purpose == "offline_retrieval_evaluation"
    assert label.references == source.references[:1]
    encoded = labels.model_dump_json()
    assert "query" not in encoded and "preference" not in encoded


def test_feedback_requires_a_retained_search_and_returned_revision(store):
    source = event()
    assert store.record(source)
    missing = event()

    assert store.record_feedback(missing.event_id, feedback(missing)) is None
    not_returned = feedback(
        source,
        selected_refs=(FeedbackReference(kind="memory", reference_id="memory-1", revision=3),),
    )
    with pytest.raises(ValueError, match="call_event_feedback_reference_not_returned"):
        store.record_feedback(source.event_id, not_returned)
    assert store.list().total == 1


def test_feedback_cannot_target_another_feedback_event(store):
    source = event()
    assert store.record(source)
    label = feedback(source)
    assert store.record_feedback(source.event_id, label) is True
    feedback_event_id = next(
        item.event_id for item in store.list().items if item.stage == "feedback"
    )

    with pytest.raises(ValueError, match="call_event_feedback_source_must_be_search"):
        store.record_feedback(
            feedback_event_id,
            feedback(
                source,
                selected_refs=(
                    FeedbackReference(kind="raw", reference_id="evidence-1", revision=1),
                ),
            ),
        )


@pytest.mark.parametrize("timestamp", ["yesterday", "2026-09-20T12:00:00", 1789905600, None])
def test_json_timestamp_requires_explicit_timezone(timestamp):
    value = event().model_dump(mode="json")
    value["occurred_at"] = timestamp
    with pytest.raises(ValidationError):
        CallEvent.model_validate_json(json.dumps(value))


@pytest.mark.parametrize(
    "changes",
    [
        {"content": "private"},
        {"query": "private"},
        {"hash": "private"},
        {"path": "/private"},
        {"endpoint": "https://example.invalid"},
        {"token": "synthetic-secret"},
        {"kind": "other"},
        {"id": "x" * 513},
        {"id": 1},
        {"revision": 0},
        {"revision": True},
        {"revision": "1"},
        {"source_id": 1},
    ],
)
def test_references_reject_extra_content_and_invalid_metadata(changes):
    values = dict(kind="raw", id="evidence-1", revision=1, source_id=None)
    values.update(changes)
    with pytest.raises(ValidationError):
        CallEventReference(**values)


def test_reference_boundaries_and_deep_immutability():
    assert CallReference is CallEventReference
    reference = CallEventReference(kind="raw", id="x" * 512, revision=1, source_id=None)
    value = event(references=(reference,) * 128, raw_count=20, memory_count=0)
    assert CallEvent.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        event(references=(reference,) * 129)
    with pytest.raises(ValidationError):
        value.raw_count = 0
    with pytest.raises(ValidationError):
        value.references[0].id = "changed"
    with pytest.raises(TypeError):
        value.references[0] = reference


@pytest.mark.parametrize(
    "host",
    [
        "cursor",
        "codex",
        "claude-code",
        "workbuddy",
        "opencode",
        "qwen-code",
        "hermes",
        "pi",
        "deepseek-harness",
        None,
    ],
)
def test_allowlisted_hosts_and_unknown_null(host):
    assert event(host_id=host, installation_id=None).host_id == host


@pytest.mark.parametrize("tool", ["om_recall", "om_conversations", "om_ask", "om_matters"])
@pytest.mark.parametrize("state", ["grounded", "empty", "partial", "unavailable"])
def test_tool_and_result_enums(tool, state):
    assert event(tool=tool, state=state).state == state


@pytest.mark.parametrize(
    "days,maximum",
    [
        (0, 1),
        (366, 1),
        (True, 1),
        (1.0, 1),
        ("30", 1),
        (1, 0),
        (1, 100001),
        (1, False),
        (1, 1.0),
        (1, "10"),
    ],
)
def test_constructor_rejects_invalid_explicit_limits(database, days, maximum):
    with pytest.raises((ValueError, ValidationError)):
        CallEventStore(database, retention_days=days, max_events=maximum)


def test_config_has_no_defaults_and_requires_existing_database(database, tmp_path):
    with pytest.raises(TypeError):
        CallEventStore(database)
    with pytest.raises(TypeError):
        CallEventStore(database, retention_days=30)
    with pytest.raises(TypeError):
        CallEventStore(database, max_events=10000)
    for days, maximum in [(1, 1), (365, 100000)]:
        CallEventStore(database, retention_days=days, max_events=maximum)
    missing = tmp_path / "absent.sqlite3"
    with pytest.raises(CallEventStoreUnavailable):
        CallEventStore(missing, retention_days=1, max_events=1)
    assert not missing.exists()


def test_constructor_and_reads_do_not_initialize(database):
    value = CallEventStore(database, retention_days=1, max_events=1)
    for operation in (
        value.list,
        lambda: value.get(uuid4()),
        lambda: value.record(event()),
        lambda: value.clear(expected_event_ids=[]),
    ):
        with pytest.raises(CallEventStoreUnavailable):
            operation()
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ("evidence",)
        ]
    value.initialize()
    value.initialize()
    assert value.list().total == 0


def test_persistence_deduplication_and_payload_conflict(store, database):
    value = event()
    assert store.record(value) is True
    assert store.record(value) is False
    reopened = CallEventStore(database, retention_days=30, max_events=10000)
    assert reopened.get(value.event_id) == value
    assert reopened.list().items == (value,)
    with pytest.raises(CallEventConflict, match="call_event_conflict"):
        reopened.record(event(**{**value.model_dump(), "elapsed_ms": 2.5}))
    assert reopened.get(value.event_id) == value
    assert reopened.list().total == 1


def test_timezone_normalization_for_order_and_idempotency(store):
    value = event(occurred_at=NOW.astimezone(timezone(timedelta(hours=8))))
    assert value.occurred_at == NOW
    assert value.occurred_at.tzinfo == UTC
    assert store.record(value)
    same = event(**{**value.model_dump(), "occurred_at": NOW})
    assert store.record(same) is False


def test_invalid_model_copy_is_revalidated_before_record(store):
    invalid = event().model_copy(update={"raw_count": 100})
    with pytest.raises(ValidationError):
        store.record(invalid)
    invalid_reference = event().references[0].model_copy(update={"revision": 0})
    with pytest.raises(ValidationError):
        store.record(event().model_copy(update={"references": (invalid_reference,)}))
    assert store.list().total == 0


def test_age_boundary_excluded_on_read_without_pruning_until_write(store, database, monkeypatch):
    boundary = event(occurred_at=NOW - timedelta(days=30))
    recent = event(occurred_at=NOW - timedelta(days=1))
    store.record(boundary)
    store.record(recent)
    assert store.list().total == 2
    monkeypatch.setattr(module, "_now", lambda: NOW + timedelta(microseconds=1))
    assert store.get(boundary.event_id) is None
    assert store.list().items == (recent,)
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT count(*) FROM call_events").fetchone()[0] == 2
    assert store.record(recent) is False
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT count(*) FROM call_events").fetchone()[0] == 1


def test_write_prunes_expired_and_count_with_deterministic_ties(database):
    store = CallEventStore(database, retention_days=1, max_events=2)
    store.initialize()
    values = [event(event_id=UUID(int=i)) for i in (1, 2, 3)]
    for value in reversed(values):
        store.record(value)
    assert store.list().items == (values[2], values[1])
    old = event(occurred_at=NOW - timedelta(days=1, microseconds=1))
    store.record(old)
    assert store.get(old.event_id) is None
    assert store.list().items == (values[2], values[1])
    newer = event(occurred_at=NOW + timedelta(microseconds=1))
    store.record(newer)
    assert store.list().items == (newer, values[2])


def test_list_host_filter_paging_and_stable_sort(store):
    values = [
        event(event_id=UUID(int=i), host_id="cursor" if i % 2 else "codex") for i in range(1, 7)
    ]
    for value in reversed(values):
        store.record(value)
    page = store.list(limit=2, offset=1, host_id="cursor")
    assert page.total == 3
    assert page.items == (values[2], values[0])
    assert store.list(limit=100, offset=100000).items == ()
    assert store.get(uuid4()) is None


@pytest.mark.parametrize(
    "options",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": True},
        {"offset": -1},
        {"offset": 100001},
        {"offset": 1.0},
        {"host_id": "' OR 1=1 --"},
    ],
)
def test_list_rejects_unbounded_or_invalid_arguments(store, options):
    with pytest.raises((ValueError, ValidationError)):
        store.list(**options)


def test_count_and_items_share_snapshot_during_concurrent_insert(store, monkeypatch):
    first = event()
    later = event(occurred_at=NOW + timedelta(seconds=1))
    store.record(first)
    connect = module.sqlite3.connect
    inserted = False

    def observed_connect(*args, **kwargs):
        db = connect(*args, **kwargs)
        if "mode=ro" in str(args[0]):

            def trace(sql):
                nonlocal inserted
                if "ORDER BY occurred_at DESC" in sql and not inserted:
                    inserted = True
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        assert pool.submit(store.record, later).result(timeout=10)

            db.set_trace_callback(trace)
        return db

    close_main_databases()  # pooled connections would skip the patch

    monkeypatch.setattr(module.sqlite3, "connect", observed_connect)
    page = store.list()
    assert inserted
    assert page.total == 1
    assert page.items == (first,)
    assert store.list().total == 2


def test_concurrent_duplicate_writers_are_idempotent(store):
    value = event()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.record(value), range(8)))
    assert results.count(True) == 1
    assert results.count(False) == 7
    assert store.list().total == 1


def test_clear_exact_ids_preserves_new_events_and_evidence(store, database):
    first, second, later = event(), event(), event()
    store.record(first)
    store.record(second)
    expected = [item.event_id for item in store.list().items]
    store.record(later)
    assert store.clear(expected_event_ids=expected) == 2
    assert store.clear(expected_event_ids=expected) == 0
    assert store.clear(expected_event_ids=[]) == 0
    assert store.list().items == (later,)
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT * FROM evidence").fetchall() == [
            ("sentinel", "preserve this Evidence")
        ]


def test_clear_all_removes_only_call_events(store, database):
    first, second, later = event(), event(), event()
    store.record(first)
    store.record(second)
    store.record(later)
    assert store.clear_all() == 3
    assert store.list().total == 0
    assert store.clear_all() == 0
    store.record(later)
    assert store.get(later.event_id) == later
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT * FROM evidence").fetchall() == [
            ("sentinel", "preserve this Evidence")
        ]
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('evidence','governed_memories')"
        ).fetchall() == [("evidence",)]


def test_clear_validates_entire_bounded_id_list_before_deleting(store):
    value = event()
    store.record(value)
    for ids in (
        [uuid4()] * 101,
        [value.event_id, "'; DELETE FROM evidence; --"],
        [str(value.event_id)],
        (value.event_id,),
    ):
        with pytest.raises((ValueError, ValidationError)):
            store.clear(expected_event_ids=ids)
        assert store.get(value.event_id) == value
    assert store.clear(expected_event_ids=[value.event_id] * 100) == 1


@pytest.mark.parametrize("payload", ["not json", "{}", '{"query":"synthetic-private"}'])
def test_corrupt_rows_fail_closed_without_leaking_payload(store, database, payload):
    value = event()
    store.record(value)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE call_events SET payload=?", (payload,))
    for read in (store.list, lambda: store.get(value.event_id)):
        with pytest.raises(CallEventStoreUnavailable, match="^call_event_store_unavailable$"):
            read()


def test_indexed_metadata_must_match_payload(store, database):
    value = event()
    store.record(value)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE call_events SET host_id='cursor'")
    with pytest.raises(CallEventStoreUnavailable):
        store.list()


def test_bad_database_missing_schema_and_deleted_file_fail_closed(tmp_path, database):
    bad = tmp_path / "bad.sqlite3"
    bad.write_text("not sqlite", encoding="utf-8")
    broken = CallEventStore(bad, retention_days=1, max_events=1)
    for operation in (broken.initialize, broken.list):
        with pytest.raises(CallEventStoreUnavailable):
            operation()
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE call_events (payload TEXT)")
    wrong = CallEventStore(database, retention_days=1, max_events=1)
    for operation in (wrong.initialize, wrong.list, lambda: wrong.record(event())):
        with pytest.raises(CallEventStoreUnavailable):
            operation()
    database.unlink()
    for operation in (wrong.initialize, wrong.list, lambda: wrong.record(event())):
        with pytest.raises(CallEventStoreUnavailable):
            operation()
    assert not database.exists()


def test_read_errors_are_not_empty_results(store, monkeypatch):
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic private path")

    close_main_databases()  # pooled connections would skip the patch

    monkeypatch.setattr(module.sqlite3, "connect", unavailable)
    with pytest.raises(CallEventStoreUnavailable, match="^call_event_store_unavailable$"):
        store.list()


def test_unexpected_trigger_cannot_delete_evidence(store, database):
    value = event()
    store.record(value)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(
            "CREATE TRIGGER unexpected AFTER DELETE ON call_events BEGIN DELETE FROM evidence; END"
        )
    with pytest.raises(CallEventStoreUnavailable):
        store.clear(expected_event_ids=[value.event_id])
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM call_events").fetchone()[0] == 1


def test_timestamp_outside_utc_range_is_validation_error():
    with pytest.raises(ValidationError):
        event(occurred_at=datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=14))))


def test_conflict_does_not_prune_expired_rows(store, database, monkeypatch):
    original = event(occurred_at=NOW - timedelta(days=30))
    store.record(original)
    monkeypatch.setattr(module, "_now", lambda: NOW + timedelta(seconds=1))
    with pytest.raises(CallEventConflict):
        store.record(event(**{**original.model_dump(), "state": "partial"}))
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT count(*) FROM call_events").fetchone()[0] == 1


def test_insert_and_pruning_roll_back_together(store, database, monkeypatch):
    old = event(occurred_at=NOW - timedelta(days=30))
    store.record(old)
    monkeypatch.setattr(module, "_now", lambda: NOW + timedelta(seconds=1))
    prune = store._prune

    def fail_after_pruning(db, cutoff):
        prune(db, cutoff)
        raise sqlite3.OperationalError("synthetic failure")

    monkeypatch.setattr(store, "_prune", fail_after_pruning)
    with pytest.raises(CallEventStoreUnavailable):
        store.record(event())
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT event_id FROM call_events").fetchall() == [(str(old.event_id),)]
        assert db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1


def test_clear_rolls_back_entire_set_on_late_delete_error(store, database, monkeypatch):
    first, second = event(), event()
    store.record(first)
    store.record(second)
    connect = module.sqlite3.connect

    class FailingConnection(sqlite3.Connection):
        deletes = 0

        def execute(self, sql, parameters=()):
            if sql.startswith("DELETE FROM call_events"):
                self.deletes += 1
                if self.deletes == 2:
                    raise sqlite3.OperationalError("synthetic failure")
            return super().execute(sql, parameters)

    def failing_connect(*args, **kwargs):
        return connect(*args, **kwargs, factory=FailingConnection)

    close_main_databases()  # pooled connections would skip the patch

    monkeypatch.setattr(module.sqlite3, "connect", failing_connect)
    with pytest.raises(CallEventStoreUnavailable):
        store.clear(expected_event_ids=[first.event_id, second.event_id])
    assert store.list().total == 2
    with closing(connect(database)) as db:
        assert db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1


def test_initialization_failure_rolls_back_new_objects(database):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE call_events_time (unrelated TEXT)")
    store = CallEventStore(database, retention_days=1, max_events=1)
    with pytest.raises(CallEventStoreUnavailable):
        store.initialize()
    with closing(sqlite3.connect(database)) as db:
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall() == [("call_events_time",), ("evidence",)]


@pytest.mark.parametrize(
    "source",
    [
        "",
        "Codex",
        "codex_export",
        "x" * 129,
        "/private/path",
        "https://example.invalid",
        "two words",
        "codex\n",
        "x\x00y",
    ],
)
def test_source_ids_use_context_source_identifier_contract(source):
    with pytest.raises(ValidationError):
        CallReference(kind="raw", id="evidence-1", revision=1, source_id=source)


@pytest.mark.parametrize("source", [None, "codex", "chatgpt-export", "manual-notes", "x" * 128])
def test_source_identifier_boundaries(source):
    assert (
        CallReference(kind="raw", id="evidence-1", revision=1, source_id=source).source_id == source
    )


@pytest.mark.parametrize(
    "control", ["\x00", "\n", "\r", "\t", "\x1f", "\x7f", "\x85", "\u202e", "\ud800"]
)
def test_reference_identifiers_reject_control_format_and_surrogate_characters(control):
    with pytest.raises(ValidationError):
        CallReference(kind="raw", id=f"evidence{control}1", revision=1, source_id=None)


def test_total_result_count_bound_and_reference_kind_consistency():
    assert event(raw_count=10, memory_count=10).raw_count == 10
    with pytest.raises(ValidationError):
        event(raw_count=11, memory_count=10)
    with pytest.raises(ValidationError):
        event(raw_count=20, memory_count=20)
    for counts in ({"raw_count": 0}, {"memory_count": 0}):
        with pytest.raises(ValidationError):
            event(**counts)
    assert event(raw_count=0, memory_count=0, references=()).references == ()
    # Counts are result items, not references: raw items can contain many messages,
    # and shared references may be deduplicated across multiple result items.
    reference = CallReference(kind="raw", id="evidence-1", revision=1, source_id=None)
    assert len(event(raw_count=1, memory_count=0, references=(reference,) * 128).references) == 128
    assert len(event(raw_count=20, memory_count=0, references=(reference,)).references) == 1


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("escaped", [False, True])
def test_stored_duplicate_json_keys_fail_closed(store, database, nested, escaped):
    value = event()
    store.record(value)
    data = value.model_dump_json()
    key, replacement = ('"raw_count":1', '"raw_count":1,"raw_count":1')
    if nested:
        key, replacement = ('"revision":1', '"revision":1,"revision":1')
    if escaped:
        replacement = replacement.replace('1,"r', '1,"\\u0072')
    data = data.replace(key, replacement, 1)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE call_events SET payload=?", (data,))
    for operation in (store.list, lambda: store.get(value.event_id), lambda: store.record(value)):
        with pytest.raises(CallEventStoreUnavailable, match="^call_event_store_unavailable$"):
            operation()


@pytest.mark.parametrize(
    "cell", ["x" * (128 * 1024 + 1), "\u00e9" * 70000, b"x" * 200000, "[" * 2000]
)
def test_corrupt_payload_size_type_or_depth_fails_closed(store, database, cell):
    value = event()
    store.record(value)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE call_events SET payload=?", (cell,))
    for operation in (store.list, lambda: store.get(value.event_id), lambda: store.record(value)):
        with pytest.raises(CallEventStoreUnavailable, match="^call_event_store_unavailable$"):
            operation()


def test_sql_never_returns_oversized_payload_to_python(store, database, monkeypatch):
    value = event()
    store.record(value)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE call_events SET payload=?", ("x" * 1000000,))
    observed = []
    parse = module._event

    def inspect_row(row):
        observed.append(row["payload"])
        assert row["payload"] is None or len(row["payload"]) <= 128 * 1024
        return parse(row)

    monkeypatch.setattr(module, "_event", inspect_row)
    for operation in (store.list, lambda: store.get(value.event_id), lambda: store.record(value)):
        with pytest.raises(CallEventStoreUnavailable):
            operation()
    assert len(observed) == 3


def test_stored_utf8_byte_cap_inclusive_boundary(store, database):
    value = event()
    store.record(value)
    data = value.model_dump_json()
    padded = data + " " * (128 * 1024 - len(data.encode("utf-8")))
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE call_events SET payload=?", (padded,))
    assert store.get(value.event_id) == value
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE call_events SET payload=?", (padded + " ",))
    with pytest.raises(CallEventStoreUnavailable):
        store.get(value.event_id)


def test_oversized_valid_json_is_rejected_before_parsing(store, database, monkeypatch):
    value = event()
    store.record(value)
    payload = value.model_dump_json() + " " * (128 * 1024)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE call_events SET payload=?", (payload,))

    def unexpected_parse(*args, **kwargs):
        pytest.fail("oversized payload reached JSON parser")

    monkeypatch.setattr(module.json, "loads", unexpected_parse)
    for operation in (store.list, lambda: store.get(value.event_id), lambda: store.record(value)):
        with pytest.raises(CallEventStoreUnavailable):
            operation()


def test_valid_json_blob_is_not_a_text_payload(store, database):
    value = event()
    store.record(value)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE call_events SET payload=?", (value.model_dump_json().encode("utf-8"),))
    for operation in (store.list, lambda: store.get(value.event_id), lambda: store.record(value)):
        with pytest.raises(CallEventStoreUnavailable):
            operation()


def test_write_byte_cap_does_not_insert_or_prune(store, database):
    reference = CallReference(kind="raw", id="\u4e00" * 512, revision=1, source_id=None)
    value = event(raw_count=1, memory_count=0, references=(reference,) * 128)
    assert len(value.model_dump_json().encode("utf-8")) > 128 * 1024
    with pytest.raises(ValueError, match="call_event_payload_too_large"):
        store.record(value)
    assert store.list().total == 0
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1


def test_128_ascii_references_fit_payload_cap(store):
    reference = CallReference(kind="raw", id="x" * 512, revision=1, source_id="x" * 128)
    value = event(raw_count=1, memory_count=0, references=(reference,) * 128)
    assert len(value.model_dump_json().encode("utf-8")) < 128 * 1024
    assert store.record(value)
    assert store.get(value.event_id) == value


@pytest.mark.parametrize("model", [CallEvent, CallReference])
def test_every_metadata_field_is_explicit_and_extras_forbidden(model):
    instance = event() if model is CallEvent else event().references[0]
    values = instance.model_dump()
    if model is CallEvent:
        assert (values["stage"] == "feedback") == (values["feedback"] is not None)
    for field in values:
        if model is CallEvent and field == "feedback":
            continue
        missing = {key: value for key, value in values.items() if key != field}
        with pytest.raises(ValidationError):
            model.model_validate(missing)
    with pytest.raises(ValidationError):
        model.model_validate({**values, "secret": "synthetic-secret"})


def test_delivery_moves_forward_once_without_claiming_adoption(store):
    value = event()
    assert store.record(value) is True

    assert (
        store.mark_delivery(
            value.event_id,
            delivery="delivered",
            host_session_id="workbuddy-session-1",
            injection_elapsed_ms=812.5,
        )
        is True
    )
    recorded = store.get(value.event_id)
    assert recorded.delivery == "delivered"
    assert recorded.adoption == "unknown"
    assert recorded.host_session_id == "workbuddy-session-1"
    assert recorded.injection_elapsed_ms == 812.5


def test_settled_delivery_is_idempotent_and_never_rewritten(store):
    value = event()
    store.record(value)
    assert (
        store.mark_delivery(
            value.event_id,
            delivery="not_delivered",
            host_session_id="workbuddy-session-1",
            injection_elapsed_ms=3500,
        )
        is True
    )

    assert (
        store.mark_delivery(
            value.event_id,
            delivery="delivered",
            host_session_id="workbuddy-session-2",
            injection_elapsed_ms=1,
        )
        is False
    )
    recorded = store.get(value.event_id)
    assert recorded.delivery == "not_delivered"
    assert recorded.host_session_id == "workbuddy-session-1"
    assert recorded.injection_elapsed_ms == 3500


def test_delivery_report_for_missing_event_does_not_resurrect_it(store):
    assert (
        store.mark_delivery(
            uuid4(),
            delivery="delivered",
            host_session_id="workbuddy-session-1",
            injection_elapsed_ms=10,
        )
        is None
    )


def test_delivery_unknown_is_not_a_writable_report(store):
    value = event()
    store.record(value)
    with pytest.raises(ValueError, match="call_event_delivery_immutable_unknown"):
        store.mark_delivery(
            value.event_id,
            delivery="unknown",
            host_session_id="workbuddy-session-1",
            injection_elapsed_ms=10,
        )


def test_legacy_retained_event_reads_with_unknown_delivery(store, database):
    value = event()
    legacy = value.model_dump(mode="json")
    legacy.pop("delivery")
    legacy.pop("host_session_id")
    legacy.pop("injection_elapsed_ms")
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(
            "INSERT INTO call_events(event_id,occurred_at,host_id,payload) VALUES (?,?,?,?)",
            (
                str(value.event_id),
                value.occurred_at.isoformat(timespec="microseconds"),
                value.host_id,
                json.dumps(legacy),
            ),
        )

    restored = store.get(value.event_id)
    assert restored is not None
    assert restored.delivery == "unknown"
    assert restored.adoption == "unknown"
    assert restored.host_session_id is None
    assert restored.injection_elapsed_ms is None


def test_partial_delivery_metadata_is_not_misread_as_a_legacy_event(store, database):
    value = event()
    corrupt = value.model_dump(mode="json")
    corrupt.pop("delivery")
    with closing(sqlite3.connect(database)) as db, db:
        db.execute(
            "INSERT INTO call_events(event_id,occurred_at,host_id,payload) VALUES (?,?,?,?)",
            (
                str(value.event_id),
                value.occurred_at.isoformat(timespec="microseconds"),
                value.host_id,
                json.dumps(corrupt),
            ),
        )

    with pytest.raises(CallEventStoreUnavailable):
        store.get(value.event_id)


def test_concurrent_delivery_reports_settle_exactly_once(store):
    value = event()
    store.record(value)

    def report(delivery, session):
        return store.mark_delivery(
            value.event_id,
            delivery=delivery,
            host_session_id=session,
            injection_elapsed_ms=12,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda args: report(*args),
                (("delivered", "session-a"), ("not_delivered", "session-b")),
            )
        )

    assert sorted(outcomes) == [False, True]
    recorded = store.get(value.event_id)
    assert recorded.delivery in {"delivered", "not_delivered"}
    expected_session = "session-a" if recorded.delivery == "delivered" else "session-b"
    assert recorded.host_session_id == expected_session
    assert recorded.adoption == "unknown"
