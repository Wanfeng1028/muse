from pydantic import JsonValue

from one_memory.imports.access import AuthorizedSourceRoot
from one_memory.imports.adapters import SourceCapabilities, SourceDescriptor, StorageKind
from one_memory.imports.models import EvidenceContentKind, WrittenBy
from one_memory.imports.sources.common import JsonlSourceAdapter, ParsedMessage, SourceRecordContext
from one_memory.imports.sources.parsing import parse_timestamp

EXPORT_DESCRIPTORS = tuple(
    SourceDescriptor(
        source_id=f"{vendor}-export",
        display_name=(
            "手工提供的对话"
            if vendor == "generic"
            else "手工提供的已有记忆"
            if vendor == "memory-content"
            else f"{label} 历史包"
        ),
        storage_kinds=frozenset({StorageKind.JSONL}),
        capabilities=SourceCapabilities(
            can_append=False,
            can_observe_edits=False,
            can_observe_deletes=False,
            can_reconcile_complete_set=False,
        ),
    )
    for vendor, label in (
        ("chatgpt", "ChatGPT"),
        ("claude", "Claude"),
        ("generic", "手工提供"),
        ("memory-content", "已有记忆"),
    )
)


def create_export_adapter(grant: AuthorizedSourceRoot) -> JsonlSourceAdapter:
    descriptor = next(item for item in EXPORT_DESCRIPTORS if item.source_id == grant.source_id)
    return JsonlSourceAdapter(
        descriptor=descriptor,
        grant=grant,
        parser=parse_export_record,
        source_version="chat-export-v1",
    )


def parse_export_record(
    record: dict[str, JsonValue], context: SourceRecordContext
) -> ParsedMessage:
    del context
    return ParsedMessage(
        conversation_id=str(record["conversation_id"]),
        message_id=str(record["message_id"]),
        role=str(record["role"]),
        written_by=WrittenBy(str(record["written_by"])),
        verbatim=str(record["verbatim"]),
        created_at=parse_timestamp(record.get("created_at")),
        project=str(record["project"]) if record.get("project") else None,
        record_type=str(record["record_type"]),
        content_kind=EvidenceContentKind(str(record.get("content_kind", "raw_conversation"))),
    )
