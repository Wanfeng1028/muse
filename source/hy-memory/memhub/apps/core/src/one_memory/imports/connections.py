"""Persist one confirmed connection intent and its jobs in the same transaction."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from one_memory.imports.access import (
    AuthorizedSourceRoot,
    SourceAccessError,
    root_identity_matches,
)
from one_memory.imports.candidates import SourceCandidateError, SourceCandidateStore
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJob, ImportJobStore
from one_memory.imports.sources.registry import RootCandidateKind, SourceRegistration

#: Schema owned by `memory_server.migrations` (migration 10). No local copy.
from one_memory.memory_server.migrations import connection_intents_ddl

SCHEMA = connection_intents_ddl("sqlite")


class ConnectionIntentError(RuntimeError):
    pass


class ConnectionIntentReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: str
    accepted_source_ids: tuple[str, ...]
    failed_sources: dict[str, str]
    jobs: tuple[ImportJob, ...]


class SourceConnectionStore:
    def __init__(
        self,
        grants: SourceGrantStore,
        jobs: ImportJobStore,
        *,
        home: Path,
        candidates: SourceCandidateStore | None = None,
    ) -> None:
        self.grants = grants
        self.jobs = jobs
        self.home = home
        self.candidates = candidates or SourceCandidateStore(grants.database_path, home=home)
        if not (
            self.candidates.database_path
            == grants.database_path.resolve()
            == jobs.database_path.resolve()
        ):
            raise ValueError("Source stores must share the same database")
        with self.grants._connect(writing=True) as db:
            db.execute(SCHEMA)

    def connect(
        self,
        *,
        request_id: str,
        registrations: tuple[SourceRegistration, ...],
        source_roots: dict[str, str],
        confirm_overrides: bool,
        full_rescan: bool,
        onboarding: bool = False,
        history_after: datetime | None = None,
        user_id: str = "local",
        import_binding: tuple[str, str] | None = None,
        source_candidate_revisions: dict[str, int] | None = None,
    ) -> ConnectionIntentReceipt:
        sources = tuple(item.descriptor.source_id for item in registrations)
        if not request_id or len(request_id) > 256 or set(source_roots) != set(sources):
            raise ConnectionIntentError("source_confirmation_required")
        if history_after is not None and (not onboarding or history_after.tzinfo is None):
            raise ConnectionIntentError("source_history_window_invalid")
        revisions = source_candidate_revisions or {}
        if not set(revisions) <= set(sources) or any(
            type(revision) is not int or revision < 0 for revision in revisions.values()
        ):
            raise ConnectionIntentError("source_candidate_revision_conflict")
        intent: dict[str, object] = {
            "sources": sources,
            "roots": source_roots,
            "overrides": confirm_overrides,
            "full_rescan": full_rescan,
            "onboarding": onboarding,
        }
        # Only the API's validated receipt adds a binding; legacy hashes stay unchanged.
        if import_binding is not None:
            intent["import_binding"] = import_binding
        if revisions:
            intent["source_candidate_revisions"] = revisions
        fingerprint = hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()
        accepted, failed, job_ids = [], {}, []
        now = datetime.now(UTC).isoformat()
        with self.grants._connect(writing=True) as db:
            prior = db.execute(
                "SELECT * FROM source_connection_intents WHERE user_id=? AND request_id=?",
                (user_id, request_id),
            ).fetchone()
            if prior is not None:
                if prior["request_hash"] != fingerprint:
                    raise ConnectionIntentError("source_intent_conflict")
                return self._receipt(prior, db)
            for registration in registrations:
                source_id = registration.descriptor.source_id
                db.execute("SAVEPOINT connection_source")
                try:
                    job_id = self._connect_source(
                        db,
                        registration,
                        user_id=user_id,
                        expected_root=source_roots[source_id],
                        confirm_overrides=confirm_overrides,
                        full_rescan=full_rescan,
                        history_after=history_after,
                        now=now,
                        expected_candidate_revision=revisions.get(source_id),
                    )
                except (SourceAccessError, ConnectionIntentError, SourceCandidateError) as error:
                    db.execute("ROLLBACK TO connection_source")
                    failed[source_id] = str(error)
                else:
                    accepted.append(source_id)
                    job_ids.append(job_id)
                finally:
                    db.execute("RELEASE connection_source")
            db.execute(
                "INSERT INTO source_connection_intents "
                "(user_id,request_id,request_hash,accepted_json,failed_json,job_ids_json,"
                "created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    user_id,
                    request_id,
                    fingerprint,
                    json.dumps(accepted),
                    json.dumps(failed),
                    json.dumps(job_ids),
                    now,
                ),
            )
            if onboarding and accepted:
                db.execute(
                    "INSERT INTO onboarding_state "
                    "(singleton,status,selected_source_ids_json,started_at,completed_at,"
                    "updated_at) "
                    "VALUES (1,'importing',?,?,NULL,?) "
                    "ON CONFLICT(singleton) DO UPDATE SET status='importing', "
                    "selected_source_ids_json=excluded.selected_source_ids_json, "
                    "started_at=excluded.started_at, updated_at=excluded.updated_at "
                    "WHERE onboarding_state.status!='completed'",
                    (json.dumps(accepted), now, now),
                )
            row = db.execute(
                "SELECT * FROM source_connection_intents WHERE user_id=? AND request_id=?",
                (user_id, request_id),
            ).fetchone()
            assert row is not None
            return self._receipt(row, db)

    def get(self, request_id: str, *, user_id: str = "local") -> ConnectionIntentReceipt | None:
        with self.grants._connect() as db:
            row = db.execute(
                "SELECT * FROM source_connection_intents WHERE user_id=? AND request_id=?",
                (user_id, request_id),
            ).fetchone()
            return self._receipt(row, db) if row else None

    def _connect_source(
        self,
        db: sqlite3.Connection,
        registration: SourceRegistration,
        *,
        user_id: str,
        expected_root: str,
        confirm_overrides: bool,
        full_rescan: bool,
        history_after: datetime | None,
        now: str,
        expected_candidate_revision: int | None = None,
    ) -> str:
        registration = self.candidates.resolve(registration, user_id=user_id, db=db)
        source_id = registration.descriptor.source_id
        if registration.candidate.kind is RootCandidateKind.USER_SELECTED:
            if expected_candidate_revision != registration.candidate.revision:
                raise ConnectionIntentError("source_candidate_revision_conflict")
            saved = db.execute(
                "SELECT root_id FROM source_candidates WHERE user_id=? AND source_id=?",
                (user_id, source_id),
            ).fetchone()
            if saved is None or saved["root_id"] != expected_root:
                raise ConnectionIntentError("source_identity_changed")
        elif expected_candidate_revision not in {None, 0}:
            raise ConnectionIntentError("source_candidate_revision_conflict")
        if (
            registration.candidate.kind
            in {RootCandidateKind.ENVIRONMENT_OVERRIDE, RootCandidateKind.USER_SELECTED}
            and not confirm_overrides
        ):
            raise ConnectionIntentError("environment_override_confirmation_required")
        root = AuthorizedSourceRoot.grant(
            source_id=source_id,
            root=registration.candidate.path,
            user_confirmed=True,
            home=self.home,
        )
        if not root_identity_matches(registration.candidate.path, expected_root):
            raise ConnectionIntentError("source_identity_changed")
        existing = db.execute(
            "SELECT job_id FROM import_jobs WHERE user_id=? AND source_id=? "
            "AND status IN ('pending','running','paused','interrupted','failed') LIMIT 1",
            (user_id, source_id),
        ).fetchone()
        prior = db.execute(
            "SELECT root_identity FROM source_grants WHERE user_id=? AND source_id=?",
            (user_id, source_id),
        ).fetchone()
        root_changed = prior is not None and prior["root_identity"] != expected_root
        running = db.execute(
            "SELECT 1 FROM import_jobs WHERE user_id=? AND source_id=? "
            "AND status='running' LIMIT 1",
            (user_id, source_id),
        ).fetchone()
        if existing and (not root_changed or running is not None):
            raise ConnectionIntentError("source_import_busy")
        if existing:
            db.execute(
                "UPDATE import_jobs SET status='cancelled', updated_at=? "
                "WHERE user_id=? AND source_id=? "
                "AND status IN ('pending','paused','interrupted','failed')",
                (now, user_id, source_id),
            )
        self.grants.write_grant(
            db,
            user_id=user_id,
            source_id=source_id,
            authorized=root,
            candidate_kind=registration.candidate.kind,
            now=now,
        )
        if full_rescan:
            db.execute(
                "DELETE FROM source_cursors WHERE user_id=? AND source_id=?", (user_id, source_id)
            )
        job_id = str(uuid4())
        db.execute(
            "INSERT INTO import_jobs (job_id,user_id,source_id,status,created_at,updated_at,"
            "operation,history_after) VALUES (?,?,?,'pending',?,?,'history',?)",
            (
                job_id,
                user_id,
                source_id,
                now,
                now,
                history_after.isoformat() if history_after is not None else None,
            ),
        )
        return job_id

    def _receipt(self, row: sqlite3.Row, db: sqlite3.Connection) -> ConnectionIntentReceipt:
        jobs = []
        for job_id in json.loads(row["job_ids_json"]):
            job = db.execute("SELECT * FROM import_jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None:
                raise ConnectionIntentError("source_intent_job_missing")
            jobs.append(self.jobs._to_job(job))
        return ConnectionIntentReceipt(
            request_id=row["request_id"],
            accepted_source_ids=tuple(json.loads(row["accepted_json"])),
            failed_sources=json.loads(row["failed_json"]),
            jobs=tuple(jobs),
        )
