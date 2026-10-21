"""Explicit derived-index transactions. No constructor migration or model invocation."""

import hashlib
import json
import math
import sqlite3
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from one_memory import ingest_journal as journal
from one_memory.context_raw import _check, _connection
from one_memory.database import take_the_write_lock_first
from one_memory.database_access import main_database
from one_memory.imports.models import EvidenceRecord
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_server.migrations import (
    _split_statements,
    retrieval_build_maps_ddl,
    retrieval_documents_v2_ddl,
    retrieval_index_ddl,
)
from one_memory.retrieval.chunking import TextChunk
from one_memory.retrieval.content import index_content, validate_chunk_coverage
from one_memory.retrieval.mapped_content import ContentMap, PreparedMappedContent
from one_memory.retrieval.models import TimeRange


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class EncoderIdentity:
    encoder_id: str
    encoder_digest: str
    tokenizer_digest: str
    dimensions: int
    chunker_version: int = 1
    normalizer_version: int = 1
    query_template_version: int = 1

    def __post_init__(self) -> None:
        if not self.encoder_id or len(self.encoder_id) > 128:
            raise ValueError("invalid_encoder")
        for value in (self.encoder_digest, self.tokenizer_digest):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("invalid_encoder_digest")
        for number in (
            self.dimensions,
            self.chunker_version,
            self.normalizer_version,
            self.query_template_version,
        ):
            if type(number) is not int or not 1 <= number <= 1000000:
                raise ValueError("invalid_encoder_number")


@dataclass(frozen=True)
class IndexLease:
    generation_id: str
    evidence_id: str
    build_id: str
    event_seq: int
    owner: str
    token: str
    expires_at: float
    grant_fingerprint: str


@dataclass(frozen=True)
class PublishedChunk:
    chunk_id: str
    build_id: str
    evidence_id: str
    revision: int
    start_cp: int
    end_cp: int
    ordinal: int
    source_id: str
    event_time: datetime | None


def chunk_identity(lease: IndexLease, chunk: TextChunk, map_digest: str | None = None) -> str:
    values = [lease.build_id, chunk.ordinal, chunk.start_cp, chunk.end_cp, digest(chunk.text)]
    return digest(values if map_digest is None else [*values, map_digest])


@contextmanager
def transaction(db: sqlite3.Connection) -> Iterator[None]:
    if not db.in_transaction:
        raise RuntimeError("retrieval_requires_caller_transaction")
    name = "retrieval_" + uuid4().hex
    previous = db.row_factory
    db.row_factory = sqlite3.Row
    db.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        db.execute(f"ROLLBACK TO {name}")
        db.execute(f"RELEASE {name}")
        raise
    else:
        db.execute(f"RELEASE {name}")
    finally:
        db.row_factory = previous


class RetrievalIndexStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    @contextmanager
    def _db(
        self, *, write: bool = False, deadline: float | None = None
    ) -> Iterator[sqlite3.Connection]:
        if deadline is not None:
            if write:
                raise ValueError("deadline_connection_is_read_only")
            with _connection(self.database_path, deadline) as db:
                db.execute("PRAGMA query_only=ON")
                yield db
            return
        database = main_database(self.database_path)
        with (
            database.write(create=False, foreign_keys=True, row_factory=sqlite3.Row)
            if write
            else database.read(foreign_keys=True, row_factory=sqlite3.Row)
        ) as db:
            try:
                if write:
                    take_the_write_lock_first(db)
                else:
                    db.execute("PRAGMA query_only=ON")
                    db.execute("BEGIN")
                yield db
                if write:
                    db.commit()
            except BaseException:
                db.rollback()
                raise

    def initialize(self, db: sqlite3.Connection) -> None:
        """Caller owns maintenance/exclusive writer admission; rollback includes baseline."""
        self._initialize(db, version=1)

    def initialize_v2(self, db: sqlite3.Connection) -> None:
        """Initialize a fresh store directly at the folded v2 schema.

        Startup provisioning uses this path so a brand-new database does not
        create a v1 schema and immediately migrate it. Explicit maintenance
        callers keep `initialize()`'s v1 baseline contract instead.
        """
        self._initialize(db, version=2)

    def _initialize(self, db: sqlite3.Connection, *, version: int) -> None:
        with transaction(db):
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='retrieval_index_state'"
            ).fetchone()
            if exists:
                self._store_id(db)
            elif db.execute(
                "SELECT 1 FROM sqlite_master WHERE name IN ('retrieval_documents',"
                "'retrieval_chunks','retrieval_index_generations','retrieval_consumers')"
            ).fetchone():
                raise ValueError("retrieval_partial_initialization")
            journal.initialize(db)
            # Migration 33 owns the schema. Explicit initialization keeps the
            # maintenance-facing v1 baseline so `migrate_v2` remains observable;
            # startup provisioning may instead ask for the folded v2 directly.
            for sql in _split_statements(retrieval_index_ddl("sqlite", version=version)):
                db.execute(sql)
            row = db.execute(
                "SELECT schema_version FROM retrieval_index_state WHERE singleton=1"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO retrieval_index_state VALUES (1,?,?)",
                    (version, uuid4().hex),
                )
            elif row[0] not in (1, 2):
                raise ValueError("retrieval_schema_mismatch")

    def migrate_v2(self, db: sqlite3.Connection) -> None:
        """Explicit maintenance transaction only; readers/worker never invoke this."""
        with transaction(db):
            self._store_id(db)
            version = db.execute("SELECT schema_version FROM retrieval_index_state").fetchone()[0]
            if version == 2:
                db.execute(
                    "SELECT build_id,source_map_json,map_digest,coverage_state "
                    "FROM retrieval_build_maps LIMIT 0"
                )
                return
            if (
                db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='retrieval_build_maps'"
                ).fetchone()
                is not None
            ):
                # A v1 index must not already own a v2-only table. Treat this
                # as a foreign/partial schema instead of letting `IF NOT
                # EXISTS` silently accept a table with the wrong columns.
                raise sqlite3.OperationalError("retrieval_build_maps already exists")
            # Both tables come from migration 33, named/derived there so this
            # module holds no DDL text of its own.
            db.execute(retrieval_documents_v2_ddl("sqlite"))
            db.execute("INSERT INTO retrieval_documents_v2 SELECT * FROM retrieval_documents")
            db.execute("DROP TABLE retrieval_documents")
            db.execute("ALTER TABLE retrieval_documents_v2 RENAME TO retrieval_documents")
            db.execute(
                "CREATE INDEX retrieval_jobs ON retrieval_documents(generation_id,state,event_seq)"
            )
            db.execute(retrieval_build_maps_ddl("sqlite"))
            db.execute("UPDATE retrieval_index_state SET schema_version=2 WHERE singleton=1")

    @staticmethod
    def _store_id(db: sqlite3.Connection) -> str:
        row = db.execute(
            "SELECT schema_version,data_store_id FROM retrieval_index_state WHERE singleton=1"
        ).fetchone()
        if row is None or row[0] not in (1, 2) or not isinstance(row[1], str) or len(row[1]) != 32:
            raise ValueError("retrieval_not_initialized")
        return str(row[1])

    def create_generation(self, db: sqlite3.Connection, identity: EncoderIdentity) -> str:
        with transaction(db):
            self._check_content_version(db, identity)
            key = digest([self._store_id(db), asdict(identity)])
            encoded = json.dumps(asdict(identity), sort_keys=True)
            row = db.execute(
                "SELECT identity_json FROM retrieval_index_generations WHERE generation_id=?",
                (key,),
            ).fetchone()
            if row is not None and row[0] != encoded:
                raise ValueError("generation_identity_changed")
            if row is None:
                db.execute(
                    "INSERT INTO retrieval_index_generations VALUES (?,?,'building',?)",
                    (key, encoded, time.time()),
                )
                db.execute("INSERT INTO retrieval_consumers VALUES (?,0,0)", (key,))
            return key

    def consume(self, db: sqlite3.Connection, generation_id: str, *, limit: int = 256) -> int:
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("invalid_consume_limit")
        with transaction(db):
            store_id = self._store_id(db)
            generation = db.execute(
                "SELECT state FROM retrieval_index_generations WHERE generation_id=?",
                (generation_id,),
            ).fetchone()
            if generation is None or generation[0] == "retired":
                raise ValueError("generation_not_writable")
            cursor = db.execute(
                "SELECT after_seq FROM retrieval_consumers WHERE generation_id=?", (generation_id,)
            ).fetchone()
            if cursor is None:
                raise ValueError("consumer_missing")
            rows = db.execute(
                "SELECT seq FROM evidence_ingest_events WHERE seq>? ORDER BY seq LIMIT ?",
                (cursor[0], limit),
            ).fetchall()
            for row in rows:
                event = journal.event(db, row[0])
                if event is None:
                    raise ValueError("journal_event_missing")
                if event.user_id != "local":
                    continue
                build = digest(
                    [
                        store_id,
                        generation_id,
                        event.evidence_id,
                        event.incarnation,
                        event.evidence_revision,
                        event.fingerprint,
                    ]
                )
                state = "deleted" if event.kind == "delete" else "pending"
                db.execute(
                    """INSERT INTO retrieval_documents
                    (generation_id,evidence_id,source_id,event_seq,build_id,state)
                    VALUES (?,?,?,?,?,?) ON CONFLICT(generation_id,evidence_id) DO UPDATE SET
                    source_id=excluded.source_id,event_seq=excluded.event_seq,build_id=excluded.build_id,
                    state=excluded.state,active_build_id=NULL,lease_owner=NULL,lease_token=NULL,
                    lease_until=NULL,grant_fingerprint=NULL
                    WHERE excluded.event_seq>retrieval_documents.event_seq""",
                    (generation_id, event.evidence_id, event.source_id, event.seq, build, state),
                )
            if rows:
                db.execute(
                    "UPDATE retrieval_consumers SET after_seq=? WHERE generation_id=?",
                    (rows[-1][0], generation_id),
                )
            return len(rows)

    def consume_pending(self, generation_id: str, *, limit: int = 256) -> int:
        with self._db(write=True) as db:
            return self.consume(db, generation_id, limit=limit)

    def encoder_identity(self, generation_id: str) -> EncoderIdentity:
        with self._db() as db:
            return self._identity(db, generation_id)

    @staticmethod
    def _check_content_version(db: sqlite3.Connection, identity: EncoderIdentity) -> None:
        versions = (identity.normalizer_version, identity.chunker_version)
        if versions not in ((1, 1), (2, 2)):
            raise ValueError("unsupported_content_generation")
        if versions == (2, 2):
            row = db.execute(
                "SELECT schema_version FROM retrieval_index_state WHERE singleton=1"
            ).fetchone()
            if row is None or row[0] != 2:
                raise ValueError("retrieval_schema2_required")

    def _identity(self, db: sqlite3.Connection, generation_id: str) -> EncoderIdentity:
        row = db.execute(
            "SELECT identity_json FROM retrieval_index_generations WHERE generation_id=?",
            (generation_id,),
        ).fetchone()
        if row is None:
            raise ValueError("generation_missing")
        identity = EncoderIdentity(**json.loads(row[0]))
        if digest([self._store_id(db), asdict(identity)]) != generation_id:
            raise ValueError("generation_identity_changed")
        self._check_content_version(db, identity)
        return identity

    def _prepare(
        self, db: sqlite3.Connection, generation_id: str, record: EvidenceRecord
    ) -> PreparedMappedContent | None:
        identity = self._identity(db, generation_id)
        return index_content(
            record,
            normalizer_version=identity.normalizer_version,
            chunker_version=identity.chunker_version,
        )

    @staticmethod
    def _grant(db: sqlite3.Connection, source_id: str) -> str | None:
        row = db.execute(
            """SELECT root_path,candidate_kind,granted_at,root_identity,revision
            FROM source_grants
            WHERE user_id='local' AND source_id=? AND revoked_at IS NULL""",
            (source_id,),
        ).fetchone()
        return digest(tuple(row)) if row and row[3] and row[4] > 0 else None

    def claim(
        self, generation_id: str, owner: str, *, now: float | None = None, lease_seconds: int = 60
    ) -> IndexLease | None:
        now = time.time() if now is None else now
        if not owner or len(owner) > 128 or not math.isfinite(now) or not 1 <= lease_seconds <= 300:
            raise ValueError("invalid_lease")
        with self._db(write=True) as db:
            generation = db.execute(
                "SELECT state FROM retrieval_index_generations WHERE generation_id=?",
                (generation_id,),
            ).fetchone()
            if generation is None or generation[0] == "retired":
                raise ValueError("generation_not_writable")
            rows = db.execute(
                """SELECT * FROM retrieval_documents WHERE generation_id=? AND
                (state='pending' OR (state='leased' AND lease_until<=?))
                ORDER BY event_seq LIMIT 256""",
                (generation_id, now),
            ).fetchall()
            for row in rows:
                event = journal.event(db, row["event_seq"])
                grant = self._grant(db, row["source_id"])
                if event is None or grant is None or not journal.matches_current(db, event):
                    db.execute(
                        "UPDATE retrieval_documents SET state='blocked',active_build_id=NULL "
                        "WHERE generation_id=? AND evidence_id=?",
                        (generation_id, row["evidence_id"]),
                    )
                    continue
                token = uuid4().hex
                until = now + lease_seconds
                db.execute(
                    """UPDATE retrieval_documents SET state='leased',lease_owner=?,lease_token=?,
                    lease_until=?,grant_fingerprint=?,attempts=attempts+1
                    WHERE generation_id=? AND evidence_id=?""",
                    (owner, token, until, grant, generation_id, row["evidence_id"]),
                )
                return IndexLease(
                    generation_id,
                    row["evidence_id"],
                    row["build_id"],
                    row["event_seq"],
                    owner,
                    token,
                    until,
                    grant,
                )
        return None

    def _validate_lease(
        self, db: sqlite3.Connection, lease: IndexLease, now: float
    ) -> journal.IngestEvent:
        if not math.isfinite(now):
            raise ValueError("invalid_lease_time")
        generation = db.execute(
            "SELECT state FROM retrieval_index_generations WHERE generation_id=?",
            (lease.generation_id,),
        ).fetchone()
        if generation is None or generation[0] == "retired":
            raise ValueError("lease_generation_retired")
        row = db.execute(
            "SELECT * FROM retrieval_documents WHERE generation_id=? AND evidence_id=?",
            (lease.generation_id, lease.evidence_id),
        ).fetchone()
        if (
            row is None
            or row["state"] != "leased"
            or (
                row["build_id"],
                row["event_seq"],
                row["lease_owner"],
                row["lease_token"],
                row["lease_until"],
                row["grant_fingerprint"],
            )
            != (
                lease.build_id,
                lease.event_seq,
                lease.owner,
                lease.token,
                lease.expires_at,
                lease.grant_fingerprint,
            )
            or lease.expires_at <= now
        ):
            raise ValueError("lease_changed_or_expired")
        event = journal.event(db, lease.event_seq)
        if (
            event is None
            or event.user_id != "local"
            or event.evidence_id != lease.evidence_id
            or not journal.matches_current(db, event)
        ):
            raise ValueError("lease_evidence_changed")
        if self._grant(db, event.source_id) != lease.grant_fingerprint:
            raise ValueError("lease_source_authority_changed")
        return event

    def read_lease(self, lease: IndexLease, *, now: float | None = None) -> EvidenceRecord:
        with self._db() as db:
            self._validate_lease(db, lease, time.time() if now is None else now)
            record = EvidenceStore._get_with_connection(db, lease.evidence_id)
            if record is None or len(record.verbatim) > 2_000_000:
                raise ValueError("lease_input_unavailable_or_too_large")
            return record

    def renew(
        self, lease: IndexLease, *, now: float | None = None, lease_seconds: int = 60
    ) -> IndexLease:
        now = time.time() if now is None else now
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 300:
            raise ValueError("invalid_lease")
        with self._db(write=True) as db:
            self._validate_lease(db, lease, now)
            expires = max(lease.expires_at, now + lease_seconds)
            db.execute(
                "UPDATE retrieval_documents SET lease_until=? "
                "WHERE generation_id=? AND evidence_id=?",
                (expires, lease.generation_id, lease.evidence_id),
            )
            return replace(lease, expires_at=expires)

    def block(self, lease: IndexLease) -> None:
        """Release only this claim; preserve uncertain derived vectors for later cleanup."""
        with self._db(write=True) as db:
            db.execute(
                """UPDATE retrieval_documents SET state='blocked',active_build_id=NULL,
                lease_owner=NULL,lease_token=NULL,lease_until=NULL
                WHERE generation_id=? AND evidence_id=? AND state='leased'
                AND build_id=? AND lease_token=? AND lease_owner=?""",
                (lease.generation_id, lease.evidence_id, lease.build_id, lease.token, lease.owner),
            )

    def retry_blocked(self, generation_id: str) -> int:
        """Bounded, durable round-robin retry/regrant pass; never creates grants."""
        changed = 0
        with self._db(write=True) as db:
            generation = db.execute(
                "SELECT g.state,c.retry_after_seq FROM retrieval_index_generations g "
                "JOIN retrieval_consumers c USING(generation_id) WHERE generation_id=?",
                (generation_id,),
            ).fetchone()
            if generation is None or generation[0] == "retired":
                raise ValueError("generation_not_writable")
            rows = db.execute(
                "SELECT * FROM retrieval_documents WHERE generation_id=? "
                "AND state IN ('blocked','ready','excluded') AND event_seq>? "
                "ORDER BY event_seq LIMIT 256",
                (generation_id, generation[1]),
            ).fetchall()
            for row in rows:
                event = journal.event(db, row["event_seq"])
                grant = self._grant(db, row["source_id"])
                if row["state"] in ("ready", "excluded") and grant == row["grant_fingerprint"]:
                    continue
                if (
                    event
                    and event.source_id == row["source_id"]
                    and grant
                    and journal.matches_current(db, event)
                ):
                    db.execute(
                        "UPDATE retrieval_documents SET state='pending',active_build_id=NULL,"
                        "lease_owner=NULL,lease_token=NULL,lease_until=NULL,grant_fingerprint=NULL "
                        "WHERE generation_id=? AND evidence_id=?",
                        (generation_id, row["evidence_id"]),
                    )
                    changed += 1
            db.execute(
                "UPDATE retrieval_consumers SET retry_after_seq=? WHERE generation_id=?",
                (rows[-1]["event_seq"] if len(rows) == 256 else 0, generation_id),
            )
        return changed

    def publish(
        self,
        lease: IndexLease,
        chunks: Sequence[TextChunk],
        *,
        vectors_verified: bool,
        now: float | None = None,
        source_map: ContentMap | None = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> tuple[str, ...]:
        """Caller verifies actual immutable vectors before entering this short transaction."""
        if vectors_verified is not True:
            raise ValueError("vectors_not_verified")
        now = time.time() if now is None else now
        if not math.isfinite(now):
            raise ValueError("invalid_lease_time")
        if len(chunks) > 8192:
            raise ValueError("invalid_chunk_manifest")
        with self._db(write=True) as db:
            if checkpoint is not None:
                checkpoint()
            event = self._validate_lease(db, lease, now)
            record = EvidenceStore._get_with_connection(db, lease.evidence_id)
            if record is None or len(record.verbatim) > 2_000_000:
                raise ValueError("lease_evidence_missing")
            prepared = self._prepare(db, lease.generation_id, record)
            if source_map != (prepared.metadata if prepared is not None else None):
                raise ValueError("source_map_mismatch")
            validate_chunk_coverage(record, chunks, prepared)
            map_digest = source_map.digest if source_map is not None else None
            keys = []
            manifest = []
            for index, chunk in enumerate(chunks):
                text_hash = digest(chunk.text)
                key = chunk_identity(lease, chunk, map_digest)
                keys.append(key)
                manifest.append(
                    (
                        key,
                        lease.generation_id,
                        lease.evidence_id,
                        lease.build_id,
                        index,
                        chunk.start_cp,
                        chunk.end_cp,
                        chunk.token_count,
                        text_hash,
                    )
                )
            existing = db.execute(
                "SELECT * FROM retrieval_chunks WHERE build_id=? ORDER BY ordinal",
                (lease.build_id,),
            ).fetchall()
            if existing:
                if [tuple(row) for row in existing] != manifest:
                    raise ValueError("immutable_chunk_manifest_conflict")
            else:
                db.executemany("INSERT INTO retrieval_chunks VALUES (?,?,?,?,?,?,?,?,?)", manifest)
            state = "ready" if chunks else "excluded"
            if source_map is not None:
                values = (
                    lease.build_id,
                    source_map.canonical_json(),
                    map_digest,
                    "indexable" if chunks else "excluded",
                )
                prior = db.execute(
                    "SELECT * FROM retrieval_build_maps WHERE build_id=?", (lease.build_id,)
                ).fetchone()
                if prior is not None and tuple(prior) != values:
                    raise ValueError("immutable_source_map_conflict")
                if prior is None:
                    db.execute("INSERT INTO retrieval_build_maps VALUES (?,?,?,?)", values)
            if not journal.matches_current(db, event):
                raise ValueError("lease_evidence_changed")
            db.execute(
                "UPDATE retrieval_documents SET state=?,active_build_id=build_id,"
                "lease_owner=NULL,lease_token=NULL,lease_until=NULL "
                "WHERE generation_id=? AND evidence_id=?",
                (state, lease.generation_id, lease.evidence_id),
            )
            if checkpoint is not None:
                checkpoint()
            return tuple(keys)

    def activate_generation(self, generation_id: str) -> None:
        with self._db(write=True) as db:
            row = db.execute(
                "SELECT state FROM retrieval_index_generations WHERE generation_id=?",
                (generation_id,),
            ).fetchone()
            cursor = db.execute(
                "SELECT after_seq FROM retrieval_consumers WHERE generation_id=?", (generation_id,)
            ).fetchone()
            if (
                row is None
                or row[0] == "retired"
                or cursor is None
                or cursor[0] != journal.watermark(db)
            ):
                raise ValueError("generation_not_caught_up")
            for document in db.execute(
                "SELECT * FROM retrieval_documents WHERE generation_id=? "
                "AND state NOT IN ('ready','excluded','deleted')",
                (generation_id,),
            ):
                if self._grant(db, document["source_id"]) is not None:
                    raise ValueError("generation_incomplete")
            for document in db.execute(
                "SELECT * FROM retrieval_documents WHERE generation_id=? "
                "AND state IN ('ready','excluded')",
                (generation_id,),
            ):
                if self._grant(db, document["source_id"]) is not None:
                    event = journal.event(db, document["event_seq"])
                    if (
                        not event
                        or not journal.matches_current(db, event)
                        or self._grant(db, document["source_id"]) != document["grant_fingerprint"]
                    ):
                        raise ValueError("generation_stale")
                    record = EvidenceStore._get_with_connection(db, document["evidence_id"])
                    if record is None:
                        raise ValueError("generation_stale")
                    self.validate_document(db, document, record)
            db.execute(
                "UPDATE retrieval_index_generations SET state='retired' "
                "WHERE state='active' AND generation_id!=?",
                (generation_id,),
            )
            db.execute(
                "UPDATE retrieval_index_generations SET state='active' WHERE generation_id=?",
                (generation_id,),
            )

    def active_chunks(
        self,
        generation_id: str,
        *,
        source_ids: frozenset[str] | None = None,
        time_range: TimeRange | None = None,
        deadline: float | None = None,
        require_active: bool = False,
    ) -> tuple[PublishedChunk, ...]:
        """Return current chunks after SQL-level source/time eligibility filtering.

        Grant fingerprints, journal freshness, and manifests are still checked
        below in the same snapshot. The SQL predicate keeps unauthorized rows
        from filling an in-memory candidate set before those checks run.
        """
        if source_ids is not None and not source_ids:
            return ()
        with self._db(deadline=deadline) as db:
            generation = db.execute(
                "SELECT state FROM retrieval_index_generations WHERE generation_id=?",
                (generation_id,),
            ).fetchone()
            if generation is None or generation[0] != "active":
                if require_active:
                    raise ValueError("active_generation_changed")
                return ()
            clauses = ["d.generation_id=?", "d.state IN ('ready','excluded')"]
            parameters: list[object] = [generation_id]
            join = ""
            if source_ids is not None:
                clauses.append("d.source_id IN (SELECT value FROM json_each(?))")
                parameters.append(json.dumps(sorted(source_ids)))
            if time_range is not None:
                join = "JOIN evidence e ON e.evidence_id=d.evidence_id "
                clauses.extend(
                    (
                        "e.created_at IS NOT NULL",
                        "julianday(e.created_at) >= julianday(?)",
                        "julianday(e.created_at) < julianday(?)",
                    )
                )
                parameters.extend((time_range.start.isoformat(), time_range.end.isoformat()))
            output = []
            for row in db.execute(
                "SELECT d.* FROM retrieval_documents d "
                + join
                + f"WHERE {' AND '.join(clauses)} ORDER BY d.event_seq,d.evidence_id",
                parameters,
            ):
                if deadline is not None:
                    _check(deadline)
                grant = self._grant(db, row["source_id"])
                if grant is None or grant != row["grant_fingerprint"]:
                    continue
                event = journal.event(db, row["event_seq"])
                if (
                    event is None
                    or event.source_id != row["source_id"]
                    or not journal.matches_current(db, event)
                ):
                    continue
                record = EvidenceStore._get_with_connection(db, row["evidence_id"])
                if (
                    record is None
                    or record.user_id != "local"
                    or record.source_id != row["source_id"]
                ):
                    continue
                event_time = record.created_at
                if event_time is not None:
                    event_time = event_time.astimezone(UTC) if event_time.tzinfo else None
                if time_range is not None and (
                    event_time is None or not time_range.start <= event_time < time_range.end
                ):
                    continue
                chunks = self.validate_document(db, row, record, deadline=deadline)
                for chunk in chunks:
                    if deadline is not None:
                        _check(deadline)
                    output.append(
                        PublishedChunk(
                            chunk["chunk_id"],
                            row["build_id"],
                            row["evidence_id"],
                            event.evidence_revision,
                            chunk["start_cp"],
                            chunk["end_cp"],
                            chunk["ordinal"],
                            record.source_id,
                            event_time,
                        )
                    )
            return tuple(output)

    def validate_document(
        self,
        db: sqlite3.Connection,
        document: sqlite3.Row,
        record: EvidenceRecord,
        *,
        deadline: float | None = None,
    ) -> tuple[sqlite3.Row, ...]:
        """Same-snapshot complete manifest/map check shared by candidate and final read."""
        if deadline is not None:
            _check(deadline)
        if document["active_build_id"] != document["build_id"]:
            raise ValueError("published_build_binding_invalid")
        prepared = self._prepare(db, document["generation_id"], record)
        map_digest = None
        if prepared is not None:
            source_map = db.execute(
                "SELECT source_map_json,map_digest,coverage_state FROM retrieval_build_maps "
                "WHERE build_id=?",
                (document["build_id"],),
            ).fetchone()
            expected_state = "excluded" if prepared.state == "no_indexable_content" else "ready"
            if (
                source_map is None
                or tuple(source_map)
                != (
                    prepared.metadata.canonical_json(),
                    prepared.metadata.digest,
                    "excluded" if expected_state == "excluded" else "indexable",
                )
                or document["state"] != expected_state
            ):
                raise ValueError("published_source_map_invalid")
            map_digest = prepared.metadata.digest
        elif document["state"] != "ready":
            raise ValueError("published_manifest_invalid")
        rows = tuple(
            db.execute(
                "SELECT * FROM retrieval_chunks WHERE generation_id=? AND evidence_id=? "
                "AND build_id=? ORDER BY ordinal LIMIT 8193",
                (document["generation_id"], record.evidence_id, document["build_id"]),
            ).fetchall()
        )
        chunks = []
        for row in rows:
            if deadline is not None:
                _check(deadline)
            start, end = row["start_cp"], row["end_cp"]
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(record.verbatim)
            ):
                raise ValueError("published_manifest_invalid")
            text = record.verbatim[start:end]
            text_hash = digest(text)
            identity = [document["build_id"], row["ordinal"], start, end, text_hash]
            if map_digest is not None:
                identity.append(map_digest)
            if row["text_hash"] != text_hash or row["chunk_id"] != digest(identity):
                raise ValueError("published_manifest_invalid")
            chunks.append(TextChunk(row["ordinal"], start, end, row["token_count"], text))
        try:
            validate_chunk_coverage(record, chunks, prepared)
        except ValueError as error:
            raise ValueError("published_manifest_incomplete_or_invalid") from error
        if deadline is not None:
            _check(deadline)
        return rows

    def status(self, generation_id: str) -> dict[str, int]:
        with self._db() as db:
            row = db.execute(
                "SELECT after_seq FROM retrieval_consumers WHERE generation_id=?", (generation_id,)
            ).fetchone()
            if row is None:
                raise ValueError("generation_missing")
            result = {
                "after_seq": int(row[0]),
                "pending": 0,
                "leased": 0,
                "ready": 0,
                "blocked": 0,
                "deleted": 0,
                "excluded": 0,
            }
            for state, count in db.execute(
                "SELECT state,count(*) FROM retrieval_documents "
                "WHERE generation_id=? GROUP BY state",
                (generation_id,),
            ):
                result[state] = count
            return result
