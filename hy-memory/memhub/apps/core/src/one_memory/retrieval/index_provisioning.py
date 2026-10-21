"""Publish one active generation for the built-in encoder, when asked to.

The runtime deliberately only resumes an index somebody already initialized, so
without this the feature could be switched on and still never index anything.
Provisioning stays separate from `start()` for the same reason it exists: it is
the one place allowed to create, and it creates only for a first enable.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from one_memory.database_access import main_database
from one_memory.embedding_assets import assets_present
from one_memory.retrieval.index_store import RetrievalIndexStore
from one_memory.retrieval.index_worker import LocalRetrievalEncoder
from one_memory.retrieval.vector_store import RawVectorStore

DATABASE_NAME = "one-memory.sqlite3"
VECTOR_DIR_NAME = "retrieval-vectors"


def provision_retrieval_index(data_dir: Path) -> str | None:
    """The active generation id for the built-in encoder, creating it once.

    Returns None whenever the right answer is to leave the data alone: no
    built-in encoder, no database yet, an index from an older schema, or one
    already published for a different encoder. None is not an error; the
    lexical lane works without an index and says so through `degraded`.
    """
    database = data_dir / DATABASE_NAME
    if not assets_present() or not database.is_file():
        return None
    identity = LocalRetrievalEncoder().identity
    store = RetrievalIndexStore(database)
    try:
        with main_database(database).write() as db, db:
            db.execute("BEGIN IMMEDIATE")
            if (existing := _published(db)) is not None:
                return existing if _matches(store, db, existing, identity) else None
            version = _schema_version(db)
            if version == 1:
                # Someone's v1 index. Migrating it is maintenance, not startup.
                return None
            if version is None:
                store.initialize_v2(db)
            generation = store.create_generation(db, identity)
        store.activate_generation(generation)
        _ensure_vectors(data_dir / VECTOR_DIR_NAME, generation, identity.dimensions)
    except Exception:
        logging.getLogger(__name__).warning("retrieval_index_provision_failed", exc_info=True)
        return None
    return generation


def _schema_version(db: sqlite3.Connection) -> int | None:
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='retrieval_index_state'"
    ).fetchone():
        return None
    row = db.execute(
        "SELECT schema_version FROM retrieval_index_state WHERE singleton=1"
    ).fetchone()
    return None if row is None else int(row[0])


def _published(db: sqlite3.Connection) -> str | None:
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='retrieval_index_generations'"
    ).fetchone():
        return None
    rows = db.execute(
        "SELECT generation_id FROM retrieval_index_generations WHERE state='active' LIMIT 2"
    ).fetchall()
    return str(rows[0][0]) if len(rows) == 1 else None


def _matches(
    store: RetrievalIndexStore,
    db: sqlite3.Connection,
    generation: str,
    identity: object,
) -> bool:
    try:
        return store._identity(db, generation) == identity
    except Exception:
        return False


def _ensure_vectors(directory: Path, generation: str, dimensions: int) -> None:
    if directory.exists():
        return
    vectors = RawVectorStore.create(directory, generation_id=generation, dimensions=dimensions)
    vectors.close()
