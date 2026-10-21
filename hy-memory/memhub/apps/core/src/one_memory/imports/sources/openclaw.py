import asyncio
import hashlib
import sqlite3
from collections.abc import AsyncIterator, Iterator
from functools import partial

from one_memory.imports.access import (
    AuthorizedSourceFile,
    AuthorizedSourceRoot,
    SourceAccessError,
    SourceAccessErrorCode,
)
from one_memory.imports.adapters import (
    ScanCursorTouch,
    ScanEvent,
    ScanFailure,
    ScanIssueCode,
    ScannedEvidence,
    ScanOptions,
    ScanPhase,
    ScanProgressEvent,
    ScanSkip,
    SourceCapabilities,
    SourceDescriptor,
    StorageKind,
)
from one_memory.imports.async_bridge import iterate_in_worker
from one_memory.imports.discovery import (
    discovered_off_loop,
)
from one_memory.imports.models import WrittenBy
from one_memory.imports.sources.common import (
    ParsedMessage,
    SourceListing,
    discovery_failure_code,
    list_changed_files,
    resume_checkpoint,
    source_cursor,
    to_evidence,
    touched_cursor,
)
from one_memory.imports.sources.parsing import parse_timestamp, tool_evidence_text
from one_memory.imports.sqlite_access import open_sqlite_readonly

OPENCLAW_DESCRIPTOR = SourceDescriptor(
    source_id="openclaw",
    display_name="OpenClaw",
    storage_kinds=frozenset({StorageKind.SQLITE}),
    capabilities=SourceCapabilities(
        can_append=True,
        can_observe_edits=False,
        can_observe_deletes=False,
        can_reconcile_complete_set=False,
    ),
)


class OpenClawSourceAdapter:
    def __init__(
        self,
        descriptor: SourceDescriptor,
        grant: AuthorizedSourceRoot,
        *,
        source_version: str | None = None,
    ) -> None:
        self._descriptor = descriptor
        self.grant = grant
        self.source_version = source_version

    @property
    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    async def detect(self) -> bool:
        async for item in discovered_off_loop(
            self.grant,
            suffixes=frozenset({".db", ".sqlite", ".sqlite3"}),
            max_targets=10_000,
        ):
            if isinstance(item, AuthorizedSourceFile):
                return True
        return False

    async def has_changes(self, options: ScanOptions) -> bool:
        listing = await asyncio.to_thread(self._changed_files, options)
        return bool(listing.changed or listing.failures)

    def _changed_files(self, options: ScanOptions) -> SourceListing:
        return list_changed_files(
            self.grant,
            suffixes=frozenset({".db", ".sqlite", ".sqlite3"}),
            max_targets=options.max_scan_targets or 100_000,
            predicate=lambda source_file: not _is_persistently_skipped(source_file, options),
            cursors=options.cursors,
        )

    async def scan(self, options: ScanOptions) -> AsyncIterator[ScanEvent]:
        emitted = 0
        listing = await asyncio.to_thread(self._changed_files, options)
        for failure in listing.failures:
            yield ScanProgressEvent(
                phase=ScanPhase.DISCOVER,
                discovered_increment=1,
            )
            yield ScanFailure(reason_code=discovery_failure_code(failure))
        for source_file in listing.changed:
            yield ScanProgressEvent(
                phase=ScanPhase.DISCOVER,
                discovered_increment=1,
            )
            try:
                async for event in iterate_in_worker(
                    partial(
                        _read_conversation_db,
                        source_file,
                        options,
                        self.descriptor.source_id,
                        self.source_version,
                    ),
                    scope_key=self.descriptor.source_id,
                ):
                    yield event
                    if isinstance(event, ScannedEvidence):
                        emitted += 1
                        if options.max_messages is not None and emitted >= options.max_messages:
                            return
            except sqlite3.Error:
                yield ScanFailure(reason_code=ScanIssueCode.SOURCE_BUSY)
        yield ScanProgressEvent(phase=ScanPhase.DONE)


def create_openclaw_adapter(
    grant: AuthorizedSourceRoot,
    *,
    source_version: str | None = None,
) -> OpenClawSourceAdapter:
    # OpenClaw is registered for catalog stability but explicitly paused
    # pending a product decision. Fail closed here as well as in location
    # inspection: an authorize/connect path that already has a grant must not
    # be able to instantiate a reader and probe the host behind the pause.
    raise SourceAccessError(SourceAccessErrorCode.GRANT_REQUIRED)
    return OpenClawSourceAdapter(
        descriptor=OPENCLAW_DESCRIPTOR,
        grant=grant,
        source_version=source_version,
    )


def _read_conversation_db(
    source_file: AuthorizedSourceFile,
    options: ScanOptions,
    source_id: str,
    source_version: str | None,
) -> Iterator[ScanEvent]:
    checkpoint = resume_checkpoint(source_file, options)
    last_rowid = _row_checkpoint(checkpoint)
    previous = options.cursors.get(source_file.safe_id)
    with open_sqlite_readonly(source_file) as connection:
        if not (
            _has_columns(
                connection,
                "messages",
                {"id", "conversation_id", "role", "content", "created_at"},
            )
            and _has_columns(
                connection,
                "conversations",
                {"id", "workspace_path", "git_root"},
            )
        ):
            # OpenClaw's own state database is orchestration bookkeeping, not a
            # transcript store, and it is usually the only database an
            # installation has. Counting every such file as a failure made a
            # healthy app look broken (reported as "导入有异常" with zero
            # conversations), so a file without the conversation tables is
            # recorded as a skip instead: nothing was lost, there was simply
            # no conversation there to read.
            yield ScanSkip(
                cursor=source_cursor(source_file, "schema:none").model_copy(
                    update={"read_to_end": True}
                ),
                conversation_id=None,
                reason_code=ScanIssueCode.UNSUPPORTED_SCHEMA,
            )
            return
        last_rowid = _validated_row_checkpoint(
            connection,
            last_rowid=last_rowid,
            checkpoint_anchor=(previous.checkpoint_anchor if previous is not None else None),
        )
        rows = connection.execute(
            """
            SELECT m.rowid AS source_rowid, m.id, m.conversation_id,
                   m.role, m.content, m.created_at,
                   c.workspace_path
            FROM messages m
            LEFT JOIN conversations c ON c.id = m.conversation_id
            WHERE m.rowid > ? AND m.role IN ('user', 'assistant', 'tool')
            ORDER BY m.rowid
            """,
            (last_rowid,),
        )
        last = None
        for row in rows:
            rowid = int(row["source_rowid"])
            cursor = source_cursor(
                source_file,
                f"row:{rowid}",
                checkpoint_anchor=_checkpoint_anchor(str(row["id"])),
            )
            last = cursor
            role = str(row["role"])
            conversation_id = str(row["conversation_id"])
            # The table has no tool-name column; the body is all there is.
            tool_text = tool_evidence_text({"content": row["content"]}) if role == "tool" else None
            if role == "tool" and tool_text is None:
                yield ScanSkip(
                    cursor=cursor,
                    conversation_id=conversation_id,
                    reason_code=ScanIssueCode.TOOL_CONTENT_EXCLUDED,
                )
                continue
            if role not in {"user", "assistant", "tool"}:
                yield ScanSkip(
                    cursor=cursor,
                    conversation_id=conversation_id,
                    reason_code=ScanIssueCode.INTERNAL_REASONING_EXCLUDED,
                )
                continue
            content = str(row["content"] or "").strip()
            if not content:
                yield ScanSkip(
                    cursor=cursor,
                    conversation_id=conversation_id,
                    reason_code=ScanIssueCode.NO_TEXT,
                )
                continue
            workspace = row["workspace_path"] if isinstance(row["workspace_path"], str) else None
            parsed = ParsedMessage(
                conversation_id=conversation_id,
                message_id=str(row["id"]),
                role=role,
                written_by={
                    "user": WrittenBy.UNKNOWN,
                    "assistant": WrittenBy.AGENT,
                    "tool": WrittenBy.TOOL,
                }[role],
                created_at=parse_timestamp(row["created_at"]),
                verbatim=tool_text or content,
                workspace=workspace,
                record_type="conversation_message",
            )
            yield ScannedEvidence(
                cursor=cursor,
                evidence=to_evidence(
                    source_id=source_id,
                    source_file=source_file,
                    parsed=parsed,
                    ordinal=f"{source_file.safe_id}:row:{rowid}",
                    source_version=source_version,
                ),
            )
        yield ScanCursorTouch(
            cursor=touched_cursor(
                source_file,
                options,
                last=last,
                empty_checkpoint="row:0",
            )
        )


def _is_persistently_skipped(
    source_file: AuthorizedSourceFile,
    options: ScanOptions,
) -> bool:
    previous = options.cursors.get(source_file.safe_id)
    return bool(
        previous is not None
        and previous.checkpoint == "schema:none"
        and previous.file_identity == source_file.file_identity
    )


def _row_checkpoint(checkpoint: str | None) -> int:
    if checkpoint is None or not checkpoint.startswith("row:"):
        return 0
    try:
        return max(0, int(checkpoint.removeprefix("row:")))
    except ValueError:
        return 0


def _validated_row_checkpoint(
    connection: sqlite3.Connection,
    *,
    last_rowid: int,
    checkpoint_anchor: str | None,
) -> int:
    if last_rowid == 0:
        return 0
    row = connection.execute(
        "SELECT id FROM messages WHERE rowid = ?",
        (last_rowid,),
    ).fetchone()
    if (
        row is None
        or checkpoint_anchor is None
        or _checkpoint_anchor(str(row["id"])) != checkpoint_anchor
    ):
        return 0
    return last_rowid


def _checkpoint_anchor(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _has_columns(
    connection: sqlite3.Connection,
    table: str,
    required: set[str],
) -> bool:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if exists is None:
        return False
    columns = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
    return required.issubset(columns)
