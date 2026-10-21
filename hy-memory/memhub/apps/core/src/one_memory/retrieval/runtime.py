"""Resume an explicitly configured local index; never create or migrate one."""

import asyncio
import json
import os
import shutil
import sqlite3
import stat
import sys
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from one_memory.database_access import main_database
from one_memory.retrieval.index_store import EncoderIdentity, RetrievalIndexStore
from one_memory.retrieval.index_supervisor import IndexSupervisorSnapshot, RetrievalIndexSupervisor
from one_memory.retrieval.index_worker import LocalRetrievalEncoder, RetrievalIndexWorker
from one_memory.retrieval.models import TimeRange
from one_memory.retrieval.raw_candidates import RawCandidateBatch, read_raw_semantic_candidates
from one_memory.retrieval.vector_store import RawVectorStore, VectorStoreError
from one_memory.service_levels import ServiceLevel, ServiceLevelScheduler, ServiceResource

type RuntimeState = Literal[
    "new", "starting", "running", "not_initialized", "failed", "stopping", "stopped"
]


@dataclass(frozen=True)
class ExistingRetrievalSnapshot:
    state: RuntimeState
    error_code: str | None
    generation_id: str | None
    supervisor: IndexSupervisorSnapshot | None


class _AdmissionError(Exception):
    def __init__(self, code: str, *, missing: bool = False):
        self.code, self.missing = code, missing


async def _native[T](operation: Callable[[], T]) -> T:
    """Owned, joined native call. Only retained internal lifecycle tasks invoke this."""
    result: list[T] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            result.append(operation())
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run, name="retrieval-resource", daemon=False)
    thread.start()
    while thread.is_alive():
        await asyncio.sleep(0.01)
    thread.join()
    if errors:
        raise errors[0]
    return result[0]


class ExistingRetrievalRuntime:
    """Caller guarantees managed Core single ownership and explicit configuration.

    Construct without I/O; start and stop on the owning event loop. A retained
    lifecycle task shields native work from caller cancellation until cleanup.
    """

    def __init__(
        self,
        data_dir: Path,
        *,
        minimum_free_bytes: int = 256 * 1024 * 1024,
        service_levels: ServiceLevelScheduler | None = None,
    ):
        if type(minimum_free_bytes) is not int or minimum_free_bytes < 0:
            raise ValueError("retrieval_runtime_invalid_disk_limit")
        self._directory = Path(data_dir)
        self._minimum_free = minimum_free_bytes
        self._service_levels = service_levels or ServiceLevelScheduler()
        self._state: ExistingRetrievalSnapshot = ExistingRetrievalSnapshot("new", None, None, None)
        self._vectors: RawVectorStore | None = None
        self._store: RetrievalIndexStore | None = None
        self._encoder: LocalRetrievalEncoder | None = None
        self._supervisor: RetrievalIndexSupervisor | None = None
        self._last_supervisor_snapshot: IndexSupervisorSnapshot | None = None
        self._start_task: asyncio.Task[bool] | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self._stop_requested = False

    def snapshot(self) -> ExistingRetrievalSnapshot:
        return ExistingRetrievalSnapshot(
            self._state.state,
            self._state.error_code,
            self._state.generation_id,
            self._supervisor.snapshot()
            if self._supervisor is not None
            else self._last_supervisor_snapshot,
        )

    def _set(
        self, state: RuntimeState, code: str | None = None, generation: str | None = None
    ) -> None:
        self._state = ExistingRetrievalSnapshot(
            state,
            code,
            generation if generation is not None else self._state.generation_id,
            None,
        )

    def trigger(self) -> bool:
        return bool(
            self._state.state == "running" and self._supervisor and self._supervisor.trigger()
        )

    def lookup_raw(
        self,
        query: str,
        *,
        source_ids: frozenset[str] | None,
        deadline: float,
        time_range: TimeRange | None = None,
    ) -> tuple[RawCandidateBatch, bool]:
        """Read-only candidate lookup. Does not release original bodies."""
        store, encoder, vectors, generation = (
            self._store,
            self._encoder,
            self._vectors,
            self._state.generation_id,
        )
        if (
            self._state.state != "running"
            or store is None
            or encoder is None
            or vectors is None
            or generation is None
        ):
            return RawCandidateBatch(reason="index_unavailable"), True
        counts = store.status(generation)
        unpublished = counts["pending"] + counts["leased"] + counts["blocked"] > 0
        resolved = source_ids
        if resolved is None:
            resolved = frozenset(
                chunk.source_id for chunk in store.active_chunks(generation, deadline=deadline)
            )
        if not resolved:
            return (
                RawCandidateBatch(complete=not unpublished, reason="no_eligible_chunks"),
                unpublished,
            )
        try:
            vector = encoder.encode_documents([query.strip()])[0]
        except Exception:
            return RawCandidateBatch(reason="index_unavailable"), True
        batch = read_raw_semantic_candidates(
            store,
            vectors,
            vector,
            generation_id=generation,
            source_ids=resolved,
            deadline=deadline,
            time_range=time_range,
        )
        return batch, unpublished

    async def start(self) -> bool:
        if self._state.state != "new" or self._stop_requested:
            raise RuntimeError("retrieval_runtime_already_started")
        self._set("starting")
        self._start_task = asyncio.create_task(self._start())
        try:
            return await asyncio.shield(self._start_task)
        except asyncio.CancelledError:
            # Retain and drain opening resources, then release them, before cancellation escapes.
            await self.stop()
            raise

    async def stop(self) -> None:
        self._stop_requested = True
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(self._stop())
        cancelled = False
        while not self._stop_task.done():
            try:
                await asyncio.shield(self._stop_task)
            except asyncio.CancelledError:
                cancelled = True
        self._stop_task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _start(self) -> bool:
        try:
            store, encoder, vectors, generation = await _native(self._open)
            self._store = store
            self._encoder = encoder
            self._vectors = vectors
            self._set("starting", generation=generation)
            if self._stop_requested:
                return False
            worker = RetrievalIndexWorker(
                store, vectors, encoder, generation_id=generation, owner="managed-core-retrieval"
            )
            self._supervisor = RetrievalIndexSupervisor(
                worker,
                background_should_yield=lambda: self._service_levels.should_yield(
                    ServiceResource.INDEX,
                    ServiceLevel.BACKGROUND,
                ),
            )
            self._supervisor.start()
            self._set("running")
            return True
        except _AdmissionError as error:
            self._set("not_initialized" if error.missing else "failed", error.code)
        except Exception:
            self._set("failed", "retrieval_runtime_start_failed")
        await self._release()
        return False

    async def _release(self) -> None:
        stop_failed = False
        if self._supervisor is not None:
            try:
                await self._supervisor.stop()
            except Exception:
                stop_failed = True
            supervisor_snapshot = self._supervisor.snapshot()
            if supervisor_snapshot.thread_alive:
                self._set("failed", "retrieval_runtime_stop_failed")
                raise RuntimeError("retrieval_runtime_stop_failed") from None
            # The supervisor owns the worker, which owns the native vector
            # client. Retain only the immutable receipt once its thread drains.
            self._last_supervisor_snapshot = supervisor_snapshot
            self._supervisor = None
        if self._vectors is not None:
            try:
                await _native(self._vectors.close)
            except Exception:
                self._set("failed", "retrieval_runtime_close_failed")
                raise RuntimeError("retrieval_runtime_close_failed") from None
            self._vectors = None
        self._store = None
        self._encoder = None
        if stop_failed:
            self._set("failed", "retrieval_runtime_stop_failed")
            raise RuntimeError("retrieval_runtime_stop_failed") from None

    async def _stop(self) -> None:
        if self._start_task is not None:
            try:
                await asyncio.shield(self._start_task)
            except Exception:
                # Startup can itself fail during cleanup. Do not lose resource ownership.
                self._set("failed", "retrieval_runtime_start_failed")
        self._set("stopping", self._state.error_code)
        await self._release()
        if self._state.error_code == "retrieval_runtime_close_failed":
            return
        self._set("stopped", self._state.error_code)

    @staticmethod
    def _path(path: Path, *, directory: bool) -> tuple[int, int]:
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise _AdmissionError("retrieval_runtime_unsafe_path")
        try:
            info = path.stat()
        except FileNotFoundError:
            raise _AdmissionError("retrieval_runtime_not_initialized", missing=True) from None
        if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            raise _AdmissionError("retrieval_runtime_unsafe_path")
        if not directory and info.st_nlink != 1:
            raise _AdmissionError("retrieval_runtime_unsafe_path")
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
            raise _AdmissionError("retrieval_runtime_unsafe_path")
        return info.st_dev, info.st_ino

    def _sidecars(self, database: Path) -> None:
        for suffix in ("-wal", "-shm", "-journal"):
            path = database.with_name(database.name + suffix)
            if path.is_symlink() or path.exists():
                self._path(path, directory=False)

    def _inspect(self, database: Path) -> tuple[RetrievalIndexStore, EncoderIdentity, str]:
        with main_database(database.absolute()).read(busy_timeout_ms=1_000) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='retrieval_index_state'"
            ).fetchone():
                raise _AdmissionError("retrieval_runtime_not_initialized", missing=True)
            state = db.execute(
                "SELECT schema_version FROM retrieval_index_state WHERE singleton=1"
            ).fetchone()
            if state is not None and state[0] == 1:
                raise _AdmissionError("retrieval_runtime_not_initialized", missing=True)
            if state is None or state[0] != 2:
                raise _AdmissionError("retrieval_runtime_invalid_index")
            rows = db.execute(
                "SELECT generation_id,identity_json FROM retrieval_index_generations "
                "WHERE state='active' LIMIT 2"
            ).fetchall()
            if not rows:
                raise _AdmissionError("retrieval_runtime_not_initialized", missing=True)
            if len(rows) != 1:
                raise _AdmissionError("retrieval_runtime_invalid_index")
            store = RetrievalIndexStore(database)
            generation = rows[0]["generation_id"]
            identity = store._identity(db, generation)
            raw = json.loads(rows[0]["identity_json"])
            if raw != asdict(identity) or set(raw) != set(asdict(identity)):
                raise _AdmissionError("retrieval_runtime_invalid_index")
            # Check required schema shape without repairing it or reading original bodies.
            db.execute(
                "SELECT build_id,source_map_json,map_digest,coverage_state "
                "FROM retrieval_build_maps LIMIT 0"
            )
            db.execute("SELECT after_seq,retry_after_seq FROM retrieval_consumers LIMIT 0")
            db.execute("SELECT lease_token,active_build_id FROM retrieval_documents LIMIT 0")
            db.execute("SELECT chunk_id,text_hash FROM retrieval_chunks LIMIT 0")
            return store, identity, generation

    def _open(self) -> tuple[RetrievalIndexStore, LocalRetrievalEncoder, RawVectorStore, str]:
        if sys.platform == "win32" or not hasattr(os, "getuid"):
            raise _AdmissionError("retrieval_runtime_platform_unsupported")
        directory = self._directory.absolute()
        database, vector_dir = directory / "one-memory.sqlite3", directory / "retrieval-vectors"
        root_pin = self._path(directory, directory=True)
        database_pin = self._path(database, directory=False)
        self._sidecars(database)
        try:
            store, identity, generation = self._inspect(database)
        except (ValueError, TypeError, sqlite3.Error):
            raise _AdmissionError("retrieval_runtime_invalid_index") from None
        vector_pin = self._path(vector_dir, directory=True)
        vector_database = vector_dir / "chroma.sqlite3"
        vector_db_pin = self._path(vector_database, directory=False)
        self._sidecars(vector_database)

        def recheck() -> None:
            if (
                self._path(directory, directory=True) != root_pin
                or self._path(database, directory=False) != database_pin
                or self._path(vector_dir, directory=True) != vector_pin
                or self._path(vector_database, directory=False) != vector_db_pin
            ):
                raise _AdmissionError("retrieval_runtime_index_changed")
            self._sidecars(database)
            self._sidecars(vector_database)

        if shutil.disk_usage(directory).free < self._minimum_free:
            raise _AdmissionError("retrieval_runtime_low_disk")
        encoder = LocalRetrievalEncoder(content_version=identity.normalizer_version)
        if encoder.identity != identity:
            raise _AdmissionError("retrieval_runtime_encoder_mismatch")
        recheck()
        try:
            vectors = RawVectorStore.open_writer_existing(
                vector_dir, generation_id=generation, dimensions=identity.dimensions
            )
            # Retain ownership immediately so all later failures use the same cleanup path.
            self._vectors = vectors
            # A generation change during the native open is not authorization to resume another.
            recheck()
            if self._inspect(database)[1:] != (identity, generation):
                raise _AdmissionError("retrieval_runtime_index_changed")
            recheck()
            return store, encoder, vectors, generation
        except BaseException as error:
            if isinstance(error, VectorStoreError):
                if str(error) in {"vector_store_not_found", "vector_collection_not_found"}:
                    raise _AdmissionError(
                        "retrieval_runtime_not_initialized", missing=True
                    ) from None
                raise _AdmissionError("retrieval_runtime_vector_unavailable") from None
            raise
