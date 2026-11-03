"""Per-job file transport into the existing source readers, never memory extraction.

The supervisor supplies the current authorized root when execution starts and
invokes ``create_snapshot_adapter`` once per execution.
Capture/reopen happens only inside scan(), after ImportRunner claims the job.
The caller owns a pre-existing private (0700) snapshot directory outside every
source root, and serializes jobs/readers for each source. Sync and sources outside
the bounded supported set retain their ordinary adapters.

Only job/snapshot identity and failures are persisted here, in the existing jobs
database. The normal reader emits the same EvidenceInput and cursor keys as live
import; ImportRunner alone writes Evidence and schedules the existing HY path.
Failed or interrupted capture needs a new confirmed job, not a new automatic ID.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from threading import Event
from typing import TypedDict

from one_memory.background_work import in_snapshot_background
from one_memory.imports.access import (
    AuthorizedSourceFile,
    AuthorizedSourceRoot,
    SourceAccessError,
)
from one_memory.imports.adapters import (
    ScanEvent,
    ScanOptions,
    ScanProgressEvent,
    SourceAdapter,
    SourceCursor,
    SourceDescriptor,
)
from one_memory.imports.jobs import ImportJob, ImportJobStore
from one_memory.imports.snapshots import (
    SnapshotError,
    SnapshotErrorCode,
    SnapshotFile,
    SnapshotLimits,
    SnapshotMode,
    SourceSnapshot,
    SourceSnapshotStore,
)
from one_memory.imports.sources.common import JsonlSourceAdapter
from one_memory.imports.sources.cursor_unified import (
    CursorUnifiedSourceAdapter,
    _is_cursor_data_file,
)
from one_memory.imports.sources.exported import EXPORT_DESCRIPTORS
from one_memory.imports.sources.registry import SourceRegistration
from one_memory.memory_server.migrations import import_job_snapshots_ddl

SNAPSHOT_SOURCE_IDS = frozenset({"workbuddy", "claude-code", "codex", "cursor"}) | frozenset(
    descriptor.source_id for descriptor in EXPORT_DESCRIPTORS
)

_SCHEMA = import_job_snapshots_ddl("sqlite")


@dataclass(frozen=True)
class _Selection:
    identity: str
    suffix_modes: dict[str, SnapshotMode]
    predicate: Callable[[AuthorizedSourceFile], bool]
    path_predicate: Callable[[Path], bool] | None = None


class _SnapshotRequest(TypedDict):
    snapshot_id: str
    source_id: str
    grant: AuthorizedSourceRoot
    selection_id: str
    suffix_modes: dict[str, SnapshotMode]
    cancelled: Callable[[], bool]


def create_snapshot_adapter(
    *,
    registration: SourceRegistration,
    grant: AuthorizedSourceRoot,
    job: ImportJob,
    job_store: ImportJobStore,
    snapshot_directory: Path,
    limits: SnapshotLimits | None = None,
    live_adapter: SourceAdapter | None = None,
) -> SourceAdapter:
    """Bind supported history jobs to an immutable capture, without doing I/O.

    The current source grant supplies the root and its live access check. A
    cached old adapter must never supply the grant.
    Limits come from snapshots.py; scan options cannot narrow the capture.
    Unsupported sources and sync jobs are unchanged, not given new selectors.
    Pass live_adapter to retain the supervisor's exact adapter on those paths.
    """
    if not (registration.descriptor.source_id == grant.source_id == job.source_id):
        raise ValueError("Snapshot job, registration and grant source IDs must match")
    if job.operation == "sync" or job.source_id not in SNAPSHOT_SOURCE_IDS:
        return live_adapter if live_adapter is not None else registration.create_adapter(grant)
    return SnapshotSourceAdapter(
        registration=registration,
        grant=grant,
        job=job,
        job_store=job_store,
        snapshot_directory=snapshot_directory,
        live_adapter=live_adapter,
        limits=limits,
    )


class SnapshotSourceAdapter:
    def __init__(
        self,
        *,
        registration: SourceRegistration,
        grant: AuthorizedSourceRoot,
        job: ImportJob,
        job_store: ImportJobStore,
        snapshot_directory: Path,
        live_adapter: SourceAdapter | None = None,
        limits: SnapshotLimits | None = None,
    ) -> None:
        self._registration = registration
        self._grant = grant
        self._job = job
        self._jobs = job_store
        self._directory = snapshot_directory
        self._live = live_adapter
        self._limits = limits

    @property
    def descriptor(self) -> SourceDescriptor:
        return self._registration.descriptor

    async def detect(self) -> bool:
        # The normal metadata-only detector is not permission to capture history.
        adapter = self._live or self._registration.create_adapter(self._grant)
        return await adapter.detect()

    async def scan(self, options: ScanOptions) -> AsyncIterator[ScanEvent]:
        cancelled = Event()
        try:
            snapshot = await _cooperative_work(
                partial(self._capture_or_reopen, cancelled), cancelled
            )
            translations = await _cooperative_work(partial(_cursor_files, snapshot), cancelled)
            incoming = _snapshot_cursors(options, translations).model_copy(
                update={"immutable": True}
            )
            reader = self._registration.create_adapter(snapshot.grant)
            stream = reader.scan(incoming)
            try:
                while True:
                    try:
                        event = await _await_worker(asyncio.ensure_future(anext(stream)), cancelled)
                    except StopAsyncIteration:
                        break
                    # Readers batch events. Recheck even for already-buffered
                    # events so revocation cannot expose the next batch member.
                    await _cooperative_work(partial(_check_snapshot, snapshot), cancelled)
                    yield _original_cursor(event, translations)
            finally:
                cancelled.set()
                close = getattr(stream, "aclose", None)
                if close is not None:
                    await _await_worker(asyncio.ensure_future(close()), cancelled)
        except (SnapshotError, SourceAccessError) as error:
            await _cooperative_work(partial(self._record_failure, str(error.code)), Event())
            raise
        except asyncio.CancelledError:
            await _cooperative_work(
                partial(self._record_failure, SnapshotErrorCode.CANCELLED), Event()
            )
            raise
        except OSError:
            await _cooperative_work(
                partial(self._record_failure, SnapshotErrorCode.IO_ERROR), Event()
            )
            raise SnapshotError(SnapshotErrorCode.IO_ERROR) from None
        finally:
            cancelled.set()

    def _capture_or_reopen(self, cancelled: Event) -> SourceSnapshot:
        adapter = self._live or self._registration.create_adapter(self._grant)
        selection = _selection(self._job.source_id, adapter)
        # Commit selection identity before file I/O so restart cannot widen it.
        with self._jobs._connect(writing=True) as connection:
            connection.execute(_SCHEMA)
            current = connection.execute(
                "SELECT user_id, source_id, operation FROM import_jobs WHERE job_id=?",
                (self._job.job_id,),
            ).fetchone()
            if current is None or (
                current["user_id"],
                current["source_id"],
                current["operation"],
            ) != (
                self._job.user_id,
                self._job.source_id,
                "history",
            ):
                raise SnapshotError(SnapshotErrorCode.CONFLICT)
            inserted = (
                connection.execute(
                    "INSERT OR IGNORE INTO import_job_snapshots (job_id, selection_id) "
                    "VALUES (?,?)",
                    (self._job.job_id, selection.identity),
                ).rowcount
                == 1
            )
            binding = connection.execute(
                "SELECT selection_id FROM import_job_snapshots WHERE job_id=?",
                (self._job.job_id,),
            ).fetchone()
            assert binding is not None
            if binding["selection_id"] != selection.identity:
                raise SnapshotError(SnapshotErrorCode.CONFLICT)
        store = SourceSnapshotStore(self._directory, limits=self._limits)
        request = _SnapshotRequest(
            snapshot_id=self._job.job_id,
            source_id=self._job.source_id,
            grant=self._grant,
            selection_id=selection.identity,
            suffix_modes=selection.suffix_modes,
            cancelled=cancelled.is_set,
        )
        if inserted:
            snapshot = store.capture(
                **request,
                file_predicate=selection.predicate,
                path_predicate=selection.path_predicate,
            )
        else:
            snapshot = store.reopen(**request)
        return snapshot

    def _record_failure(self, reason: str) -> None:
        # ScanIssueCode is the parser's vocabulary. Keep the precise snapshot /
        # access code without translating it to a successful empty scan, and let
        # the existing runner own FAILED/INTERRUPTED transitions.
        now = datetime.now(UTC).isoformat()
        with self._jobs._connect(writing=True) as connection:
            connection.execute(
                "INSERT INTO import_issues (job_id, kind, reason, created_at) "
                "VALUES (?, 'error', ?, ?)",
                (self._job.job_id, reason, now),
            )
            connection.execute(
                "UPDATE import_jobs SET errors=errors+1, updated_at=? WHERE job_id=?",
                (now, self._job.job_id),
            )


def _selection(source_id: str, adapter: SourceAdapter) -> _Selection:
    # Bump this version whenever the metadata-only selection semantics change.
    identity = f"{source_id}:adapter-files:v1"
    if adapter.descriptor.source_id != source_id:
        raise SnapshotError(SnapshotErrorCode.INVALID_REQUEST)
    if source_id == "cursor":
        if not isinstance(adapter, CursorUnifiedSourceAdapter):
            raise SnapshotError(SnapshotErrorCode.UNSUPPORTED_MODE)
        return _Selection(
            identity="cursor:history-roots:v3",
            suffix_modes={
                ".jsonl": SnapshotMode.BYTE_EXTENT,
                ".json": SnapshotMode.BYTE_EXTENT,
                ".db": SnapshotMode.SQLITE_BACKUP,
                ".vscdb": SnapshotMode.SQLITE_BACKUP,
            },
            predicate=_is_cursor_snapshot_file,
            path_predicate=lambda relative: (
                relative.parts[0]
                in {
                    "projects",
                    "agent-transcripts",
                    "chats",
                    "acp-sessions",
                    "globalStorage",
                    "workspaceStorage",
                    "User",
                }
                or relative.name == "state.vscdb"
            ),
        )
    if not isinstance(adapter, JsonlSourceAdapter):
        raise SnapshotError(SnapshotErrorCode.UNSUPPORTED_MODE)
    if not adapter.suffixes <= {".jsonl", ".zstd", ".zst"}:
        raise SnapshotError(SnapshotErrorCode.UNSUPPORTED_MODE)
    modes = dict.fromkeys(adapter.suffixes, SnapshotMode.BYTE_EXTENT)
    predicate = adapter.file_predicate
    if source_id == "workbuddy":
        # WorkBuddy's existing lazy workspace resolver reads only *.meta.json.
        # Test filenames here; opening metadata belongs to the ordinary parser.
        modes[".json"] = SnapshotMode.BYTE_EXTENT

        def with_metadata(source_file: AuthorizedSourceFile) -> bool:
            if source_file.relative_path.suffix.lower() == ".json":
                return source_file.relative_path.name.endswith(".meta.json")
            return predicate(source_file)

        return _Selection(identity, modes, with_metadata)
    return _Selection(identity, modes, predicate)


def _is_cursor_snapshot_file(source_file: AuthorizedSourceFile) -> bool:
    if _is_cursor_data_file(source_file):
        return True
    relative = source_file.relative_path
    if not relative.name.endswith(".meta.json"):
        return False
    transcript = relative.with_name(relative.name.removesuffix(".meta.json") + ".jsonl")
    return _is_cursor_data_file(replace(source_file, relative_path=transcript))


def _check_snapshot(snapshot: SourceSnapshot) -> None:
    if snapshot.grant.access_check is not None:
        snapshot.grant.access_check()


def _cursor_files(snapshot: SourceSnapshot) -> dict[str, tuple[SnapshotFile, AuthorizedSourceFile]]:
    result = {}
    for entry in snapshot.manifest.files:
        copied = snapshot.grant.authorize_file(Path(entry.relative_path))
        # History priority uses the frozen source mtime, not copy/reopen time.
        if copied.modified_ns != entry.source_modified_ns:
            raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)
        result[copied.safe_id] = (entry, copied)
    return result


def _snapshot_cursors(
    options: ScanOptions,
    files: dict[str, tuple[SnapshotFile, AuthorizedSourceFile]],
) -> ScanOptions:
    mapped: dict[str, SourceCursor] = {}
    for key, previous in options.cursors.items():
        pair = files.get(key)
        if pair is None:
            continue
        original, copied = pair
        # Never make a checkpoint from another incarnation valid by relabeling
        # it. Anchor/content validation still belongs to the unchanged reader.
        if (
            previous.file_key != key
            or previous.file_identity != original.source_file_identity
            or previous.observed_size > original.source_size
        ):
            continue
        mapped[key] = previous.model_copy(
            update={
                "file_identity": copied.file_identity,
                "observed_size": original.captured_size,
                "observed_modified_ns": copied.modified_ns,
            }
        )
    return options.model_copy(update={"cursors": mapped})


def _original_cursor(
    event: ScanEvent, files: dict[str, tuple[SnapshotFile, AuthorizedSourceFile]]
) -> ScanEvent:
    if isinstance(event, ScanProgressEvent) or event.cursor is None:
        return event
    pair = files.get(event.cursor.file_key)
    if pair is None or event.cursor.file_identity != pair[1].file_identity:
        raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)
    original = pair[0]
    cursor = event.cursor.model_copy(
        update={
            "file_identity": original.source_file_identity,
            "observed_size": original.source_size,
            "observed_modified_ns": original.source_modified_ns,
        }
    )
    return event.model_copy(update={"cursor": cursor})


async def _cooperative_work[T](work: Callable[[], T], cancelled: Event) -> T:
    return await _await_worker(asyncio.create_task(in_snapshot_background(work)), cancelled)


async def _await_worker[T](worker: asyncio.Future[T], cancelled: Event) -> T:
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled.set()
        await _finish_cleanup(worker)
        raise


async def _finish_cleanup[T](worker: asyncio.Future[T]) -> None:
    # A second cancel must not release the source lock before the thread exits.
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if not worker.cancelled():
        worker.exception()
