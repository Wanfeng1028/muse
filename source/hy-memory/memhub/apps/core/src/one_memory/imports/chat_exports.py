"""Decode vendor conversation exports, without extracting or confirming memories."""

import hashlib
import io
import json
import tempfile
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from one_memory.imports.archive import ArchiveRejection, safe_entry_names
from one_memory.imports.manual_transcript import parse_manual_json, parse_marked_text
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.sources.common import ParsedMessage
from one_memory.imports.sources.parsing import parse_timestamp

MAX_UPLOAD_BYTES = 128 * 1024 * 1024
MAX_MESSAGES = 100_000


@dataclass(frozen=True)
class ParsedExport:
    vendor: Literal["chatgpt", "claude", "generic", "memory-content"]
    messages: tuple[ParsedMessage, ...]
    skipped_records: int
    ignored_files: int


def parse_chat_export(payload: bytes, filename: str) -> ParsedExport:
    if not payload or len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("export_size_exceeded")
    ignored = 0
    if filename.lower().endswith(".zip") or zipfile.is_zipfile(io.BytesIO(payload)):
        with tempfile.TemporaryDirectory(prefix="one-memory-export-") as directory:
            archive_path = Path(directory) / "upload.zip"
            archive_path.write_bytes(payload)
            try:
                names = safe_entry_names(
                    archive_path, max_total_bytes=MAX_UPLOAD_BYTES, max_entries=20_000
                )
                if len(names) != len(set(names)) or any(
                    "\\" in name or PureWindowsPath(name).drive for name in names
                ):
                    raise ValueError("unsafe_export_archive")
                candidates = [name for name in names if Path(name).name == "conversations.json"]
                if len(candidates) != 1:
                    raise ValueError("ambiguous_export_payload")
                with zipfile.ZipFile(archive_path) as archive:
                    payload = archive.read(candidates[0])
                ignored = len(names) - 1
            except (ArchiveRejection, zipfile.BadZipFile, RuntimeError, zlib.error) as error:
                raise ValueError("unsafe_export_archive") from error
    try:
        text = payload.decode("utf-8-sig")
        if filename.lower().endswith((".md", ".txt")) and not text.lstrip().startswith("["):
            messages = parse_marked_text(text)
            _validate_messages(messages, "generic")
            return ParsedExport("generic", tuple(messages), 0, ignored)
        data = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("invalid_export_json") from error
    if (
        isinstance(data, list)
        and data
        and any(isinstance(item, dict) and "role" in item for item in data)
    ):
        messages = parse_manual_json(data, "manual:" + hashlib.sha256(payload).hexdigest())
        _validate_messages(messages, "generic")
        return ParsedExport("generic", tuple(messages), 0, ignored)
    if not isinstance(data, list) or not data or not all(isinstance(item, dict) for item in data):
        raise ValueError("unsupported_export_schema")
    vendor: Literal["chatgpt", "claude"]
    if all(isinstance(item.get("mapping"), dict) for item in data):
        vendor, parser = "chatgpt", _chatgpt
    elif all(isinstance(item.get("chat_messages"), list) for item in data):
        vendor, parser = "claude", _claude
    else:
        raise ValueError("unsupported_export_schema")
    messages = []
    skipped = 0
    conversations: set[str] = set()
    for conversation in data:
        identity = _identifier(
            (conversation.get("id") or conversation.get("conversation_id"))
            if vendor == "chatgpt"
            else conversation.get("uuid")
        )
        if identity in conversations:
            raise ValueError("duplicate_export_identity")
        conversations.add(identity)
        parsed, omitted = parser(conversation)
        messages.extend(parsed)
        skipped += omitted
        if len(messages) > MAX_MESSAGES:
            raise ValueError("export_message_limit_exceeded")
    _validate_messages(messages, vendor)
    return ParsedExport(vendor, tuple(messages), skipped, ignored)


def _validate_messages(messages: list[ParsedMessage], vendor: str) -> None:
    if len(messages) > MAX_MESSAGES:
        raise ValueError("export_message_limit_exceeded")
    if not messages:
        raise ValueError("export_has_no_text_conversations")
    identities = set()
    for message in messages:
        message_identity = (message.conversation_id, message.message_id)
        if message_identity in identities:
            raise ValueError("duplicate_export_identity")
        identities.add(message_identity)
        try:
            value = EvidenceInput(
                source_id=f"{vendor}-export",
                conversation_id=message.conversation_id,
                message_id=message.message_id,
                role=message.role,
                written_by=message.written_by,
                content_kind=message.content_kind,
                verbatim=message.verbatim,
                created_at=message.created_at,
                project=message.project,
                origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
            )
            # Preview and the normal importer must accept the same records.
            value.model_dump_json()
        except ValueError as error:
            raise ValueError("export_record_invalid") from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("invalid_export_json")
        value[key] = item
    return value


def _invalid_constant(value: str) -> None:
    raise ValueError("invalid_export_json")


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 300:
        raise ValueError("unsupported_export_schema")
    return value


def _chatgpt(conversation: dict[str, Any]) -> tuple[list[ParsedMessage], int]:
    conversation_id = _identifier(conversation.get("id") or conversation.get("conversation_id"))
    mapping = conversation["mapping"]
    if not mapping or not all(isinstance(node, dict) for node in mapping.values()):
        raise ValueError("unsupported_export_schema")
    depths: dict[str, int] = {}
    for key in mapping:
        chain, seen = [], set()
        cursor = key
        while cursor is not None and cursor not in depths:
            if not isinstance(cursor, str) or cursor not in mapping or cursor in seen:
                raise ValueError("invalid_export_branch")
            chain.append(cursor)
            seen.add(cursor)
            cursor = mapping[cursor].get("parent")
            if cursor is not None and not isinstance(cursor, str):
                raise ValueError("invalid_export_branch")
        depth = depths.get(cursor, -1) if cursor is not None else -1
        for entry in reversed(chain):
            depth += 1
            depths[entry] = depth
    active: set[str] = set()
    current = conversation.get("current_node")
    while current is not None:
        if not isinstance(current, str) or current in active or current not in mapping:
            raise ValueError("invalid_export_branch")
        active.add(current)
        current = mapping[current].get("parent")
    messages, skipped = [], 0
    for key in sorted(mapping, key=lambda key: depths[key]):
        node = mapping[key]
        message = node.get("message")
        if message is None:
            continue
        if not isinstance(message, dict) or not isinstance(message.get("author"), dict):
            raise ValueError("unsupported_export_schema")
        role = message["author"].get("role")
        if (
            role not in ("user", "assistant")
            or message.get("channel") == "analysis"
            or message.get("recipient") not in (None, "all")
        ):
            skipped += 1
            continue
        content = message.get("content")
        if not isinstance(content, dict) or not isinstance(content.get("parts"), list):
            skipped += 1
            continue
        parts = content["parts"]
        text = "\n".join(part for part in parts if isinstance(part, str))
        if not text.strip():
            skipped += 1
            continue
        # An alternate answer must not appear as the next step of the active dialogue.
        branch = conversation_id
        if key not in active and active:
            ancestor, visited = key, set()
            while mapping[ancestor].get("parent") not in active:
                if ancestor in visited:
                    raise ValueError("invalid_export_branch")
                visited.add(ancestor)
                parent = mapping[ancestor].get("parent")
                if parent is None:
                    break
                if parent not in mapping:
                    raise ValueError("invalid_export_branch")
                ancestor = parent
            branch = (
                f"{conversation_id}:branch:{hashlib.sha256(ancestor.encode()).hexdigest()[:16]}"
            )
        messages.append(
            ParsedMessage(
                conversation_id=branch,
                message_id=_identifier(message.get("id") or key),
                role=role,
                written_by=WrittenBy.PERSON if role == "user" else WrittenBy.AGENT,
                created_at=parse_timestamp(message.get("create_time")),
                verbatim=text,
                project=conversation.get("title")
                if isinstance(conversation.get("title"), str)
                else None,
                record_type="chatgpt_export",
            )
        )
    return messages, skipped


def _claude(conversation: dict[str, Any]) -> tuple[list[ParsedMessage], int]:
    conversation_id = _identifier(conversation.get("uuid"))
    messages, skipped = [], 0
    for message in conversation["chat_messages"]:
        if not isinstance(message, dict):
            raise ValueError("unsupported_export_schema")
        sender = message.get("sender")
        if sender not in ("human", "assistant"):
            skipped += 1
            continue
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            blocks = message.get("content", [])
            text = (
                "\n".join(
                    block["text"]
                    for block in blocks
                    if isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                )
                if isinstance(blocks, list)
                else ""
            )
        if not text.strip():
            skipped += 1
            continue
        messages.append(
            ParsedMessage(
                conversation_id=conversation_id,
                message_id=_identifier(message.get("uuid")),
                role="user" if sender == "human" else "assistant",
                written_by=WrittenBy.PERSON if sender == "human" else WrittenBy.AGENT,
                created_at=parse_timestamp(message.get("created_at")),
                verbatim=text,
                project=conversation.get("name")
                if isinstance(conversation.get("name"), str)
                else None,
                record_type="claude_export",
            )
        )
    return messages, skipped
