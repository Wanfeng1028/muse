"""Read explicit user-supplied role markers, never infer authors or message times."""

import hashlib
import re
from datetime import datetime

from one_memory.imports.models import MAX_VERBATIM_CHARACTERS, WrittenBy
from one_memory.imports.sources.common import ParsedMessage

ROLES = {
    "user": "user",
    "human": "user",
    "用户": "user",
    "assistant": "assistant",
    "助手": "assistant",
}
MARKER = re.compile(
    r"^(?:#{1,6}[ \t]+)?(user|human|assistant|用户|助手)[ \t]*[:：][ \t]?(.*)$"
    r"|^#{1,6}[ \t]+(user|human|assistant|用户|助手)[ \t]*$",
    re.IGNORECASE,
)
UNSUPPORTED = re.compile(
    r"^(?:#{1,6}[ \t]+)?(?:system|tool|developer|系统|工具)[ \t]*(?:[:：]|$)", re.IGNORECASE
)


class ManualTranscriptError(ValueError):
    def __init__(self, code: str, location: str, excerpt: str) -> None:
        super().__init__("generic_import_invalid")
        self.issue = {"code": code, "location": location, "excerpt": excerpt[:200]}


def _message(
    role: object,
    content: object,
    time: object,
    identity: str,
    ordinal: int,
    location: str,
    title: str | None = None,
) -> ParsedMessage:
    excerpt = content if isinstance(content, str) else ""
    if role not in ("user", "assistant"):
        raise ManualTranscriptError("unknown_role", location, excerpt)
    if not isinstance(content, str) or not content.strip():
        raise ManualTranscriptError("empty_message", location, excerpt)
    if len(content) > MAX_VERBATIM_CHARACTERS:
        raise ManualTranscriptError("message_too_long", location, excerpt)
    created = None
    if time is not None:
        try:
            if not isinstance(time, str):
                raise ValueError
            created = datetime.fromisoformat(time.replace("Z", "+00:00"))
            if created.utcoffset() is None:
                raise ValueError
        except ValueError:
            raise ManualTranscriptError("invalid_time", location, str(time)) from None
    return ParsedMessage(
        conversation_id=identity,
        message_id=str(ordinal),
        role=role,
        written_by=WrittenBy.PERSON if role == "user" else WrittenBy.AGENT,
        verbatim=content,
        created_at=created,
        project=title,
        record_type="manual_transcript",
    )


def parse_manual_json(data: list[object], identity: str) -> list[ParsedMessage]:
    messages = []
    for index, value in enumerate(data, 1):
        location = f"message:{index}"
        if not isinstance(value, dict) or set(value) - {"role", "content", "time"}:
            raise ManualTranscriptError("invalid_record", location, str(value))
        messages.append(
            _message(
                value.get("role"),
                value.get("content"),
                value.get("time"),
                identity,
                index,
                location,
            )
        )
    return messages


def parse_marked_text(text: str) -> list[ParsedMessage]:
    identity = "manual:" + hashlib.sha256(text.encode()).hexdigest()
    messages: list[ParsedMessage] = []
    role, title, start = None, None, 1
    content: list[str] = []
    fence: tuple[str, int] | None = None

    def finish() -> None:
        if role is not None:
            messages.append(
                _message(
                    role,
                    "".join(content).strip("\r\n"),
                    None,
                    identity,
                    len(messages) + 1,
                    f"line:{start}",
                    title,
                )
            )

    for number, line in enumerate(text.splitlines(keepends=True), 1):
        plain = line.rstrip("\r\n")
        if fence is not None:
            content.append(line)
            if re.fullmatch(
                r"[ \t]{0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}[ \t]*", plain
            ):
                fence = None
            continue
        marker = MARKER.fullmatch(plain)
        if marker:
            finish()
            role = ROLES[(marker[1] or marker[3]).lower()]
            start, content = number, []
            if marker[1] and marker[2]:
                content.append(marker[2] + ("\n" if line.endswith("\n") else ""))
            continue
        if UNSUPPORTED.match(plain):
            raise ManualTranscriptError("unknown_role", f"line:{number}", plain)
        if role is None:
            if not plain.strip():
                continue
            if plain.startswith("# ") and title is None:
                title = plain[2:].strip()
                continue
            raise ManualTranscriptError("missing_role", f"line:{number}", plain)
        opening = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", plain)
        if opening:
            fence = (opening[1][0], len(opening[1]))
        content.append(line)
    if fence:
        raise ManualTranscriptError("unclosed_code", f"line:{start}", "".join(content))
    finish()
    if not messages:
        raise ManualTranscriptError("missing_role", "line:1", text)
    return messages
