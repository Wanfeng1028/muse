"""Explicitly supplied memory reports, not inferred chats or vendor schemas."""

import hashlib
import json
from datetime import datetime

from one_memory.imports.chat_exports import (
    MAX_MESSAGES,
    MAX_UPLOAD_BYTES,
    ParsedExport,
    _invalid_constant,
    _unique_object,
    _validate_messages,
)
from one_memory.imports.models import EvidenceContentKind, WrittenBy
from one_memory.imports.sources.common import ParsedMessage


def parse_memory_content(payload: bytes, filename: str) -> ParsedExport:
    if not payload or len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("export_size_exceeded")
    try:
        text = payload.decode("utf-8-sig")
        if filename.lower().endswith((".txt", ".md")):
            records = [{"content": text}]
        elif filename.lower().endswith(".json"):
            data = json.loads(
                text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
            )
            if (
                not isinstance(data, dict)
                or set(data) != {"format", "memories"}
                or data["format"] != "one-memory-content-v1"
                or not isinstance(data["memories"], list)
            ):
                raise ValueError("unsupported_memory_content_schema")
            records = data["memories"]
        else:
            raise ValueError("unsupported_memory_content_schema")
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("invalid_export_json") from None
    if len(records) > MAX_MESSAGES:
        raise ValueError("export_message_limit_exceeded")
    messages = []
    identity = "memory-content:" + hashlib.sha256(payload).hexdigest()
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict) or set(record) - {"content", "author", "time"}:
            raise ValueError("invalid_memory_content_record")
        content, author = record.get("content"), record.get("author", "unknown")
        if (
            not isinstance(content, str)
            or not content.strip()
            or not isinstance(author, str)
            or author not in {"person", "agent", "unknown"}
        ):
            raise ValueError("invalid_memory_content_record")
        created = None
        if record.get("time") is not None:
            try:
                if not isinstance(record["time"], str):
                    raise ValueError
                created = datetime.fromisoformat(record["time"].replace("Z", "+00:00"))
                if created.utcoffset() is None:
                    raise ValueError
            except ValueError:
                raise ValueError("invalid_memory_content_time") from None
        messages.append(
            ParsedMessage(
                conversation_id=identity,
                message_id=str(index),
                role="memory",
                written_by=WrittenBy(author),
                verbatim=content,
                created_at=created,
                content_kind=EvidenceContentKind.MEMORY_CONTENT,
                record_type="explicit_memory_content_v1",
            )
        )
    _validate_messages(messages, "memory-content")
    return ParsedExport("memory-content", tuple(messages), 0, 0)
