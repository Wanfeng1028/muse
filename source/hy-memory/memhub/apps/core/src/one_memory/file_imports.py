import asyncio
import hashlib
import json
import os
import shutil
import stat
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast, overload
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from one_memory.imports.chat_exports import MAX_UPLOAD_BYTES, parse_chat_export
from one_memory.imports.jobs import ImportJobStore
from one_memory.imports.manual_transcript import ManualTranscriptError
from one_memory.imports.memory_content import parse_memory_content
from one_memory.imports.models import EvidenceContentKind, WrittenBy


class ImportPreviewMessage(BaseModel):
    role: str
    text: str
    created_at: datetime | None = None
    truncated: bool = False
    written_by: WrittenBy = WrittenBy.UNKNOWN


class FileImportReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: UUID
    filename: str
    vendor: Literal["chatgpt", "claude", "generic", "memory-content"]
    content_kind: EvidenceContentKind = EvidenceContentKind.RAW_CONVERSATION
    source_id: str
    messages: int
    conversations: int
    human_messages: int
    agent_messages: int
    unknown_author_messages: int = 0
    skipped_records: int
    ignored_files: int
    checksum: str
    created_at: datetime
    committed: bool = False
    preview: tuple[ImportPreviewMessage, ...] = ()


class FileImportConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]


class FileImportOperationConflict(RuntimeError):
    pass


class FileImportOperationUnavailable(RuntimeError):
    pass


class _InvalidUpload(ValueError):
    pass


def _operation_id(value: str) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid_import_operation_id") from None
    return value


def _upload_fingerprint(filename: str, kind: EvidenceContentKind, checksum: str) -> str:
    return hashlib.sha256(
        json.dumps(
            [filename, kind.value, checksum], ensure_ascii=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_import_record_key")
        result[key] = value
    return result


class FileImportOperationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    operation_id: str
    state: Literal["not_found", "pending", "completed", "failed"]
    upload_id: UUID | None = None
    code: Literal["import_upload_invalid"] | None = None
    # Completion is historical staging, not current availability or confirmation.
    upload_state: Literal["staged", "committed", "missing", "unknown"] | None = None


class _UploadOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1] = 1
    operation_id: str
    upload_id: str
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: Literal["pending", "completed", "failed"] = "pending"
    code: Literal["import_upload_invalid"] | None = None

    @field_validator("operation_id", "upload_id")
    @classmethod
    def identifier(cls, value: str) -> str:
        return _operation_id(value)

    @model_validator(mode="after")
    def terminal(self) -> "_UploadOperation":
        if (self.state == "failed") != (self.code is not None):
            raise ValueError("invalid_import_operation_record")
        return self


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_private_record(path: Path) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_mode & 0o077
            or (hasattr(os, "getuid") and info.st_uid != os.getuid())
            or info.st_size > 16_384
        ):
            raise ValueError("invalid_import_operation_file")
        contents = source.read(16_385)
        after = os.fstat(source.fileno())
        current = path.lstat()
        if (
            len(contents) > 16_384
            or (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode, info.st_nlink)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_mode, after.st_nlink)
            or current.st_ino != info.st_ino
            or current.st_dev != info.st_dev
            or current.st_mode != after.st_mode
            or current.st_nlink != after.st_nlink
            or current.st_uid != after.st_uid
            or current.st_mtime_ns != after.st_mtime_ns
            or current.st_ctime_ns != after.st_ctime_ns
            or stat.S_ISLNK(current.st_mode)
        ):
            raise ValueError("changed_import_operation_file")
        return contents


class FileImportStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @overload
    def prepare(
        self,
        payload: bytes,
        filename: str,
        *,
        input_kind: EvidenceContentKind = EvidenceContentKind.RAW_CONVERSATION,
        operation_id: None = None,
    ) -> FileImportReceipt: ...

    @overload
    def prepare(
        self,
        payload: bytes,
        filename: str,
        *,
        input_kind: EvidenceContentKind = EvidenceContentKind.RAW_CONVERSATION,
        operation_id: str,
    ) -> FileImportOperationReceipt: ...

    def prepare(
        self,
        payload: bytes,
        filename: str,
        *,
        input_kind: EvidenceContentKind = EvidenceContentKind.RAW_CONVERSATION,
        operation_id: str | None = None,
    ) -> FileImportReceipt | FileImportOperationReceipt:
        if operation_id is not None:
            return self._prepare_operation(payload, filename, input_kind, operation_id)
        return self._prepare_upload(payload, filename, input_kind=input_kind)

    def _operation_directory(self, *, create: bool = False) -> Path:
        directory = self.root / "operations"
        if create:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_info = self.root.lstat()
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_mode & 0o022
            or (hasattr(os, "getuid") and root_info.st_uid != os.getuid())
        ):
            raise ValueError("invalid_import_store_directory")
        if create:
            directory.mkdir(exist_ok=True, mode=0o700)
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_mode & 0o077
            or (hasattr(os, "getuid") and info.st_uid != os.getuid())
        ):
            raise ValueError("invalid_import_operation_directory")
        return directory

    def _operation_record(self, operation_id: str) -> _UploadOperation | None:
        try:
            directory = self._operation_directory()
            path = directory / f"{operation_id}.json"
            path.lstat()
        except FileNotFoundError:
            return None
        contents = _read_private_record(path)
        record = _UploadOperation.model_validate(
            json.loads(contents, object_pairs_hook=_unique_object)
        )
        if record.operation_id != operation_id:
            raise ValueError("import_operation_identity_mismatch")
        return record

    def _operation_receipt(self, record: _UploadOperation) -> FileImportOperationReceipt:
        result = FileImportOperationReceipt(
            operation_id=record.operation_id, state=record.state, code=record.code
        )
        if record.state != "completed":
            return result
        upload_id = UUID(record.upload_id)
        try:
            directory = self.root / "staging" / record.upload_id
            info = directory.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_mode & 0o077
                or (hasattr(os, "getuid") and info.st_uid != os.getuid())
            ):
                raise ValueError("invalid_upload_directory")
            path = directory / "receipt.json"
            contents = _read_private_record(path)
            receipt = FileImportReceipt.model_validate_json(contents)
            if (
                receipt.upload_id != upload_id
                or receipt.source_id != f"{receipt.vendor}-export"
                or len(receipt.checksum) != 64
                or any(char not in "0123456789abcdef" for char in receipt.checksum)
                or _upload_fingerprint(receipt.filename, receipt.content_kind, receipt.checksum)
                != record.fingerprint
            ):
                raise ValueError("import_upload_identity_mismatch")
            upload_state = "committed" if receipt.committed else "staged"
            for name in ("original", "messages.jsonl"):
                info = (directory / name).lstat()
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_mode & 0o077
                    or (hasattr(os, "getuid") and info.st_uid != os.getuid())
                ):
                    raise ValueError("invalid_upload_file")
            if not receipt.committed:
                target = self.root / "ready" / receipt.source_id / f"{receipt.checksum}.jsonl"
                with suppress(FileNotFoundError):
                    if target.samefile(directory / "messages.jsonl"):
                        upload_state = "committed"
            if _read_private_record(path) != contents:
                raise ValueError("changed_import_upload_receipt")
        except (FileNotFoundError, KeyError):
            upload_state = "missing"
        except (OSError, ValueError):
            upload_state = "unknown"
        return result.model_copy(update={"upload_id": upload_id, "upload_state": upload_state})

    def lookup_operation(self, operation_id: str) -> FileImportOperationReceipt:
        _operation_id(operation_id)
        try:
            record = self._operation_record(operation_id)
            if record is None:
                return FileImportOperationReceipt(operation_id=operation_id, state="not_found")
            return self._operation_receipt(record)
        except (OSError, ValueError):
            raise FileImportOperationUnavailable("import_upload_operation_unavailable") from None

    def _write_operation(self, record: _UploadOperation, *, reserve: bool) -> None:
        directory = self._operation_directory(create=reserve)
        path = directory / f"{record.operation_id}.json"
        temporary = path if reserve else directory / f".{record.operation_id}.{uuid4()}.tmp"
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(record.model_dump_json())
                output.flush()
                os.fsync(output.fileno())
            if not reserve:
                previous = self._operation_record(record.operation_id)
                if previous != record.model_copy(update={"state": "pending", "code": None}):
                    raise ValueError("import_operation_reservation_changed")
                os.replace(temporary, path)
            _sync_directory(directory)
            if reserve:
                _sync_directory(self.root)
                _sync_directory(self.root.parent)
        finally:
            # An incomplete reservation is deliberately retained as unavailable.
            if not reserve:
                temporary.unlink(missing_ok=True)

    def _prepare_operation(
        self, payload: bytes, filename: str, input_kind: EvidenceContentKind, operation_id: str
    ) -> FileImportOperationReceipt:
        _operation_id(operation_id)
        kind = EvidenceContentKind(input_kind)
        if len(payload) > MAX_UPLOAD_BYTES:
            raise ValueError("export_size_exceeded")
        fingerprint = _upload_fingerprint(filename, kind, hashlib.sha256(payload).hexdigest())
        record = _UploadOperation(
            operation_id=operation_id, upload_id=str(uuid4()), fingerprint=fingerprint
        )
        try:
            try:
                self._write_operation(record, reserve=True)
            except FileExistsError:
                previous = self._operation_record(operation_id)
                if previous is None:
                    raise ValueError("import_operation_reservation_missing") from None
                if previous.fingerprint != fingerprint:
                    raise FileImportOperationConflict("import_upload_operation_conflict") from None
                return self._operation_receipt(previous)
            try:
                self._prepare_upload(
                    payload,
                    filename,
                    input_kind=kind,
                    upload_id=UUID(record.upload_id),
                    durable=True,
                )
            except _InvalidUpload:
                record = record.model_copy(
                    update={"state": "failed", "code": "import_upload_invalid"}
                )
            else:
                record = record.model_copy(update={"state": "completed"})
            self._write_operation(record, reserve=False)
            return self._operation_receipt(record)
        except (OSError, ValueError):
            raise FileImportOperationUnavailable("import_upload_operation_unavailable") from None

    def _prepare_upload(
        self,
        payload: bytes,
        filename: str,
        *,
        input_kind: EvidenceContentKind,
        upload_id: UUID | None = None,
        durable: bool = False,
    ) -> FileImportReceipt:
        kind = EvidenceContentKind(input_kind)
        try:
            parsed = (
                parse_memory_content(payload, filename)
                if kind is EvidenceContentKind.MEMORY_CONTENT
                else parse_chat_export(payload, filename)
            )
        except ValueError:
            if durable:
                raise _InvalidUpload("import_upload_invalid") from None
            raise
        upload_id = upload_id or uuid4()
        directory = self.root / "staging" / str(upload_id)
        if durable:
            directory.parent.mkdir(exist_ok=True, mode=0o700)
            info = directory.parent.lstat()
            # Legacy uploads create this container under the caller's umask.
            # Read/traverse bits are compatible; writable parents are not.
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_mode & 0o022
                or (hasattr(os, "getuid") and info.st_uid != os.getuid())
            ):
                raise ValueError("invalid_import_staging_directory")
        directory.mkdir(parents=True, mode=0o700)
        checksum = hashlib.sha256(payload).hexdigest()
        receipt = FileImportReceipt(
            upload_id=upload_id,
            filename=filename,
            vendor=parsed.vendor,
            content_kind=kind,
            source_id=f"{parsed.vendor}-export",
            messages=len(parsed.messages),
            conversations=len({message.conversation_id for message in parsed.messages}),
            human_messages=sum(message.written_by == "person" for message in parsed.messages),
            agent_messages=sum(message.written_by == "agent" for message in parsed.messages),
            unknown_author_messages=sum(
                message.written_by == "unknown" for message in parsed.messages
            ),
            skipped_records=parsed.skipped_records,
            ignored_files=parsed.ignored_files,
            checksum=checksum,
            created_at=datetime.now(UTC),
            preview=tuple(
                ImportPreviewMessage(
                    role=message.role,
                    written_by=message.written_by,
                    text=message.verbatim[:600],
                    created_at=message.created_at,
                    truncated=len(message.verbatim) > 600,
                )
                for message in parsed.messages[:4]
            ),
        )
        try:
            (directory / "original").write_bytes(payload)
            conversations: dict[str, list[dict[str, object]]] = {}
            for message in parsed.messages:
                conversations.setdefault(message.conversation_id, []).append(asdict(message))
            snapshot_ids = {
                key: hashlib.sha256(
                    json.dumps(values, sort_keys=True, default=str).encode()
                ).hexdigest()
                for key, values in conversations.items()
            }
            with (directory / "messages.jsonl").open("w", encoding="utf-8") as output:
                for message in parsed.messages:
                    record = asdict(message)
                    # Snapshot time is not message time. Keep changed conversations
                    # beside earlier snapshots rather than overwriting their evidence.
                    record["conversation_id"] += (
                        f":snapshot:{snapshot_ids[message.conversation_id]}"
                    )
                    output.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            (directory / "receipt.json").write_text(receipt.model_dump_json(), encoding="utf-8")
            for file in directory.iterdir():
                file.chmod(0o600)
                if durable:
                    with file.open("rb") as staged:
                        os.fsync(staged.fileno())
            if durable:
                _sync_directory(directory)
                _sync_directory(directory.parent)
                _sync_directory(self.root)
        except Exception:
            shutil.rmtree(directory)
            raise
        return receipt

    def get(self, upload_id: UUID) -> FileImportReceipt:
        path = self.root / "staging" / str(upload_id) / "receipt.json"
        try:
            contents = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise KeyError(upload_id) from error
        receipt = FileImportReceipt.model_validate_json(contents)
        target = self.root / "ready" / receipt.source_id / f"{receipt.checksum}.jsonl"
        committed = receipt.committed
        # Older receipts predate per-upload confirmation. Only the very file
        # published by that upload is evidence of its own confirmation.
        if not committed:
            with suppress(FileNotFoundError):
                committed = target.samefile(path.parent / "messages.jsonl")
        return receipt.model_copy(update={"committed": committed})

    def commit(self, upload_id: UUID) -> FileImportReceipt:
        with self._lock(upload_id):
            receipt = self.get(upload_id)
            if receipt.committed:
                return receipt
            target = self.root / "ready" / receipt.source_id
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory = self.root / "staging" / str(upload_id)
            with suppress(FileExistsError):
                os.link(directory / "messages.jsonl", target / f"{receipt.checksum}.jsonl")
            receipt = receipt.model_copy(update={"committed": True})
            temporary = directory / "receipt.pending.json"
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    output.write(receipt.model_dump_json())
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, directory / "receipt.json")
            finally:
                temporary.unlink(missing_ok=True)
            return receipt

    def discard(self, upload_id: UUID) -> None:
        with self._lock(upload_id):
            receipt = self.get(upload_id)
            if receipt.committed:
                raise ValueError("import_file_already_committed")
            shutil.rmtree(self.root / "staging" / str(upload_id))

    def _lock(self, upload_id: UUID) -> FileLock:
        directory = self.root / "locks"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return FileLock(directory / f"{upload_id}.lock", timeout=5, mode=0o600)


def file_import_router(dependencies: Sequence[Depends]) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/import-files", tags=["file-imports"], dependencies=dependencies
    )

    def store(request: Request) -> FileImportStore:
        if not request.app.state.settings.imports_enabled:
            raise HTTPException(409, "imports_disabled")
        return cast(FileImportStore, request.app.state.file_import_store)

    @router.post("", response_model=FileImportReceipt | FileImportOperationReceipt, status_code=201)
    async def upload(
        request: Request,
        filename: str,
        response: Response,
        input_kind: EvidenceContentKind = EvidenceContentKind.RAW_CONVERSATION,
        operation_id: str | None = None,
    ) -> FileImportReceipt | FileImportOperationReceipt | JSONResponse:
        files = store(request)
        response.headers["Cache-Control"] = "no-store"
        if operation_id is not None:
            try:
                _operation_id(operation_id)
            except ValueError:
                raise HTTPException(422, "invalid_import_operation_id") from None
        if (
            len(filename) > 200
            or "/" in filename
            or "\\" in filename
            or not filename.lower().endswith((".zip", ".json", ".md", ".txt"))
        ):
            raise HTTPException(422, "unsupported_export_filename")
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "export_size_exceeded")
            payload.extend(chunk)
        try:
            if operation_id is None:
                return await asyncio.to_thread(
                    files.prepare, bytes(payload), filename, input_kind=input_kind
                )
            return await asyncio.to_thread(
                files.prepare,
                bytes(payload),
                filename,
                input_kind=input_kind,
                operation_id=operation_id,
            )
        except FileImportOperationConflict:
            raise HTTPException(409, "import_upload_operation_conflict") from None
        except FileImportOperationUnavailable:
            raise HTTPException(503, "import_upload_operation_unavailable") from None
        except ManualTranscriptError as error:
            return JSONResponse(
                status_code=422, content={"detail": "generic_import_invalid", "issue": error.issue}
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.get("/operations/{operation_id}", response_model=FileImportOperationReceipt)
    def lookup_operation(
        operation_id: str, request: Request, response: Response
    ) -> FileImportOperationReceipt:
        response.headers["Cache-Control"] = "no-store"
        try:
            return store(request).lookup_operation(operation_id)
        except ValueError:
            raise HTTPException(422, "invalid_import_operation_id") from None
        except FileImportOperationUnavailable:
            raise HTTPException(503, "import_upload_operation_unavailable") from None

    @router.get("/{upload_id}", response_model=FileImportReceipt)
    def get(upload_id: UUID, request: Request) -> FileImportReceipt:
        try:
            return store(request).get(upload_id)
        except KeyError as error:
            raise HTTPException(404, "import_file_not_found") from error

    @router.post("/{upload_id}/commit", response_model=FileImportReceipt)
    def commit(
        upload_id: UUID, confirmation: FileImportConfirmation, request: Request
    ) -> FileImportReceipt:
        del confirmation
        try:
            files = store(request)
            receipt = files.get(upload_id)
            if receipt.committed:
                return receipt
            jobs = cast(ImportJobStore, request.app.state.import_job_store)
            # Share connect's SQLite writer boundary through publication, so an
            # earlier job cannot capture a newly confirmed file. Parsing is done.
            with jobs._connect(writing=True) as db:
                receipt = files.get(upload_id)
                if receipt.committed:
                    return receipt
                busy = db.execute(
                    "SELECT 1 FROM import_jobs WHERE source_id=? "
                    "AND status IN ('pending','running','paused','interrupted','failed') "
                    "LIMIT 1",
                    (receipt.source_id,),
                ).fetchone()
                if busy is not None:
                    raise HTTPException(409, "import_source_busy")
                return files.commit(upload_id)
        except KeyError as error:
            raise HTTPException(404, "import_file_not_found") from error
        except Timeout as error:
            raise HTTPException(503, "import_file_busy") from error

    @router.delete("/{upload_id}", status_code=204)
    def discard(upload_id: UUID, request: Request) -> None:
        try:
            store(request).discard(upload_id)
        except KeyError as error:
            raise HTTPException(404, "import_file_not_found") from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        except Timeout as error:
            raise HTTPException(503, "import_file_busy") from error

    return router
