"""The index has to come up through the product, not through a test helper.

Every existing retrieval test builds its generation by hand, so none of them
can tell whether a user who enables the feature ever gets an index at all.
"""

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from one_memory.imports.storage import EvidenceStore
from one_memory.retrieval.index_provisioning import provision_retrieval_index
from one_memory.retrieval.index_store import RetrievalIndexStore
from one_memory.retrieval.index_worker import LocalRetrievalEncoder


def database(tmp_path: Path) -> Path:
    path = tmp_path / "one-memory.sqlite3"
    EvidenceStore(path)
    return path


def active(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='retrieval_index_generations'"
        ).fetchone():
            return []
        return [
            row[0]
            for row in db.execute(
                "SELECT generation_id FROM retrieval_index_generations WHERE state='active'"
            )
        ]


def test_first_enable_publishes_one_active_generation_and_its_vector_store(tmp_path):
    database(tmp_path)

    generation = provision_retrieval_index(tmp_path)

    assert generation is not None
    assert active(tmp_path / "one-memory.sqlite3") == [generation]
    assert (tmp_path / "retrieval-vectors").is_dir()


def test_second_start_reuses_the_same_generation_rather_than_stacking_one(tmp_path):
    database(tmp_path)

    first = provision_retrieval_index(tmp_path)
    second = provision_retrieval_index(tmp_path)

    assert first == second
    assert active(tmp_path / "one-memory.sqlite3") == [first]


def test_a_v1_index_is_left_alone_instead_of_being_migrated_on_startup(tmp_path, caplog):
    """Falsifiable against the first test, where provisioning does publish one.

    Migrating someone's existing index while they were only starting the app is
    the one thing the schema note rules out, so this must stay a no-op. The
    absence of a warning is asserted too: crashing into the same `None` would
    otherwise read as a deliberate decision.
    """
    path = database(tmp_path)
    store = RetrievalIndexStore(path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        store.initialize(db)

    with caplog.at_level(logging.WARNING):
        assert provision_retrieval_index(tmp_path) is None
    assert active(path) == []
    assert "retrieval_index_provision_failed" not in caplog.text
    with closing(sqlite3.connect(path)) as db:
        version = db.execute("SELECT schema_version FROM retrieval_index_state").fetchone()[0]
    assert version == 1


def test_a_generation_for_another_encoder_is_not_swapped_out_silently(tmp_path):
    path = database(tmp_path)
    store = RetrievalIndexStore(path)
    other = LocalRetrievalEncoder(content_version=1).identity
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        store.initialize(db)
        store.migrate_v2(db)
        foreign = store.create_generation(db, other)
    store.activate_generation(foreign)

    assert provision_retrieval_index(tmp_path) is None
    assert active(path) == [foreign]


def test_without_the_built_in_encoder_no_index_is_created(tmp_path, monkeypatch):
    path = database(tmp_path)
    monkeypatch.setattr(
        "one_memory.retrieval.index_provisioning.assets_present", lambda *_args: False
    )

    assert provision_retrieval_index(tmp_path) is None
    assert active(path) == []
    assert not (tmp_path / "retrieval-vectors").exists()


def test_a_missing_database_is_not_created_by_provisioning(tmp_path):
    assert provision_retrieval_index(tmp_path) is None
    assert not (tmp_path / "one-memory.sqlite3").exists()
    assert not (tmp_path / "retrieval-vectors").exists()


@pytest.mark.parametrize("failure", ["initialize_v2", "create_generation"])
def test_a_failed_provision_reports_none_instead_of_half_an_index(tmp_path, monkeypatch, failure):
    path = database(tmp_path)

    def explode(*_args, **_kwargs):
        raise sqlite3.OperationalError("synthetic")

    monkeypatch.setattr(RetrievalIndexStore, failure, explode)

    assert provision_retrieval_index(tmp_path) is None
    assert active(path) == []
