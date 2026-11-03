import asyncio
import hashlib
import heapq
import json
import os
import sqlite3
import sys
from collections.abc import AsyncIterator, Iterator, Mapping
from functools import partial
from pathlib import Path

from pydantic import JsonValue

from one_memory.imports.access import (
    AuthorizedSourceFile,
    AuthorizedSourceRoot,
    SourceAccessError,
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
    SourceFileDiscoveryFailure,
    discovered_off_loop,
)
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.sources.common import (
    STOP_SCAN_ACCESS_CODES,
    discovery_failure_code,
    resume_checkpoint,
    source_cursor,
    touched_cursor,
)
from one_memory.imports.sources.parsing import is_host_generated_user_turn, parse_timestamp
from one_memory.imports.sqlite_access import open_sqlite_readonly

CURSOR_DESCRIPTOR = SourceDescriptor(
    source_id="cursor",
    display_name="Cursor",
    storage_kinds=frozenset({StorageKind.SQLITE}),
    capabilities=SourceCapabilities(
        can_append=True,
        can_observe_edits=False,
        can_observe_deletes=False,
        can_reconcile_complete_set=False,
    ),
)


class CursorSourceAdapter:
    def __init__(
        self,
        *,
        grant: AuthorizedSourceRoot,
        source_version: str | None = None,
    ) -> None:
        if grant.source_id != CURSOR_DESCRIPTOR.source_id:
            raise ValueError("Cursor grant must use the cursor source ID")
        self.grant = grant
        self.source_version = source_version

    @property
    def descriptor(self) -> SourceDescriptor:
        return CURSOR_DESCRIPTOR

    async def detect(self) -> bool:
        async for event in discovered_off_loop(
            self.grant,
            suffixes=frozenset({".vscdb"}),
            max_targets=10_000,
        ):
            if (
                isinstance(event, AuthorizedSourceFile)
                and event.relative_path.name == "state.vscdb"
            ):
                return True
        return False

    async def read_listed(
        self, files: list[AuthorizedSourceFile], options: ScanOptions
    ) -> AsyncIterator[ScanEvent]:
        """Read rows after each database's cursor; the caller listed and filtered them."""
        emitted = 0
        for listed in files:
            try:
                discovered = await asyncio.to_thread(listed.admit)
            except SourceAccessError as error:
                if error.code in STOP_SCAN_ACCESS_CODES:
                    raise
                continue
            previous = options.cursors.get(discovered.safe_id)
            last_rowid = _row_checkpoint(resume_checkpoint(discovered, options))
            cursor = None
            try:
                async for message in iterate_in_worker(
                    partial(
                        _read_cursor_messages,
                        discovered,
                        last_rowid=last_rowid,
                        checkpoint_anchor=(
                            previous.checkpoint_anchor if previous is not None else None
                        ),
                    ),
                    scope_key=self.descriptor.source_id,
                ):
                    cursor = source_cursor(
                        discovered,
                        f"row:{message.source_rowid}",
                        checkpoint_anchor=_checkpoint_anchor(message.source_key),
                    )
                    if message.text is None:
                        yield ScanSkip(cursor=cursor, reason_code=ScanIssueCode.NO_TEXT)
                        continue
                    yield ScannedEvidence(
                        cursor=cursor, evidence=self._evidence(discovered, message)
                    )
                    emitted += 1
                    if options.max_messages is not None and emitted >= options.max_messages:
                        return
            except sqlite3.Error:
                yield ScanFailure(cursor=cursor, reason_code=ScanIssueCode.SOURCE_BUSY)
                continue
            except SourceAccessError as error:
                if error.code in STOP_SCAN_ACCESS_CODES:
                    raise
                continue
            yield ScanCursorTouch(
                cursor=touched_cursor(discovered, options, last=cursor, empty_checkpoint="row:0")
            )

    def _evidence(
        self, discovered: AuthorizedSourceFile, message: "_CursorMessage"
    ) -> EvidenceInput:
        written_by = (
            WrittenBy.AGENT
            if (
                message.role == "assistant"
                or message.is_subagent is True
                or is_host_generated_user_turn(message.text or "")
            )
            else WrittenBy.PERSON
        )
        return EvidenceInput(
            source_id=self.descriptor.source_id,
            conversation_id=message.conversation_id,
            message_id=message.message_id,
            role=message.role,
            written_by=written_by,
            created_at=parse_timestamp(message.created_at),
            verbatim=message.text or "",
            workspace=message.workspace,
            origin_meta={
                EvidenceOrigin.FILE: OriginMetadata(
                    source_version=self.source_version,
                    raw_meta={"file_key": discovered.safe_id, "channel": "vscdb"},
                )
            },
        )

    async def scan(self, options: ScanOptions) -> AsyncIterator[ScanEvent]:
        emitted = 0
        async for discovered in discovered_off_loop(
            self.grant,
            suffixes=frozenset({".vscdb"}),
            max_targets=options.max_scan_targets or 10_000,
        ):
            if isinstance(discovered, SourceFileDiscoveryFailure):
                yield ScanFailure(reason_code=discovery_failure_code(discovered))
                continue
            if discovered.relative_path.name != "state.vscdb":
                continue
            yield ScanProgressEvent(
                phase=ScanPhase.DISCOVER,
                discovered_increment=1,
            )
            previous = options.cursors.get(discovered.safe_id)
            last_rowid = _row_checkpoint(resume_checkpoint(discovered, options))
            try:
                async for message in iterate_in_worker(
                    partial(
                        _read_cursor_messages,
                        discovered,
                        last_rowid=last_rowid,
                        checkpoint_anchor=(
                            previous.checkpoint_anchor if previous is not None else None
                        ),
                    ),
                    scope_key=self.descriptor.source_id,
                ):
                    cursor = source_cursor(
                        discovered,
                        f"row:{message.source_rowid}",
                        checkpoint_anchor=_checkpoint_anchor(message.source_key),
                    )
                    if message.text is None:
                        yield ScanSkip(
                            cursor=cursor,
                            reason_code=ScanIssueCode.NO_TEXT,
                        )
                        continue
                    yield ScannedEvidence(
                        cursor=cursor,
                        evidence=self._evidence(discovered, message),
                    )
                    emitted += 1
                    if options.max_messages is not None and emitted >= options.max_messages:
                        return
            except sqlite3.Error:
                yield ScanFailure(
                    cursor=cursor,
                    reason_code=ScanIssueCode.SOURCE_BUSY,
                )
        yield ScanProgressEvent(phase=ScanPhase.DONE)


class _CursorMessage:
    def __init__(
        self,
        *,
        conversation_id: str,
        message_id: str,
        role: str,
        text: str | None,
        created_at: JsonValue | None,
        is_subagent: bool | None,
        workspace: str | None,
        source_rowid: int,
        source_key: str,
    ) -> None:
        self.conversation_id = conversation_id
        self.message_id = message_id
        self.role = role
        self.text = text
        self.created_at = created_at
        self.is_subagent = is_subagent
        self.workspace = workspace
        self.source_rowid = source_rowid
        self.source_key = source_key


def _read_cursor_messages(
    source_file: AuthorizedSourceFile,
    *,
    last_rowid: int,
    checkpoint_anchor: str | None,
) -> Iterator[_CursorMessage]:
    with open_sqlite_readonly(source_file, timeout=0.1) as connection:
        connection.execute("PRAGMA busy_timeout = 100")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "cursorDiskKV" not in tables:
            return
        last_rowid = _validated_row_checkpoint(
            connection,
            last_rowid=last_rowid,
            checkpoint_anchor=checkpoint_anchor,
        )
        composer_headers = _read_composer_headers(connection, tables)
        rows = _read_bubble_rows(
            connection,
            composer_ids=tuple(composer_headers),
            last_rowid=last_rowid,
        )
        for source_rowid, key, value in rows:
            parsed_key = _parse_bubble_key(key)
            parsed_value = _parse_json_object(value)
            if parsed_key is None or parsed_value is None:
                continue
            conversation_id, fallback_message_id = parsed_key
            role = _bubble_role(parsed_value.get("type"))
            if role is None:
                continue
            text = parsed_value.get("text")
            yield _CursorMessage(
                conversation_id=conversation_id,
                message_id=_string(parsed_value.get("bubbleId")) or fallback_message_id,
                role=role,
                text=text.strip() if isinstance(text, str) and text.strip() else None,
                created_at=parsed_value.get("createdAt") or parsed_value.get("timestamp"),
                is_subagent=composer_headers.get(conversation_id, (None, None))[0],
                workspace=composer_headers.get(conversation_id, (None, None))[1],
                source_rowid=int(source_rowid),
                source_key=str(key),
            )


def _read_composer_headers(
    connection: sqlite3.Connection,
    tables: set[str],
) -> dict[str, tuple[bool | None, str | None]]:
    result: dict[str, tuple[bool | None, str | None]] = {}
    if "ItemTable" in tables:
        row = connection.execute(
            "SELECT value FROM ItemTable WHERE key = ? LIMIT 1",
            ("composer.composerHeaders",),
        ).fetchone()
        if row is None:
            row = connection.execute(
                "SELECT value FROM ItemTable WHERE key = ? LIMIT 1",
                ("composerHeaders",),
            ).fetchone()
        if row is not None:
            try:
                parsed = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                parsed = None
            candidates: list[JsonValue] = []
            if isinstance(parsed, list):
                candidates = parsed
            elif isinstance(parsed, dict) and isinstance(parsed.get("headers"), list):
                candidates = parsed["headers"]
            elif isinstance(parsed, dict) and isinstance(parsed.get("allComposers"), list):
                candidates = parsed["allComposers"]
            for composer_id, is_subagent in _composer_header_candidates(candidates).items():
                result[composer_id] = (is_subagent, None)
    if "composerHeaders" in tables:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(composerHeaders)")}
        required = {"composerId", "isSubagent"}
        if required <= columns:
            selected = ["composerId", "isSubagent"]
            selected.append("subagentTypeName" if "subagentTypeName" in columns else "NULL")
            selected.append("workspaceId" if "workspaceId" in columns else "NULL")
            rows = connection.execute(f"SELECT {', '.join(selected)} FROM composerHeaders")
            for composer_id, is_subagent, subagent_type, workspace_id in rows:
                composer = _string(composer_id)
                if not composer:
                    continue
                result[composer] = (
                    bool(is_subagent) or bool(_string(subagent_type)),
                    _string(workspace_id),
                )
    return result


def _composer_header_candidates(candidates: list[JsonValue]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        composer_id = _string(candidate.get("composerId")) or _string(candidate.get("id"))
        is_subagent = candidate.get("isSubagent")
        if not composer_id:
            continue
        if isinstance(is_subagent, bool):
            result[composer_id] = is_subagent
            continue
        result[composer_id] = bool(
            candidate.get("subagentInfo") or candidate.get("isBestOfNSubcomposer") is True
        )
    return result


def _read_bubble_rows(
    connection: sqlite3.Connection,
    *,
    composer_ids: tuple[str, ...],
    last_rowid: int,
) -> Iterator[tuple[int, str, str]]:
    if not composer_ids:
        return

    cursors = [
        connection.execute(
            """
            SELECT rowid AS source_rowid, key, value FROM cursorDiskKV
            WHERE rowid > ?
              AND key >= ? AND key < ?
              AND value IS NOT NULL
            ORDER BY rowid
            """,
            (
                last_rowid,
                f"bubbleId:{composer_id}:",
                f"bubbleId:{composer_id};",
            ),
        )
        for composer_id in composer_ids
    ]
    queue: list[tuple[int, int, str, str]] = []
    for index, cursor in enumerate(cursors):
        row = cursor.fetchone()
        if row is not None:
            heapq.heappush(queue, (int(row[0]), index, str(row[1]), str(row[2])))

    while queue:
        source_rowid, index, key, value = heapq.heappop(queue)
        yield source_rowid, key, value
        row = cursors[index].fetchone()
        if row is not None:
            heapq.heappush(queue, (int(row[0]), index, str(row[1]), str(row[2])))


def _parse_bubble_key(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != "bubbleId" or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def _parse_json_object(value: object) -> dict[str, JsonValue] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _bubble_role(value: JsonValue | None) -> str | None:
    if value == 1:
        return "user"
    if value == 2:
        return "assistant"
    return None


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None


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
        "SELECT key FROM cursorDiskKV WHERE rowid = ?",
        (last_rowid,),
    ).fetchone()
    if (
        row is None
        or checkpoint_anchor is None
        or _checkpoint_anchor(str(row["key"])) != checkpoint_anchor
    ):
        return 0
    return last_rowid


def _checkpoint_anchor(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cursor_default_root(
    home: Path,
    *,
    platform: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Cursor's legacy data root when `~/.cursor` is absent.

    The modern install writes under `~/.cursor`; this is only the fallback for
    an older layout. It used to hard-code the macOS Library path, so on Windows
    the catalog would point at a directory that never exists. The platform
    branches match `_cursor_data_root` in the registry — one opinion, two callers.
    """
    current = platform or sys.platform
    env = environment if environment is not None else os.environ
    if current == "darwin":
        return home / "Library" / "Application Support" / "Cursor" / "User"
    if current == "win32":
        app_data = env.get("APPDATA")
        return (Path(app_data) if app_data else home / "AppData" / "Roaming") / "Cursor" / "User"
    config_home = env.get("XDG_CONFIG_HOME")
    return (Path(config_home) if config_home else home / ".config") / "Cursor" / "User"
