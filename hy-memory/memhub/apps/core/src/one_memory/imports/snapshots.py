"""Approved-once adapter files, not a parser or an import/job engine.

Run capture/reopen in a worker thread. The caller owns the private job directory,
stable snapshot ID, current grant/token, and a versioned, metadata-only selector.
Only a committed manifest is replayable. Byte extents are enumerated before any
copy; each SQLite backup pins its own read transaction (not a cross-file instant).
Closed WAL databases with neither sidecar use a guarded, exact-extent private
copy, with matching full source hashes before/after copying and after backup.
Only that verified copy is opened immutable. This is a stable-observation
boundary, not an atomic cross-file snapshot or proof that no writer exists:
changes between observations that leave no metadata/hash trace cannot be ruled
out. Observed changes/sidecars fail the attempt and require fresh confirmation.
No source grant is created or upgraded here. The replay grant retains the original
grant's execution check, source ID and relative paths; original inode metadata is
in the manifest, while replay cursors correctly use the independent copy's inode.

max_disk_bytes counts payload, private SQLite staging, manifest and the attempt marker, not
filesystem allocation overhead; min_free_bytes reserves additional free space.
A killed process may leave an identifiable *.pending directory, never a published
partial snapshot. Its job
owner must reclaim that directory only after proving the capturing worker stopped.
An uncommitted attempt retains only a small intent marker after cooperative
cleanup. Retrying that ID is refused: no persisted SQLite transaction can be
resumed after cancellation, and rediscovery would silently expand the consent.
The caller must capture immediately after confirmation, before parser execution;
there is no separate metadata-only confirmation-time SQLite high-water API here.
"""

import errno
import hashlib
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import BinaryIO, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from one_memory.diagnostic_log import diagnostic_event, elapsed_ms
from one_memory.imports.access import (
    AuthorizedSourceFile,
    AuthorizedSourceRoot,
    SourceAccessError,
    SourceAccessErrorCode,
    source_root_identity,
)

# Every chunk re-runs authority, symlink and budget checks; small chunks made
# those checks, not I/O, the copy bottleneck (~19 MB/s at 256 KiB).
_CHUNK_BYTES = 8 * 1024 * 1024
_MANIFEST_MAX_BYTES = 64 * 1024 * 1024
_SNAPSHOT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_BYTE_SUFFIXES = frozenset({".jsonl", ".zstd", ".zst", ".json"})
_SQLITE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3", ".vscdb"})


class SnapshotMode(StrEnum):
    BYTE_EXTENT = "byte_extent"
    SQLITE_BACKUP = "sqlite_backup"


class SnapshotErrorCode(StrEnum):
    INVALID_REQUEST = "snapshot_invalid_request"
    INVALID_DESTINATION = "snapshot_invalid_destination"
    CONFLICT = "snapshot_intent_conflict"
    INCOMPLETE = "snapshot_incomplete"
    INVALID_MANIFEST = "snapshot_invalid_manifest"
    CHECKSUM_MISMATCH = "snapshot_checksum_mismatch"
    NOT_READ_ONLY = "snapshot_not_read_only"
    FILE_LIMIT = "snapshot_file_limit"
    TOTAL_LIMIT = "snapshot_total_limit"
    DISK_BUDGET = "snapshot_disk_budget"
    SCAN_LIMIT = "snapshot_scan_limit"
    CANCELLED = "snapshot_cancelled"
    SOURCE_CHANGED = "snapshot_source_changed"
    UNSUPPORTED_MODE = "snapshot_unsupported_mode"
    SQLITE_UNAVAILABLE = "snapshot_sqlite_unavailable"
    IO_ERROR = "snapshot_io_error"
    CLEANUP_FAILED = "snapshot_cleanup_failed"


class SnapshotError(RuntimeError):
    def __init__(self, code: SnapshotErrorCode) -> None:
        super().__init__(code)
        self.code = code


class SnapshotLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    max_files: int = Field(default=100_000, ge=1, le=100_000)
    max_scan_entries: int = Field(default=200_000, ge=1)
    max_file_bytes: int = Field(default=2 * 1024**3, ge=1)
    max_total_bytes: int = Field(default=4 * 1024**3, ge=1)
    max_disk_bytes: int = Field(default=5 * 1024**3, ge=1)
    min_free_bytes: int = Field(default=128 * 1024**2, ge=0)


class SnapshotIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1, max_length=512)
    root_path: str = Field(min_length=1, max_length=8192)
    requested_root: str = Field(min_length=1, max_length=8192)
    root_identity: str = Field(min_length=1, max_length=512)
    selection_id: str = Field(min_length=1, max_length=512)
    suffix_modes: dict[str, SnapshotMode]


class SnapshotFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    relative_path: str = Field(min_length=1, max_length=8192)
    mode: SnapshotMode
    source_file_identity: str = Field(min_length=1, max_length=256)
    source_size: int = Field(ge=0)
    source_modified_ns: int = Field(ge=0)
    captured_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SnapshotManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    format_version: Literal[1]
    state: Literal["complete"]
    snapshot_id: str
    intent: SnapshotIntent
    files: tuple[SnapshotFile, ...] = Field(max_length=100_000)
    total_bytes: int = Field(ge=0)


@dataclass(frozen=True)
class SourceSnapshot:
    root: Path
    grant: AuthorizedSourceRoot
    manifest: SnapshotManifest
    disk_bytes: int


class _Request(TypedDict):
    snapshot_id: str
    source_id: str
    grant: AuthorizedSourceRoot
    selection_id: str
    suffix_modes: Mapping[str, SnapshotMode]
    cancelled: Callable[[], bool] | None


class SourceSnapshotStore:
    def __init__(self, private_job_dir: Path, *, limits: SnapshotLimits | None = None) -> None:
        self.directory = private_job_dir.expanduser().absolute()
        self.limits = limits or SnapshotLimits()
        _reject_symlinks(self.directory)
        _require_directory(self.directory, mode=0o700)
        self._directory_identity = source_root_identity(self.directory)

    def capture(
        self,
        *,
        snapshot_id: str,
        source_id: str,
        grant: AuthorizedSourceRoot,
        selection_id: str,
        suffix_modes: Mapping[str, SnapshotMode],
        file_predicate: Callable[[AuthorizedSourceFile], bool],
        cancelled: Callable[[], bool] | None = None,
        path_predicate: Callable[[Path], bool] | None = None,
    ) -> SourceSnapshot:
        """Capture all selected files or fail, cleaning this call's staging tree.

        selection_id must change when the adapter's file predicate changes. It is
        an intent version, not inferred from Python callable identity. Repeating
        a committed intent verifies the old copy without rediscovering live files.
        An uncommitted attempt returns INCOMPLETE on retry. Fresh confirmation
        and a new snapshot ID are required, never an automatic new attempt ID.
        """
        request = _Request(
            snapshot_id=snapshot_id,
            source_id=source_id,
            grant=grant,
            selection_id=selection_id,
            suffix_modes=suffix_modes,
            cancelled=cancelled,
        )
        # Record the attempt even when already cancelled. It contains no source
        # payload, and prevents a later resume from silently rediscovering scope.
        intent, authority_check = self._prepare(**(request | {"cancelled": None}))

        def check() -> None:
            if cancelled is not None and cancelled():
                raise SnapshotError(SnapshotErrorCode.CANCELLED)
            authority_check()

        final = self.directory / snapshot_id
        if os.path.lexists(final):
            return self.reopen(**request)
        staging: Path | None = None
        staging_inode: tuple[int, int] | None = None
        phase = "prepare"
        file_kind = "none"
        try:
            attempt = self.directory / f".{snapshot_id}.attempt.json"
            attempt_bytes = self._begin_attempt(attempt, intent, authority_check)
            check()
            phase = "discovery"
            discovery_started = monotonic()
            selected = self._discover(grant, intent, file_predicate, check, path_predicate)
            source_bytes = sum(source_file.size for source_file, _mode in selected)
            diagnostic_event(
                level="info",
                component="import.snapshot",
                event="import.discovery.completed",
                outcome="succeeded",
                job_id=snapshot_id,
                duration_ms=elapsed_ms(discovery_started),
                details={
                    "source_id": source_id,
                    "file_count": len(selected),
                    "sqlite_file_count": sum(
                        mode is SnapshotMode.SQLITE_BACKUP for _file, mode in selected
                    ),
                    "byte_file_count": sum(
                        mode is SnapshotMode.BYTE_EXTENT for _file, mode in selected
                    ),
                    "total_bytes": source_bytes,
                },
            )
            check()
            staging = Path(
                tempfile.mkdtemp(prefix=f".{snapshot_id}.", suffix=".pending", dir=self.directory)
            )
            staging_inode = _inode(staging)
            root = staging / "files"
            root.mkdir(mode=0o700)
            root_inode = _inode(root)

            def capture_check() -> None:
                check()
                _reject_symlinks(root)
                if _inode(staging_path) != staging_inode or _inode(root) != root_inode:
                    raise SnapshotError(SnapshotErrorCode.INVALID_DESTINATION)

            staging_path = staging
            budget = _Budget(self.directory, self.limits, overhead=attempt_bytes)
            files: list[SnapshotFile] = []
            skipped_live_sqlite = False
            phase = "snapshot_copy"
            capture_started = monotonic()
            for source_file, mode in selected:
                file_kind = str(mode)
                capture_check()
                _check_source_file(grant, source_file, mode)
                target = root / source_file.relative_path
                _make_parents(root, source_file.relative_path.parent, capture_check)

                def file_check(path: Path = target) -> None:
                    capture_check()
                    _reject_symlinks(path)

                try:
                    if mode is SnapshotMode.BYTE_EXTENT:
                        budget.reserve(source_file.size)
                        digest = _copy_extent(source_file, grant, target, budget, file_check)
                    else:
                        digest = _backup_sqlite(source_file, grant, target, budget, file_check)
                except SnapshotError as error:
                    # An open database is one file. Failing the whole snapshot
                    # used to drop every transcript beside it, and the leftover
                    # attempt then made every retry incomplete.
                    if error.code is not SnapshotErrorCode.SQLITE_UNAVAILABLE:
                        raise
                    if target.exists():
                        target.unlink()
                    skipped_live_sqlite = True
                    continue
                file_check()
                os.utime(target, ns=(source_file.modified_ns, source_file.modified_ns))
                target.chmod(0o400)
                files.append(
                    SnapshotFile(
                        relative_path=source_file.relative_path.as_posix(),
                        mode=mode,
                        source_file_identity=source_file.file_identity,
                        source_size=source_file.size,
                        source_modified_ns=source_file.modified_ns,
                        captured_size=target.stat().st_size,
                        sha256=digest,
                    )
                )
            if not files and skipped_live_sqlite:
                raise SnapshotError(SnapshotErrorCode.SQLITE_UNAVAILABLE)
            manifest = SnapshotManifest(
                format_version=1,
                state="complete",
                snapshot_id=snapshot_id,
                intent=intent,
                files=tuple(files),
                total_bytes=sum(item.captured_size for item in files),
            )
            capture_duration = elapsed_ms(capture_started)
            diagnostic_event(
                level="info",
                component="import.snapshot",
                event="import.snapshot.completed",
                outcome="succeeded",
                job_id=snapshot_id,
                duration_ms=capture_duration,
                details={
                    "source_id": source_id,
                    "file_count": len(files),
                    "copied_bytes": manifest.total_bytes,
                    "bytes_per_second": round(
                        manifest.total_bytes / max(capture_duration / 1000, 0.001)
                    ),
                },
            )
            phase = "publish"
            encoded = manifest.model_dump_json().encode()
            if len(encoded) > _MANIFEST_MAX_BYTES:
                raise SnapshotError(SnapshotErrorCode.DISK_BUDGET)
            budget.manifest(len(encoded))
            capture_check()
            manifest_tmp = staging / ".manifest.pending"
            with _create_file(manifest_tmp) as sink:
                for offset in range(0, len(encoded), _CHUNK_BYTES):
                    capture_check()
                    _write_chunk(sink, encoded[offset : offset + _CHUNK_BYTES])
                sink.flush()
                os.fchmod(sink.fileno(), 0o400)
                os.fsync(sink.fileno())
            capture_check()
            os.replace(manifest_tmp, staging / "manifest.json")
            for directory, _, _ in os.walk(root, topdown=False, followlinks=False):
                capture_check()
                _reject_symlinks(Path(directory))
                Path(directory).chmod(0o500)
                _fsync_directory(Path(directory))
            capture_check()
            _fsync_directory(staging)
            check()
            try:
                # Publishing the directory makes manifest + all files visible together.
                os.rename(staging, final)
            except OSError as error:
                if error.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise
                return self.reopen(**request)
            staging = None
            _fsync_directory(self.directory)
            check()
            attempt.unlink()
            _fsync_directory(self.directory)
            return self._handle(final / "files", manifest, encoded, grant, check)
        except (SnapshotError, SourceAccessError) as error:
            diagnostic_event(
                level="error",
                component="import.snapshot",
                event="import.snapshot.failed",
                outcome="failed",
                job_id=snapshot_id,
                error_code=str(error.code),
                error_type=type(error).__name__,
                details={
                    "source_id": source_id,
                    "phase": phase,
                    "file_kind": file_kind,
                },
            )
            raise
        except OSError:
            diagnostic_event(
                level="error",
                component="import.snapshot",
                event="import.snapshot.failed",
                outcome="failed",
                job_id=snapshot_id,
                error_code=str(SnapshotErrorCode.IO_ERROR),
                error_type="OSError",
                details={
                    "source_id": source_id,
                    "phase": phase,
                    "file_kind": file_kind,
                },
            )
            raise SnapshotError(SnapshotErrorCode.IO_ERROR) from None
        finally:
            if staging is not None and staging_inode is not None:
                _remove_staging(staging, staging_inode)

    def _begin_attempt(self, path: Path, intent: SnapshotIntent, check: Callable[[], None]) -> int:
        check()
        encoded = intent.model_dump_json().encode()
        if len(encoded) > self.limits.max_disk_bytes:
            raise SnapshotError(SnapshotErrorCode.DISK_BUDGET)
        _Budget(self.directory, self.limits).space(len(encoded))
        try:
            sink = _create_file(path)
        except FileExistsError:
            try:
                previous = SnapshotIntent.model_validate_json(_read_manifest(path, check))
            except (ValidationError, SnapshotError, OSError):
                raise SnapshotError(SnapshotErrorCode.INCOMPLETE) from None
            if previous != intent:
                raise SnapshotError(SnapshotErrorCode.CONFLICT) from None
            raise SnapshotError(SnapshotErrorCode.INCOMPLETE) from None
        with sink:
            _write_chunk(sink, encoded)
            os.fchmod(sink.fileno(), 0o400)
            os.fsync(sink.fileno())
        _fsync_directory(self.directory)
        check()
        return len(encoded)

    def reopen(
        self,
        *,
        snapshot_id: str,
        source_id: str,
        grant: AuthorizedSourceRoot,
        selection_id: str,
        suffix_modes: Mapping[str, SnapshotMode],
        cancelled: Callable[[], bool] | None = None,
    ) -> SourceSnapshot:
        """Revalidate the frozen manifest, file set, permissions and hashes."""
        intent, check = self._prepare(
            snapshot_id=snapshot_id,
            source_id=source_id,
            grant=grant,
            selection_id=selection_id,
            suffix_modes=suffix_modes,
            cancelled=cancelled,
        )
        final = self.directory / snapshot_id
        try:
            check()
            if not (final / "manifest.json").exists():
                raise SnapshotError(SnapshotErrorCode.INCOMPLETE)
            _reject_symlinks(final)
            _require_directory(final, mode=0o700)
            if {item.name for item in final.iterdir()} != {"files", "manifest.json"}:
                raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)
            encoded = _read_manifest(final / "manifest.json", check)
            try:
                manifest = SnapshotManifest.model_validate_json(encoded)
            except ValidationError:
                raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST) from None
            if manifest.snapshot_id != snapshot_id or manifest.intent != intent:
                raise SnapshotError(SnapshotErrorCode.CONFLICT)
            root = final / "files"
            _require_directory(root, mode=0o500)
            _validate_entries(manifest, self.limits, grant.max_file_bytes)
            _validate_tree(
                root,
                {item.relative_path: item for item in manifest.files},
                check,
            )
            handle = self._handle(root, manifest, encoded, grant, check)
            if handle.disk_bytes > self.limits.max_disk_bytes:
                raise SnapshotError(SnapshotErrorCode.DISK_BUDGET)
            for entry in manifest.files:
                check()
                frozen_file = handle.grant.authorize_file(Path(entry.relative_path))
                _require_readonly(frozen_file.path)
                if frozen_file.size != entry.captured_size:
                    raise SnapshotError(SnapshotErrorCode.CHECKSUM_MISMATCH)
                with frozen_file.open_binary() as source:
                    digest = _hash_stream(
                        source,
                        check,
                        path=frozen_file.path,
                        size=entry.captured_size,
                        readonly=True,
                    )
                    if digest != entry.sha256:
                        raise SnapshotError(SnapshotErrorCode.CHECKSUM_MISMATCH)
                _require_readonly(frozen_file.path)
            check()
            return handle
        except OSError:
            raise SnapshotError(SnapshotErrorCode.IO_ERROR) from None

    def _prepare(
        self,
        *,
        snapshot_id: str,
        source_id: str,
        grant: AuthorizedSourceRoot,
        selection_id: str,
        suffix_modes: Mapping[str, SnapshotMode],
        cancelled: Callable[[], bool] | None,
    ) -> tuple[SnapshotIntent, Callable[[], None]]:
        if not _SNAPSHOT_ID.fullmatch(snapshot_id) or source_id != grant.source_id:
            raise SnapshotError(SnapshotErrorCode.INVALID_REQUEST)
        if not grant.root_identity:
            raise SourceAccessError(SourceAccessErrorCode.GRANT_REQUIRED)
        if self.directory.is_relative_to(grant.root) or grant.root.is_relative_to(self.directory):
            raise SnapshotError(SnapshotErrorCode.INVALID_DESTINATION)
        modes = _validated_modes(suffix_modes)
        try:
            intent = SnapshotIntent(
                source_id=source_id,
                root_path=str(grant.root),
                requested_root=str(grant.requested_root or grant.root),
                root_identity=grant.root_identity,
                selection_id=selection_id,
                suffix_modes=modes,
            )
        except ValidationError:
            raise SnapshotError(SnapshotErrorCode.INVALID_REQUEST) from None

        def check() -> None:
            if cancelled is not None and cancelled():
                raise SnapshotError(SnapshotErrorCode.CANCELLED)
            if grant.access_check is not None:
                grant.access_check()
            _reject_symlinks(grant.requested_root or grant.root)
            _reject_symlinks(grant.root)
            if source_root_identity(grant.requested_root or grant.root) != grant.root_identity:
                raise SourceAccessError(SourceAccessErrorCode.SOURCE_IDENTITY_CHANGED)
            _reject_symlinks(self.directory)
            if source_root_identity(self.directory) != self._directory_identity:
                raise SnapshotError(SnapshotErrorCode.INVALID_DESTINATION)

        check()
        return intent, check

    def _discover(
        self,
        grant: AuthorizedSourceRoot,
        intent: SnapshotIntent,
        predicate: Callable[[AuthorizedSourceFile], bool],
        check: Callable[[], None],
        path_predicate: Callable[[Path], bool] | None,
    ) -> list[tuple[AuthorizedSourceFile, SnapshotMode]]:
        # The ordinary discovery helper silently prunes symlink directories and
        # walk errors. A complete bounded manifest must instead report either.
        stack = [(grant.root, _inode(grant.root))]
        selected: list[tuple[AuthorizedSourceFile, SnapshotMode]] = []
        inspected = total = 0
        while stack:
            directory, identity = stack.pop()
            check()
            _reject_symlinks(directory)
            if _inode(directory) != identity:
                raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
            with os.scandir(directory) as entries:
                for entry in entries:
                    check()
                    inspected += 1
                    if inspected > self.limits.max_scan_entries:
                        raise SnapshotError(SnapshotErrorCode.SCAN_LIMIT)
                    path = Path(entry.path)
                    if path_predicate is not None and not path_predicate(
                        path.relative_to(grant.root)
                    ):
                        continue
                    details = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(details.st_mode):
                        raise SourceAccessError(SourceAccessErrorCode.SYMLINK_NOT_ALLOWED)
                    if stat.S_ISDIR(details.st_mode):
                        stack.append((path, (details.st_dev, details.st_ino)))
                        continue
                    mode = intent.suffix_modes.get(path.suffix.lower())
                    if mode is None:
                        continue
                    source_file = grant.authorize_file(path)
                    if not predicate(source_file):
                        continue
                    _validate_relative(source_file.relative_path.as_posix())
                    _check_file_mode(source_file.relative_path, mode)
                    selected.append((source_file, mode))
                    total += source_file.size
                    if (
                        len(selected) > self.limits.max_files
                        or source_file.size > self.limits.max_file_bytes
                    ):
                        raise SnapshotError(SnapshotErrorCode.FILE_LIMIT)
                    if total > self.limits.max_total_bytes:
                        raise SnapshotError(SnapshotErrorCode.TOTAL_LIMIT)
            check()
            if _inode(directory) != identity:
                raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
        return sorted(selected, key=lambda item: item[0].relative_path.as_posix())

    def _handle(
        self,
        root: Path,
        manifest: SnapshotManifest,
        encoded: bytes,
        original: AuthorizedSourceRoot,
        check: Callable[[], None],
    ) -> SourceSnapshot:
        check()
        _reject_symlinks(root)
        _require_directory(root, mode=0o500)
        return SourceSnapshot(
            root=root,
            grant=AuthorizedSourceRoot(
                source_id=original.source_id,
                root=root,
                requested_root=root,
                root_identity=source_root_identity(root),
                max_file_bytes=min(original.max_file_bytes, self.limits.max_file_bytes),
                access_check=check,
            ),
            manifest=manifest,
            disk_bytes=manifest.total_bytes + len(encoded),
        )


@dataclass
class _Budget:
    directory: Path
    limits: SnapshotLimits
    used: int = 0
    overhead: int = 0

    def reserve(self, amount: int) -> None:
        if amount > self.limits.max_file_bytes:
            raise SnapshotError(SnapshotErrorCode.FILE_LIMIT)
        if self.used + amount > self.limits.max_total_bytes:
            raise SnapshotError(SnapshotErrorCode.TOTAL_LIMIT)
        if self.used + amount + self.overhead > self.limits.max_disk_bytes:
            raise SnapshotError(SnapshotErrorCode.DISK_BUDGET)
        self.space(amount)
        self.used += amount

    def space(self, amount: int) -> None:
        if shutil.disk_usage(self.directory).free < self.limits.min_free_bytes + amount:
            raise SnapshotError(SnapshotErrorCode.DISK_BUDGET)

    def manifest(self, amount: int) -> None:
        if self.used + amount + self.overhead > self.limits.max_disk_bytes:
            raise SnapshotError(SnapshotErrorCode.DISK_BUDGET)
        self.space(amount)


def _copy_extent(
    source_file: AuthorizedSourceFile,
    grant: AuthorizedSourceRoot,
    target: Path,
    budget: _Budget,
    check: Callable[[], None],
) -> str:
    digest = hashlib.sha256()
    check()
    with source_file.open_binary() as source:
        check()
        _check_source_file(grant, source_file, SnapshotMode.BYTE_EXTENT)
        with _create_file(target) as sink:
            destination_identity = _inode(target)

            def copy_check() -> None:
                check()
                if _inode(target) != destination_identity:
                    raise SnapshotError(SnapshotErrorCode.INVALID_DESTINATION)

            remaining = source_file.size
            while remaining:
                copy_check()
                _check_source_file(grant, source_file, SnapshotMode.BYTE_EXTENT)
                # BufferedReader.read(n) may prefetch bytes beyond the approved
                # extent. Use the guarded descriptor without buffered read-ahead.
                chunk = os.read(source.fileno(), min(_CHUNK_BYTES, remaining))
                if not chunk:
                    raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
                copy_check()
                _check_source_file(grant, source_file, SnapshotMode.BYTE_EXTENT)
                budget.space(len(chunk))
                _write_chunk(sink, chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            copy_check()
            _check_source_file(grant, source_file, SnapshotMode.BYTE_EXTENT)
            sink.flush()
            os.fsync(sink.fileno())
    return digest.hexdigest()


def _backup_sqlite(
    source_file: AuthorizedSourceFile,
    grant: AuthorizedSourceRoot,
    target: Path,
    budget: _Budget,
    check: Callable[[], None],
) -> str:
    closed_wal = False
    changed_ns: int | None = None
    started = time.monotonic()

    def sqlite_check() -> None:
        check()
        if time.monotonic() - started > 30:
            raise SnapshotError(SnapshotErrorCode.SQLITE_UNAVAILABLE)
        _check_source_file(grant, source_file, SnapshotMode.SQLITE_BACKUP)
        for suffix in ("-wal", "-shm", "-journal"):
            path = source_file.path.with_name(source_file.path.name + suffix)
            if os.path.lexists(path):
                if closed_wal:
                    raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
                _reject_symlinks(path)
                grant.authorize_file(path)
        if closed_wal:
            details = source_file.path.stat()
            if (
                details.st_size != source_file.size
                or details.st_mtime_ns != source_file.modified_ns
                or details.st_ctime_ns != changed_ns
            ):
                raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
        else:
            _reject_writable_shm(source_file.path)

    sqlite_check()
    # Never open a sidecar-free WAL source through SQLite: even mode=ro can
    # create sidecars. A partial set must not fall back to ignoring a live WAL.
    with source_file.open_binary() as header_file:
        sqlite_check()
        header = os.read(header_file.fileno(), 20)
    if header[18:20] == b"\x02\x02":
        sidecars = [
            os.path.lexists(source_file.path.with_name(source_file.path.name + suffix))
            for suffix in ("-wal", "-shm", "-journal")
        ]
        if any(sidecars) and (not all(sidecars[:2]) or sidecars[2]):
            raise SnapshotError(SnapshotErrorCode.SQLITE_UNAVAILABLE)
        closed_wal = not any(sidecars)
        if closed_wal:
            changed_ns = source_file.path.stat().st_ctime_ns
    try:
        sqlite_check()
        source_context = (
            _open_closed_wal_snapshot_source(source_file, grant, target, budget, sqlite_check)
            if closed_wal
            else _open_sqlite_snapshot_source(source_file, sqlite_check)
        )
        with source_context as source:
            source.execute("BEGIN")
            source.execute("SELECT count(*) FROM sqlite_schema").fetchone()
            page_size = source.execute("PRAGMA page_size").fetchone()[0]
            page_count = source.execute("PRAGMA page_count").fetchone()[0]
            size = page_size * page_count
            if size > grant.max_file_bytes:
                raise SourceAccessError(SourceAccessErrorCode.FILE_TOO_LARGE)
            budget.reserve(size)
            sqlite_check()
            with _create_file(target):
                pass
            destination = sqlite3.connect(f"{target.as_uri()}?mode=rw", uri=True, timeout=0.1)
            try:
                destination.execute("PRAGMA journal_mode=OFF")
                destination.execute("PRAGMA synchronous=OFF")

                def progress(status: int, remaining: int, total: int) -> None:
                    sqlite_check()
                    if total != page_count and status == sqlite3.SQLITE_OK:
                        raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
                    if time.monotonic() - started > 30:
                        raise SnapshotError(SnapshotErrorCode.SQLITE_UNAVAILABLE)
                    budget.space(min(64, remaining) * page_size)

                sqlite_check()
                source.backup(destination, pages=64, progress=progress, sleep=0.01)
                sqlite_check()
                destination.execute("PRAGMA journal_mode=DELETE")
                if closed_wal:
                    # Bound native validation and preserve the precise cancellation
                    # / permission error; sqlite3 masks callback exceptions.
                    interrupted: Exception | None = None

                    def integrity_progress() -> int:
                        nonlocal interrupted
                        try:
                            sqlite_check()
                        except Exception as error:
                            interrupted = error
                            return 1
                        return 0

                    destination.set_progress_handler(integrity_progress, 1000)
                    try:
                        if destination.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                            raise SnapshotError(SnapshotErrorCode.SQLITE_UNAVAILABLE)
                    except sqlite3.Error:
                        if interrupted is not None:
                            raise interrupted from None
                        raise
                    finally:
                        destination.set_progress_handler(None, 0)
                    sqlite_check()
            finally:
                destination.close()
            source.rollback()
        sqlite_check()
        if target.stat().st_size != size:
            raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
        with target.open("rb") as copied:
            digest = _hash_stream(copied, sqlite_check, path=target, size=size)
            sqlite_check()
            os.fsync(copied.fileno())
        sqlite_check()
        return digest
    except sqlite3.Error:
        raise SnapshotError(SnapshotErrorCode.SQLITE_UNAVAILABLE) from None


@contextmanager
def _open_closed_wal_snapshot_source(
    source_file: AuthorizedSourceFile,
    grant: AuthorizedSourceRoot,
    target: Path,
    budget: _Budget,
    check: Callable[[], None],
) -> Iterator[sqlite3.Connection]:
    def source_digest() -> str:
        check()
        with source_file.open_binary() as stream:
            check()
            digest = _hash_stream(stream, check, path=source_file.path, size=source_file.size)
        check()
        return digest

    expected = source_digest()
    # Temporary bytes count toward disk, but are not a second imported payload.
    budget.manifest(source_file.size)
    budget.overhead += source_file.size
    staged = target.with_name(target.name + ".sqlite-stage")
    try:
        copied_digest = _copy_extent(source_file, grant, staged, budget, check)
        if copied_digest != expected or source_digest() != expected:
            raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
        check()
        _reject_symlinks(staged)
        staged.chmod(0o400)
        staged_identity = _inode(staged)

        def private_check() -> None:
            check()
            _reject_symlinks(staged)
            _require_readonly(staged)
            if _inode(staged) != staged_identity:
                raise SnapshotError(SnapshotErrorCode.INVALID_DESTINATION)

        with staged.open("rb") as stream:
            if (
                _hash_stream(
                    stream, private_check, path=staged, size=source_file.size, readonly=True
                )
                != expected
            ):
                raise SnapshotError(SnapshotErrorCode.CHECKSUM_MISMATCH)
            private_check()
            connection = sqlite3.connect(
                f"{staged.as_uri()}?mode=ro&immutable=1", uri=True, timeout=0.1
            )
            try:
                private_check()
                connection.execute("PRAGMA query_only=ON")
                yield connection
                private_check()
            finally:
                connection.close()
        if source_digest() != expected:
            raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
    finally:
        staged.unlink(missing_ok=True)
        budget.overhead -= source_file.size


def _reject_writable_shm(database: Path) -> None:
    # SQLite shares WAL mappings by inode inside a process. readonly_shm cannot
    # downgrade an existing writable mapping. The job owner must serialize this
    # capture with other in-process reads of the same source (host writers run
    # separately). Inspect descriptor metadata only, never descriptor contents.
    if os.name != "posix" or not Path("/dev/fd").is_dir():
        raise SnapshotError(SnapshotErrorCode.SQLITE_UNAVAILABLE)
    import fcntl

    shm = database.with_name(database.name + "-shm")
    if not shm.exists():
        return
    identity = _inode(shm)
    for name in os.listdir("/dev/fd"):
        try:
            descriptor = int(name)
            details = os.fstat(descriptor)
            flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
        except (ValueError, OSError):
            continue
        if (details.st_dev, details.st_ino) == identity and flags & os.O_ACCMODE != os.O_RDONLY:
            raise SnapshotError(SnapshotErrorCode.SQLITE_UNAVAILABLE)


@contextmanager
def _open_sqlite_snapshot_source(
    source_file: AuthorizedSourceFile, check: Callable[[], None]
) -> Iterator[sqlite3.Connection]:
    # The existing file guard still pins/validates the source. The ordinary
    # open_sqlite_readonly helper lacks readonly_shm, and can write WAL read marks.
    with source_file.open_binary():
        check()
        connection = sqlite3.connect(
            f"{source_file.path.as_uri()}?mode=ro&readonly_shm=1", uri=True, timeout=0.1
        )
        try:
            check()
            connection.execute("PRAGMA query_only=ON")
            yield connection
        finally:
            connection.close()


def _check_source_file(
    grant: AuthorizedSourceRoot, source_file: AuthorizedSourceFile, mode: SnapshotMode
) -> None:
    _reject_symlinks(source_file.path)
    current = grant.authorize_file(source_file.relative_path)
    if current.file_identity != source_file.file_identity:
        raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)
    if mode is SnapshotMode.BYTE_EXTENT and (
        current.size < source_file.size
        or (current.size == source_file.size and current.modified_ns != source_file.modified_ns)
    ):
        raise SnapshotError(SnapshotErrorCode.SOURCE_CHANGED)


def _validated_modes(modes: Mapping[str, SnapshotMode]) -> dict[str, SnapshotMode]:
    result: dict[str, SnapshotMode] = {}
    if not modes:
        raise SnapshotError(SnapshotErrorCode.UNSUPPORTED_MODE)
    for suffix, raw_mode in modes.items():
        try:
            mode = SnapshotMode(raw_mode)
        except ValueError:
            raise SnapshotError(SnapshotErrorCode.UNSUPPORTED_MODE) from None
        supported = _BYTE_SUFFIXES if mode is SnapshotMode.BYTE_EXTENT else _SQLITE_SUFFIXES
        if suffix not in supported:
            raise SnapshotError(SnapshotErrorCode.UNSUPPORTED_MODE)
        result[suffix] = mode
    return dict(sorted(result.items()))


def _check_file_mode(path: Path, mode: SnapshotMode) -> None:
    if path.suffix.lower() == ".json" and (
        mode is not SnapshotMode.BYTE_EXTENT or not path.name.endswith(".meta.json")
    ):
        raise SnapshotError(SnapshotErrorCode.UNSUPPORTED_MODE)


def _validate_relative(value: str) -> Path:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {".", ".."} for part in value.split("/"))
        or path.as_posix() != value
        or "\\" in value
        or "\0" in value
    ):
        raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)
    return Path(value)


def _validate_entries(
    manifest: SnapshotManifest, limits: SnapshotLimits, grant_max_bytes: int
) -> set[str]:
    paths: set[str] = set()
    if len(manifest.files) > limits.max_files:
        raise SnapshotError(SnapshotErrorCode.FILE_LIMIT)
    for item in manifest.files:
        relative = _validate_relative(item.relative_path)
        _check_file_mode(relative, item.mode)
        if (
            item.relative_path in paths
            or manifest.intent.suffix_modes.get(relative.suffix.lower()) != item.mode
            or (item.mode is SnapshotMode.BYTE_EXTENT and item.captured_size != item.source_size)
        ):
            raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)
        if max(item.captured_size, item.source_size) > min(limits.max_file_bytes, grant_max_bytes):
            raise SnapshotError(SnapshotErrorCode.FILE_LIMIT)
        paths.add(item.relative_path)
    if manifest.total_bytes != sum(item.captured_size for item in manifest.files):
        raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)
    if manifest.total_bytes > limits.max_total_bytes:
        raise SnapshotError(SnapshotErrorCode.TOTAL_LIMIT)
    return paths


def _validate_tree(
    root: Path,
    expected: Mapping[str, SnapshotFile],
    check: Callable[[], None],
) -> None:
    expected_directories = {
        parent.as_posix()
        for item in expected
        for parent in Path(item).parents
        if parent != Path(".")
    }
    found: set[str] = set()
    stack = [root]
    while stack:
        directory = stack.pop()
        check()
        _reject_symlinks(directory)
        _require_directory(directory, mode=0o500)
        with os.scandir(directory) as entries:
            for entry in entries:
                check()
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                if entry.is_dir(follow_symlinks=False):
                    if relative not in expected_directories:
                        raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)
                    stack.append(path)
                else:
                    if relative not in expected:
                        raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)
                    _require_readonly(path)
                    item = expected[relative]
                    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                    with os.fdopen(os.open(path, flags), "rb") as source:
                        digest = _hash_stream(
                            source,
                            check,
                            path=path,
                            size=item.captured_size,
                            readonly=True,
                        )
                    if digest != item.sha256:
                        raise SnapshotError(SnapshotErrorCode.CHECKSUM_MISMATCH)
                    found.add(relative)
    if found != set(expected):
        raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)


def _reject_symlinks(path: Path) -> None:
    for component in (*reversed(path.parents), path):
        if component.is_symlink():
            raise SourceAccessError(SourceAccessErrorCode.SYMLINK_NOT_ALLOWED)


def _inode(path: Path) -> tuple[int, int]:
    details = path.lstat()
    return details.st_dev, details.st_ino


def _require_directory(path: Path, *, mode: int) -> None:
    details = path.lstat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != mode
        or (hasattr(os, "getuid") and details.st_uid != os.getuid())
    ):
        raise SnapshotError(SnapshotErrorCode.INVALID_DESTINATION)


def _require_readonly(path: Path) -> None:
    details = path.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o400
        or details.st_nlink != 1
        or (hasattr(os, "getuid") and details.st_uid != os.getuid())
    ):
        raise SnapshotError(SnapshotErrorCode.NOT_READ_ONLY)


def _make_parents(root: Path, relative: Path, check: Callable[[], None]) -> None:
    parent = root
    for part in relative.parts:
        check()
        parent /= part
        parent.mkdir(mode=0o700, exist_ok=True)
        _reject_symlinks(parent)
        _require_directory(parent, mode=0o700)


def _create_file(path: Path) -> BinaryIO:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    return os.fdopen(os.open(path, flags, 0o600), "wb", buffering=0)


def _write_chunk(sink: BinaryIO, chunk: bytes) -> None:
    if sink.write(chunk) != len(chunk):
        raise SnapshotError(SnapshotErrorCode.IO_ERROR)


def _read_manifest(path: Path, check: Callable[[], None]) -> bytes:
    check()
    _reject_symlinks(path)
    _require_readonly(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        size = os.fstat(source.fileno()).st_size
        if size > _MANIFEST_MAX_BYTES:
            raise SnapshotError(SnapshotErrorCode.INVALID_MANIFEST)
        return b"".join(_checked_chunks(source, check, path=path, size=size, readonly=True))


def _hash_stream(
    source: BinaryIO,
    check: Callable[[], None],
    *,
    path: Path,
    size: int,
    readonly: bool = False,
) -> str:
    digest = hashlib.sha256()
    for chunk in _checked_chunks(source, check, path=path, size=size, readonly=readonly):
        digest.update(chunk)
    return digest.hexdigest()


def _checked_chunks(
    source: BinaryIO,
    check: Callable[[], None],
    *,
    path: Path,
    size: int,
    readonly: bool,
) -> Iterator[bytes]:
    initial = os.fstat(source.fileno())
    remaining = size
    while True:
        check()
        _reject_symlinks(path)
        current = path.lstat()
        if (
            (current.st_dev, current.st_ino) != (initial.st_dev, initial.st_ino)
            or current.st_size != size
            or current.st_mtime_ns != initial.st_mtime_ns
            or not stat.S_ISREG(current.st_mode)
        ):
            raise SnapshotError(SnapshotErrorCode.CHECKSUM_MISMATCH)
        if readonly:
            _require_readonly(path)
        if remaining == 0:
            return
        chunk = os.read(source.fileno(), min(_CHUNK_BYTES, remaining))
        if not chunk:
            raise SnapshotError(SnapshotErrorCode.CHECKSUM_MISMATCH)
        remaining -= len(chunk)
        yield chunk


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_staging(path: Path, identity: tuple[int, int]) -> None:
    try:
        # Only this call's unpublished tree is writable for cleanup. Never chmod
        # a symlink target, the original source, or an existing committed copy.
        _reject_symlinks(path)
        if _inode(path) != identity:
            raise SnapshotError(SnapshotErrorCode.CLEANUP_FAILED)
        # Python/Linux does not implement chmod(path, follow_symlinks=False).
        # Walk without following links and chmod the already-open directory
        # descriptors instead: this preserves the no-symlink boundary without
        # relying on a platform-specific path API.
        for _directory, _directories, _files, descriptor in os.fwalk(path, follow_symlinks=False):
            os.fchmod(descriptor, 0o700)
        shutil.rmtree(path)
    except OSError:
        raise SnapshotError(SnapshotErrorCode.CLEANUP_FAILED) from None
