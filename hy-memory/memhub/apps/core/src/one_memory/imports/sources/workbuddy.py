import json
import re
from collections.abc import Iterator, Mapping
from functools import partial
from xml.etree import ElementTree

from pydantic import JsonValue

from one_memory.derived_echo import strip_injected_memory
from one_memory.imports.access import (
    AuthorizedSourceFile,
    AuthorizedSourceRoot,
    SourceAccessError,
)
from one_memory.imports.adapters import (
    ScanIssueCode,
    SourceCapabilities,
    SourceDescriptor,
    StorageKind,
)
from one_memory.imports.discovery import discover_source_files
from one_memory.imports.models import WrittenBy
from one_memory.imports.sources.common import (
    JsonlSourceAdapter,
    ParsedMessage,
    ParsedSkip,
    SourceRecordContext,
)
from one_memory.imports.sources.parsing import (
    as_record,
    conversation_from_relative_path,
    first_string,
    parse_timestamp,
    text_content,
    tool_evidence_text,
    unwrap_host_envelope,
)

WORKBUDDY_DESCRIPTOR = SourceDescriptor(
    source_id="workbuddy",
    display_name="WorkBuddy",
    storage_kinds=frozenset({StorageKind.JSONL}),
    capabilities=SourceCapabilities(
        can_append=True,
        can_observe_edits=True,
        can_observe_deletes=False,
        can_reconcile_complete_set=False,
    ),
)
_AUTOMATION_REMINDER = re.compile(
    r"(?:^|[>\n])\s*<automation_system_reminder>\s*This is a scheduled automation task\."
    r"[\s\S]*?</automation_system_reminder>\s*</system[-_]reminder>\s*$"
)


def create_workbuddy_adapter(
    grant: AuthorizedSourceRoot,
    *,
    source_version: str | None = None,
) -> JsonlSourceAdapter:
    return JsonlSourceAdapter(
        descriptor=WORKBUDDY_DESCRIPTOR,
        grant=grant,
        parser=partial(
            parse_workbuddy_record,
            workspace_by_conversation=_WorkspacesFromDisk(grant),
        ),
        source_version=source_version,
    )


def parse_workbuddy_record(
    record: dict[str, JsonValue],
    context: SourceRecordContext,
    *,
    workspace_by_conversation: Mapping[str, str] | None = None,
) -> ParsedMessage | ParsedSkip:
    event_type = first_string(record.get("type")) or "message"
    nested = as_record(record.get("message"))
    provider = as_record(record.get("providerData"))
    if _is_internal(provider):
        return ParsedSkip(ScanIssueCode.INTERNAL_REASONING_EXCLUDED)
    role = _normalize_role(
        record.get("role") or (nested.get("role") if nested else None) or event_type
    )
    if role == "system":
        return ParsedSkip(ScanIssueCode.TOOL_CONTENT_EXCLUDED)
    if role == "tool" or _is_tool_event(event_type):
        return _tool_message(record, nested, event_type, context, workspace_by_conversation)
    if role not in {"user", "assistant"}:
        return ParsedSkip(ScanIssueCode.UNKNOWN_RECORD)
    content = text_content(
        record.get("content"),
        allowed_block_types=frozenset({"text", "input_text", "output_text"}),
    )
    if not content and nested:
        content = text_content(
            nested.get("content"),
            allowed_block_types=frozenset({"text", "input_text", "output_text"}),
        )
    if not content and isinstance(record.get("message"), str):
        content = text_content(
            record.get("message"),
            allowed_block_types=frozenset({"text"}),
        )
    if not content:
        return ParsedSkip(ScanIssueCode.NO_TEXT)
    conversation_id = first_string(
        record.get("sessionId"),
        record.get("conversationId"),
        record.get("threadId"),
        nested.get("sessionId") if nested else None,
        nested.get("conversationId") if nested else None,
    ) or conversation_from_relative_path(context.relative_path)
    if (
        provider is not None
        and provider.get("isCompacted") is True
        and content.startswith("<cb_summary>")
        and content.endswith("</cb_summary>")
    ):
        # Historical projections carry the replay's ID/time, not the originals'.
        return ParsedSkip(ScanIssueCode.INTERNAL_REASONING_EXCLUDED, conversation_id)
    if (
        role == "user"
        and provider is not None
        and provider.get("isMeta") is True
        and content.startswith("<task-notification>")
        and "</task-notification>" in content
    ):
        return ParsedSkip(ScanIssueCode.TOOL_CONTENT_EXCLUDED, conversation_id)
    scheduled_automation = False
    if role == "user":
        envelope = unwrap_host_envelope(strip_injected_memory(content))
        content = envelope.text
        if not content:
            return ParsedSkip(ScanIssueCode.NO_TEXT)
        scheduled_automation = any(
            _is_scheduled_automation(block) for block in envelope.prefix_blocks
        )
    workspace = first_string(
        record.get("cwd"),
        record.get("workspacePath"),
        nested.get("cwd") if nested else None,
        nested.get("workspacePath") if nested else None,
    ) or (workspace_by_conversation or {}).get(conversation_id)
    user_is_agent = role == "user" and (
        "/subagents/" in f"/{context.relative_path}"
        # WorkBuddy stamps the receiving agent name on every input, including
        # human prompts. Only explicit subagent/team provenance changes author.
        or (
            provider is not None
            and (provider.get("isSubAgent") is True or provider.get("isTeamMember") is True)
        )
    )
    if role == "assistant" or user_is_agent:
        written_by = WrittenBy.AGENT
    elif scheduled_automation or (provider is not None and provider.get("isMeta") is True):
        # An unattended invocation does not establish who wrote its saved prompt.
        # Unrecognized meta records likewise do not prove human or agent authorship.
        written_by = WrittenBy.UNKNOWN
    else:
        written_by = WrittenBy.PERSON
    record_type = event_type
    if scheduled_automation:
        record_type += ".scheduled_automation"
    return ParsedMessage(
        conversation_id=conversation_id,
        message_id=first_string(
            record.get("id"),
            record.get("uuid"),
            record.get("messageId"),
            nested.get("id") if nested else None,
        ),
        role=role,
        written_by=written_by,
        created_at=parse_timestamp(
            record.get("timestamp")
            or record.get("createdAt")
            or record.get("updatedAt")
            or (nested.get("timestamp") if nested else None)
        ),
        verbatim=content,
        workspace=workspace,
        record_type=record_type,
    )


def _tool_message(
    record: dict[str, JsonValue],
    nested: dict[str, JsonValue] | None,
    event_type: str,
    context: SourceRecordContext,
    workspace_by_conversation: Mapping[str, str] | None,
) -> ParsedMessage | ParsedSkip:
    text = tool_evidence_text({**(nested or {}), **record})
    if text is None:
        return ParsedSkip(ScanIssueCode.TOOL_CONTENT_EXCLUDED)
    conversation_id = first_string(
        record.get("sessionId"),
        record.get("conversationId"),
        record.get("threadId"),
        nested.get("sessionId") if nested else None,
        nested.get("conversationId") if nested else None,
    ) or conversation_from_relative_path(context.relative_path)
    return ParsedMessage(
        conversation_id=conversation_id,
        message_id=first_string(
            record.get("id"),
            record.get("uuid"),
            record.get("callId"),
            record.get("call_id"),
            nested.get("id") if nested else None,
        ),
        role="tool",
        written_by=WrittenBy.TOOL,
        created_at=parse_timestamp(
            record.get("timestamp")
            or record.get("createdAt")
            or (nested.get("timestamp") if nested else None)
        ),
        verbatim=text,
        workspace=first_string(record.get("cwd"), record.get("workspacePath"))
        or (workspace_by_conversation or {}).get(conversation_id),
        record_type=event_type,
    )


def _is_scheduled_automation(block: str) -> bool:
    # Parse only the validated opening tag; the host body is text, not XML.
    opening = block.partition(">")[0]
    try:
        context = ElementTree.fromstring(f"{opening}/>")
    except ElementTree.ParseError:
        return False
    return (
        context.tag in {"system-reminder", "system_reminder"}
        and context.get("data-role") == "user-context"
        and _AUTOMATION_REMINDER.search(block) is not None
    )


def _normalize_role(value: JsonValue | None) -> str | None:
    if value in {"user", "human"}:
        return "user"
    if value in {"assistant", "ai"}:
        return "assistant"
    if value in {"tool", "function"}:
        return "tool"
    if value in {"system", "developer"}:
        return "system"
    return None


def _is_internal(provider: dict[str, JsonValue] | None) -> bool:
    if provider is None:
        return False
    teammate = as_record(provider.get("teammateMessage"))
    return (
        provider.get("skipRun") is True
        or provider.get("isCompactInternal") is True
        or provider.get("agent") == "compact"
        or (teammate is not None and first_string(teammate.get("from")) is not None)
    )


def _is_tool_event(event_type: str) -> bool:
    return event_type in {
        "function_call",
        "function_call_input",
        "function_call_result",
        "function_call_output",
        "tool_call",
        "tool_result",
        "custom_tool_call",
        "custom_tool_call_output",
    }


class _WorkspacesFromDisk(Mapping[str, str]):
    """Which project each conversation belongs to, read when first asked.

    Building this walks the host's whole data directory. The adapter is put
    together on the event loop, and building it there froze everything else
    for the length of the walk. Parsing runs in a reader thread, so waiting
    until a record actually asks moves the walk there.
    """

    def __init__(self, grant: AuthorizedSourceRoot) -> None:
        self._grant = grant
        self._index: dict[str, str] | None = None

    def _resolve(self) -> dict[str, str]:
        if self._index is None:
            self._index = _workspace_by_conversation(self._grant)
        return self._index

    def __getitem__(self, conversation_id: str) -> str:
        return self._resolve()[conversation_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._resolve())


def _workspace_by_conversation(grant: AuthorizedSourceRoot) -> dict[str, str]:
    workspaces: dict[str, str] = {}
    for discovered in discover_source_files(
        grant,
        suffixes=frozenset({".json"}),
        max_targets=100_000,
    ):
        if not isinstance(discovered, AuthorizedSourceFile):
            continue
        if not discovered.relative_path.name.endswith(".meta.json"):
            continue
        try:
            with discovered.open_binary() as source:
                metadata = json.load(source)
        except (SourceAccessError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(metadata, dict):
            continue
        conversation_id = first_string(
            metadata.get("sourceConversationId"),
            metadata.get("conversationId"),
            discovered.relative_path.name.removesuffix(".meta.json"),
        )
        workspace = first_string(metadata.get("cwd"), metadata.get("workspacePath"))
        if conversation_id and workspace:
            workspaces[conversation_id] = workspace
    return workspaces
