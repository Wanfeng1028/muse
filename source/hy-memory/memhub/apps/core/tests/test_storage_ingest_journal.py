import asyncio
import sqlite3
from contextlib import closing

import pytest

from one_memory import ingest_journal as journal
from one_memory.imports.adapters import ScannedEvidence
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.runner import ImportRunner
from one_memory.imports.storage import EvidenceStore
from tests.test_import_runner import FixtureAdapter, cursor, evidence, stores


def value(key="a", **changes):
    fields = dict(
        source_id="cursor",
        conversation_id="thread",
        message_id=key,
        role="user",
        written_by=WrittenBy.PERSON,
        verbatim="Synthetic message",
        origin_meta={EvidenceOrigin.FILE: OriginMetadata(raw_meta={"path": "synthetic"})},
    )
    fields.update(changes)
    return EvidenceInput(**fields)


def initialize(store):
    with store._connect(writing=True) as db:
        journal.initialize(db)


def head(store, key):
    with store._connect() as db:
        return journal.current(db, "local", key)


def test_legacy_put_and_reopen_never_initialize_journal(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path / "legacy.sqlite3")
    monkeypatch.setattr(journal, "record", lambda *a, **k: pytest.fail("legacy journal write"))
    store.put(value())
    store.put(value(verbatim="changed"))
    EvidenceStore(store.database_path)
    with store._connect() as db:
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'evidence_ingest%'"
        ).fetchall()


def test_initialized_put_records_final_origins_create_revision_and_noop(tmp_path):
    store = EvidenceStore(tmp_path / "journal.sqlite3")
    initialize(store)
    record = store.put(value()).record
    first = head(store, record.evidence_id)
    assert first is not None and first.kind == "create" and first.generation_eligible
    with store._connect() as db:
        assert journal.matches_current(db, first)
    store.put(value())
    assert head(store, record.evidence_id) == first
    store.put(value(verbatim="Revised"))
    revised = head(store, record.evidence_id)
    assert (
        revised.kind == "revise" and revised.generation_eligible and revised.evidence_revision == 2
    )
    store.put(
        value(
            verbatim="Revised",
            origin_meta={EvidenceOrigin.HOOK: OriginMetadata(raw_meta={"nested": {"all": [1, 2]}})},
        )
    )
    updated = head(store, record.evidence_id)
    assert updated.kind == "metadata" and updated.generation_eligible
    assert updated.origin_hash != revised.origin_hash
    with store._connect() as db:
        assert journal.matches_current(db, updated)
        assert not journal.matches_current(db, revised)


def test_attribution_propagation_journals_old_rows_as_maintenance_only(tmp_path):
    store = EvidenceStore(tmp_path / "journal.sqlite3")
    old = [store.put(value(key)).record for key in ("a", "b")]
    unrelated = store.put(value("other", conversation_id="other")).record
    foreign = store.put(value("foreign", user_id="other")).record
    initialize(store)
    before = {item.evidence_id: head(store, item.evidence_id) for item in old}
    new = store.put(value("c", workspace="/synthetic/project", project="project")).record
    current = head(store, new.evidence_id)
    assert current.kind == "create" and current.generation_eligible
    for item in old:
        updated = head(store, item.evidence_id)
        assert updated.seq > before[item.evidence_id].seq
        assert updated.kind == "metadata" and not updated.generation_eligible
        with store._connect() as db:
            assert journal.matches_current(db, updated)
    assert store.get(unrelated.evidence_id).workspace is None
    assert store.get(foreign.evidence_id).workspace is None
    with store._connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM evidence_ingest_events WHERE evidence_id=?",
                (new.evidence_id,),
            ).fetchone()[0]
            == 1
        )
        before_seq = journal.watermark(db)
    store.put(value("c", workspace="/synthetic/project", project="project"))
    with store._connect() as db:
        assert journal.watermark(db) == before_seq


@pytest.mark.parametrize("caller", [False, True])
def test_journal_failure_rolls_back_whole_put_not_just_event(tmp_path, monkeypatch, caller):
    store = EvidenceStore(tmp_path / "journal.sqlite3")
    old = store.put(value()).record
    initialize(store)
    original = journal.record

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic finalize failure")

    monkeypatch.setattr(journal, "record", fail)
    if caller:
        with store._connect(writing=True) as db:
            db.execute("CREATE TABLE caller_marker(value TEXT)")
            db.execute("INSERT INTO caller_marker VALUES ('retain')")
            with pytest.raises(RuntimeError, match="synthetic"):
                store.put(value("b", workspace="/new", project="new"), connection=db)
            assert db.in_transaction
            assert db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM caller_marker").fetchone()[0] == 1
    else:
        with pytest.raises(RuntimeError, match="synthetic"):
            store.put(value("b", workspace="/new", project="new"))
    assert store.count() == 1
    assert store.get(old.evidence_id).workspace is None
    assert head(store, old.evidence_id).kind == "migration_baseline"


def test_caller_transaction_rollback_and_autocommit_rejection(tmp_path):
    store = EvidenceStore(tmp_path / "journal.sqlite3")
    initialize(store)
    with closing(sqlite3.connect(store.database_path, autocommit=True)) as db:
        db.row_factory = sqlite3.Row
        with pytest.raises(RuntimeError):
            store.put(value(), connection=db)
        assert store.count() == 0
        db.execute("BEGIN IMMEDIATE")
        item = store.put(value(), connection=db).record
        assert journal.current(db, "local", item.evidence_id) is not None
        assert store.count() == 0
        db.execute("ROLLBACK")
    assert store.count() == 0
    with store._connect() as db:
        assert journal.watermark(db) == 0


@pytest.mark.parametrize("repair", ["cursor_host_authorship", "cursor_conversation_attribution"])
def test_startup_repairs_invalidate_as_maintenance_and_reopen_does_not_rehash(
    tmp_path, monkeypatch, repair
):
    store = EvidenceStore(tmp_path / "repair.sqlite3")
    first = store.put(value("a", verbatim="<dynamic_tool_catalog>synthetic")).record
    second = store.put(value("b")).record
    with store._connect(writing=True) as db:
        if repair == "cursor_conversation_attribution":
            db.execute(
                "UPDATE evidence SET workspace='/project',project='p' WHERE evidence_id=?",
                (second.evidence_id,),
            )
        journal.initialize(db)
        old = journal.current(db, "local", first.evidence_id)
        db.execute("DELETE FROM evidence_repairs WHERE name=?", (repair,))
    EvidenceStore(store.database_path)
    updated = head(store, first.evidence_id)
    assert updated.seq > old.seq and not updated.generation_eligible
    assert updated.kind == "metadata"
    with store._connect() as db:
        assert journal.matches_current(db, updated)
        count = journal.watermark(db)
    monkeypatch.setattr(
        journal, "record", lambda *a, **k: pytest.fail("completed boot rehashed evidence")
    )
    EvidenceStore(store.database_path)
    with store._connect() as db:
        assert journal.watermark(db) == count


@pytest.mark.parametrize("fail_checkpoint", [False, True])
def test_real_import_runner_event_and_checkpoint_share_transaction(
    tmp_path, monkeypatch, fail_checkpoint
):
    records, jobs = stores(tmp_path)
    initialize(records)
    job = jobs.create(user_id="local", source_id="fixture")
    observed = []
    original = jobs.record_evidence

    def checkpoint(*args, **kwargs):
        with records._connect() as reader:
            assert journal.watermark(reader) == 0
        db = kwargs["connection"]
        assert journal.watermark(db) > 0
        result = original(*args, **kwargs)
        if fail_checkpoint:
            raise RuntimeError("synthetic checkpoint failure")
        return result

    monkeypatch.setattr(jobs, "record_evidence", checkpoint)
    runner = ImportRunner(evidence_store=records, job_store=jobs, on_evidence=observed.append)

    async def run():
        return await runner.run(
            adapter=FixtureAdapter(
                [ScannedEvidence(evidence=evidence("1"), cursor=cursor("line:1"))]
            ),
            job_id=job.job_id,
        )

    if fail_checkpoint:
        with pytest.raises(RuntimeError, match="synthetic"):
            asyncio.run(run())
        assert records.count() == 0 and observed == []
        assert jobs.require(job.job_id).checkpoint is None
        with records._connect() as db:
            assert journal.watermark(db) == 0
    else:
        result = asyncio.run(run())
        assert result.stored == 1 and len(observed) == 1
        assert head(records, evidence("1").evidence_id).generation_eligible


def test_metadata_only_update_and_old_duplicate_never_authorize_baseline(tmp_path):
    store = EvidenceStore(tmp_path / "journal.sqlite3")
    old = store.put(value()).record
    initialize(store)
    before = head(store, old.evidence_id)
    store.put(value())
    assert head(store, old.evidence_id) == before
    store.put(value(project="scope"))
    after = head(store, old.evidence_id)
    assert after.kind == "metadata" and not after.generation_eligible
    assert after.seq > before.seq
    assert store.get(old.evidence_id).revision == old.revision


def test_incomplete_journal_refuses_put_before_any_evidence_write(tmp_path):
    store = EvidenceStore(tmp_path / "journal.sqlite3")
    initialize(store)
    with store._connect(writing=True) as db:
        db.execute("DELETE FROM evidence_ingest_journal_state")
    with pytest.raises(RuntimeError, match="not_initialized"):
        store.put(value())
    assert store.count() == 0


def test_failed_startup_journal_rolls_back_repair_and_claim(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path / "repair.sqlite3")
    original = store.put(value(verbatim="<dynamic_tool_catalog>synthetic")).record
    initialize(store)
    with store._connect(writing=True) as db:
        db.execute("DELETE FROM evidence_repairs WHERE name='cursor_host_authorship'")
    record_event = journal.record

    def fail(*args, **kwargs):
        record_event(*args, **kwargs)
        raise RuntimeError("synthetic repair finalize failure")

    monkeypatch.setattr(journal, "record", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        EvidenceStore(store.database_path)
    assert store.get(original.evidence_id) == original
    assert head(store, original.evidence_id).kind == "migration_baseline"
    with store._connect() as db:
        assert not db.execute(
            "SELECT 1 FROM evidence_repairs WHERE name='cursor_host_authorship'"
        ).fetchone()


def test_direct_maintenance_create_and_duplicate_import_stays_ineligible(tmp_path):
    store = EvidenceStore(tmp_path / "journal.sqlite3")
    initialize(store)
    item = value()
    with store._connect(writing=True) as db:
        # Maintenance is not an import put. Use a direct repair-like insertion.
        db.execute(
            """INSERT INTO evidence
            (evidence_id,idempotency_key,user_id,source_id,conversation_id,message_id,
             role,written_by,verbatim,content_hash,revision,imported_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,1,'2026-09-19','2026-09-19')""",
            (
                item.evidence_id,
                item.idempotency_key,
                item.user_id,
                item.source_id,
                item.conversation_id,
                item.message_id,
                item.role,
                item.written_by,
                item.verbatim,
                item.content_hash,
            ),
        )
        db.execute(
            "INSERT INTO evidence_origins VALUES (?,?,?,?,?)",
            (item.evidence_id, "file", '{"path":"synthetic"}', None, "2026-09-19"),
        )
        observed = journal.record(db, item.evidence_id, cause="maintenance")
    assert not observed.generation_eligible
    store.put(item)
    assert head(store, item.evidence_id) == observed
