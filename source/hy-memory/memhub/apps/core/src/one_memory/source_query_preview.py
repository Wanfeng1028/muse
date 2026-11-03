"""Conservative, deterministic display projection; never changes stored evidence."""

import json
import re

from one_memory.imports.sources.parsing import is_host_generated_user_turn, unwrap_host_envelope

_UNRESOLVED = re.compile(
    r"(?:^\[Image\]|"
    r"^# (?:AGENTS\.md instructions for|Files mentioned by the user)|"
    r"^<(?:user_query|user_info|rules|agent_transcripts|system[-_]notification|"
    r"pipeline_log|additional_data|system[-_]reminder|working_memory_reminder|"
    r"subagent_notification|codex_delegation|environment_context|image_files|"
    r"dynamic_tools|dynamic_tool_catalog|INSTRUCTIONS)(?:\s|>))",
    re.IGNORECASE,
)
_CURSOR_TIMESTAMP_PREFIX = re.compile(r"<timestamp>[\s\S]*?</timestamp>\s*")
_CURSOR_IMAGE_FILES_PREFIX = re.compile(r"\[Image\]\s*<image_files>[\s\S]*?</image_files>\s*")


def _strip_cursor_host_prefix(text: str) -> str:
    text = _CURSOR_IMAGE_FILES_PREFIX.sub("", text, count=1)
    return _CURSOR_TIMESTAMP_PREFIX.sub("", text, count=1)


def display_query_projection(text: str, role: str, author: str) -> str | None:
    """SQLite UDF returns a small JSON value, or NULL when identity is uncertain.

    Callers must apply source/user permissions and role/author before this UDF.
    Oversized or ambiguous wrappers are withheld, not rewritten or guessed.
    """
    if role != "user" or author != "person" or len(text) > 65536:
        return None
    if is_host_generated_user_turn(text):
        return None
    envelope = unwrap_host_envelope(_strip_cursor_host_prefix(text))
    query = envelope.text
    if not query or _UNRESOLVED.match(query) or is_host_generated_user_turn(query):
        return None
    # The projection must point at an exact, unambiguous substring of the original.
    start = text.find(query)
    if start < 0 or text.find(query, start + 1) >= 0:
        return None
    return json.dumps(
        {
            "excerpt": query[:600],
            "truncated": len(query) > 600,
            "query_start": start,
            "query_end": start + len(query),
            "projection_version": 1,
        },
        ensure_ascii=False,
    )
