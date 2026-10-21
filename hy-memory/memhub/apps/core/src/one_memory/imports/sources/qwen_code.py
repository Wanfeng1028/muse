import re
from pathlib import PurePosixPath

from pydantic import JsonValue

from one_memory.imports.access import (
    AuthorizedSourceFile,
    AuthorizedSourceRoot,
    safe_project_label,
)
from one_memory.imports.adapters import (
    ScanIssueCode,
    SourceCapabilities,
    SourceDescriptor,
    StorageKind,
)
from one_memory.imports.models import WrittenBy
from one_memory.imports.sources.common import (
    JsonlSourceAdapter,
    ParsedMessage,
    ParsedSkip,
    SourceRecordContext,
    followed_by_tool,
)
from one_memory.imports.sources.parsing import (
    as_record,
    first_string,
    parse_timestamp,
    strip_host_wrappers,
    text_content,
    tool_blocks_evidence,
)

QWEN_CODE_DESCRIPTOR = SourceDescriptor(
    source_id="qwen-code",
    display_name="Qwen Code",
    storage_kinds=frozenset({StorageKind.JSONL}),
    capabilities=SourceCapabilities(
        can_append=True,
        can_observe_edits=True,
        # Qwen Code deletes a transcript when the user clears a session, but it
        # leaves nothing behind saying so, and the set it keeps is per project
        # rather than complete. So: new turns are followed, disappearances are
        # not inferred.
        can_observe_deletes=False,
        can_reconcile_complete_set=False,
    ),
)

# Read off the installed bundle (`@qwen-code/qwen-code@0.23.0`), not its docs:
# `defaultSessionScanner` accepts `^[0-9a-fA-F-]{32,36}\.jsonl$` under
# `<projectDir>/chats`, and `rebuildFromSessionJsonl` reads the same directory
# while excluding `*.ledger.jsonl`.
_SESSION_FILE = re.compile(r"^[0-9a-fA-F-]{32,36}\.jsonl$")


def is_qwen_code_transcript(source_file: AuthorizedSourceFile) -> bool:
    """A session transcript, not one of the files sitting beside it.

    `chats/` also holds `<id>.ledger.jsonl` (usage accounting) and the JSON
    sidecars `<id>.runtime.json`, `.worktree.json` and `.pr.json`. Only the
    bare `<sessionId>.jsonl` is the conversation, and matching the session-id
    shape rather than "ends with .jsonl" is what keeps the ledger out.
    """
    name = source_file.relative_path.name
    if name.endswith(".ledger.jsonl"):
        return False
    return _SESSION_FILE.match(name) is not None


def create_qwen_code_adapter(
    grant: AuthorizedSourceRoot,
    *,
    descriptor: SourceDescriptor = QWEN_CODE_DESCRIPTOR,
    source_version: str | None = None,
) -> JsonlSourceAdapter:
    return JsonlSourceAdapter(
        descriptor=descriptor,
        grant=grant,
        parser=parse_qwen_code_record,
        source_version=source_version,
        file_predicate=is_qwen_code_transcript,
    )


def parse_qwen_code_record(
    record: dict[str, JsonValue],
    context: SourceRecordContext,
) -> ParsedMessage | ParsedSkip:
    """One line of a Qwen Code transcript.

    The envelope carries `sessionId`, `cwd`, `timestamp` and `type`; the text
    is either `text` on the record or `message.content` in the stream-json
    shape. Qwen Code is a Gemini CLI fork, so the model's turns are typed
    `gemini` as often as `assistant`, and `model` appears as a role.
    """
    conversation_id = (
        first_string(record.get("sessionId"), record.get("session_id"))
        or PurePosixPath(context.relative_path).stem
    )
    message = as_record(record.get("message"))
    record_type = first_string(record.get("type"))
    role = first_string(
        message.get("role") if message else None,
        record_type,
    )
    # Telemetry and other bookkeeping share the transcript with the
    # conversation. `summarizeTranscript` reads exactly these to rebuild usage
    # totals; none of it is anyone speaking.
    if record_type == "system" or role == "system":
        return ParsedSkip(
            reason_code=ScanIssueCode.INTERNAL_REASONING_EXCLUDED,
            conversation_id=conversation_id,
        )
    # A sub-agent's turn, attributed to the tool call that started it. Keeping
    # it would put a nested agent's words in the main conversation.
    if first_string(record.get("parent_tool_use_id")) is not None or record.get("isSidechain"):
        return ParsedSkip(
            reason_code=ScanIssueCode.INTERNAL_REASONING_EXCLUDED,
            conversation_id=conversation_id,
        )
    is_agent = role in {"assistant", "gemini", "model"}
    provenance = record.get("provenance")
    if record_type in {"tool", "tool_result"}:
        # Recorded as user content with provenance `tool_result`; not the person.
        if provenance not in (None, "tool_result"):
            return ParsedSkip(
                reason_code=ScanIssueCode.TOOL_CONTENT_EXCLUDED,
                conversation_id=conversation_id,
            )
        return _tool_message(record, message, conversation_id)
    if (
        (role != "user" and not is_agent)
        or record_type in {"tool", "tool_result"}
        or (
            provenance is not None
            and provenance != ("assistant_output" if is_agent else "real_user")
        )
        or record.get("subtype") not in (None, "mid_turn_user_message")
    ):
        return ParsedSkip(
            reason_code=ScanIssueCode.TOOL_CONTENT_EXCLUDED,
            conversation_id=conversation_id,
        )
    if message and "parts" in message:
        # Native 0.23 logs include private thoughts and function responses in
        # the same parts array. Only visible text is conversation evidence.
        text = _native_visible_parts(message.get("parts"))
        if text is None and is_agent:
            return _tool_message(record, message, conversation_id)
    else:
        text = first_string(record.get("text"))
        if text is None:
            text = text_content(
                message.get("content") if message else None,
                allowed_block_types=frozenset({"text"}),
            )
    if not text:
        return ParsedSkip(
            reason_code=ScanIssueCode.NO_TEXT,
            conversation_id=conversation_id,
        )
    # A slash command the user typed is their keystrokes but not their words:
    # Qwen Code records `/model`, `/clear` and the rest as user items with
    # `sentToModel: false`. Storing them would fill the memory with commands.
    if record.get("sentToModel") is False and text.startswith("/"):
        return ParsedSkip(
            reason_code=ScanIssueCode.INTERNAL_REASONING_EXCLUDED,
            conversation_id=conversation_id,
        )
    if not is_agent:
        text = strip_host_wrappers(text)
    if not text:
        return ParsedSkip(
            reason_code=ScanIssueCode.INTERNAL_REASONING_EXCLUDED,
            conversation_id=conversation_id,
        )
    workspace = first_string(record.get("cwd"))
    return followed_by_tool(
        ParsedMessage(
            conversation_id=conversation_id,
            message_id=first_string(
                record.get("uuid"),
                record.get("id"),
                record.get("messageId"),
            ),
            role="assistant" if is_agent else "user",
            written_by=WrittenBy.AGENT if is_agent else WrittenBy.PERSON,
            created_at=parse_timestamp(record.get("timestamp")),
            verbatim=text,
            workspace=workspace,
            project=safe_project_label(workspace),
            record_type="message",
        ),
        _function_parts_text(message) if is_agent else None,
    )


def _tool_message(
    record: dict[str, JsonValue],
    message: dict[str, JsonValue] | None,
    conversation_id: str,
) -> ParsedMessage | ParsedSkip:
    text = _function_parts_text(message)
    if text is None:
        return ParsedSkip(
            reason_code=ScanIssueCode.TOOL_CONTENT_EXCLUDED,
            conversation_id=conversation_id,
        )
    workspace = first_string(record.get("cwd"))
    return ParsedMessage(
        conversation_id=conversation_id,
        message_id=first_string(record.get("uuid"), record.get("id"), record.get("messageId")),
        role="tool",
        written_by=WrittenBy.TOOL,
        created_at=parse_timestamp(record.get("timestamp")),
        verbatim=text,
        workspace=workspace,
        project=safe_project_label(workspace),
        record_type=f"{first_string(record.get('type')) or 'message'}.tool",
    )


def _function_parts_text(message: dict[str, JsonValue] | None) -> str | None:
    """`functionCall` / `functionResponse` parts, the Gemini shapes Qwen Code records."""
    blocks: list[JsonValue] = []
    parts = message.get("parts") if message else None
    for item in parts if isinstance(parts, list) else []:
        part = as_record(item) or {}
        if (call := as_record(part.get("functionCall"))) is not None:
            blocks.append({"type": "call", "name": call.get("name"), "arguments": call.get("args")})
        if (response := as_record(part.get("functionResponse"))) is not None:
            body = as_record(response.get("response")) or {}
            blocks.append(
                {
                    "type": "call",
                    "name": response.get("name"),
                    "output": body.get("output") or body.get("error") or body,
                }
            )
    return tool_blocks_evidence(blocks, block_types=frozenset({"call"}))


def _native_visible_parts(value: JsonValue | None) -> str | None:
    if not isinstance(value, list):
        return None
    visible = []
    for item in value:
        part = as_record(item)
        if part is None or part.get("thought") not in (None, False):
            continue
        if any(
            key in part for key in ("functionCall", "functionResponse", "inlineData", "fileData")
        ):
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            visible.append(text)
    return "\n".join(visible) or None
