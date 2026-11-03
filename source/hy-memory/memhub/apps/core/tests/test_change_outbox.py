"""Evidence imports no longer feed the dormant change outbox."""

import sqlite3
from contextlib import closing

from one_memory.change_outbox import ChangeOutbox, evidence_event_id
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore


def _evidence(verbatim: str = "SECRET_DECISION") -> EvidenceInput:
    return EvidenceInput(
        source_id="workbuddy",
        conversation_id="session-a",
        message_id="m1",
        role="user",
        written_by=WrittenBy.PERSON,
        verbatim=verbatim,
        origin_meta={EvidenceOrigin.FILE: OriginMetadata(raw_meta={"root": "proj"})},
    )


def test_evidence_writes_do_not_append_to_the_dormant_outbox(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    outbox = ChangeOutbox(path)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        created = store.put(_evidence(), connection=db)
        revised = store.put(_evidence("UPDATED_DECISION"), connection=db)
        unchanged = store.put(_evidence("UPDATED_DECISION"), connection=db)
        db.commit()

    assert created.was_created is True
    assert revised.was_revised is True
    assert unchanged.was_created is False
    assert unchanged.was_revised is False
    assert outbox.pending() == ()
    with closing(sqlite3.connect(path)) as db:
        stored = db.execute("SELECT * FROM change_outbox").fetchall()
    assert stored == []


def test_existing_outbox_write_and_read_apis_remain_available(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    outbox = ChangeOutbox(path)

    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        saved = store.put(_evidence(), connection=db)
        outbox.record(
            db,
            event_id=evidence_event_id(saved.record.evidence_id, saved.record.revision),
            cause="import",
            evidence_id=saved.record.evidence_id,
            evidence_revision=saved.record.revision,
            permission_epoch=0,
        )
        db.commit()

    pending = ChangeOutbox(path).pending()
    assert len(pending) == 1
    assert pending[0].evidence_id == saved.record.evidence_id
    assert pending[0].notified is False
    with closing(sqlite3.connect(path)) as db:
        stored = db.execute("SELECT * FROM change_outbox").fetchall()
    assert stored
    assert "SECRET_DECISION" not in "\n".join(str(cell) for row in stored for cell in row)
