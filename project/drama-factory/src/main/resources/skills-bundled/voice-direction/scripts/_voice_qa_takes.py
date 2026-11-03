"""Resolve each take's intended text, voice and language for voice_qa.py (meta.json, alignment JSON, script, --text)."""
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from pydantic import BaseModel, TypeAdapter


class ScriptEntry(BaseModel):
    id: str
    text: str | None = None
    forms: list[str] = []


@dataclass(frozen=True)
class Take:
    path: Path
    name: str
    voice: str
    text: str | None
    language: str | None


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def load_script(path: Path | None) -> list[ScriptEntry]:
    if not path:
        return []
    return TypeAdapter(list[ScriptEntry]).validate_json(path.read_text())


def match_script(stem: str, entries: list[ScriptEntry], prefix: str) -> tuple[ScriptEntry | None, str]:
    for entry in sorted(entries, key=lambda item: len(item.id), reverse=True):
        found = re.fullmatch(rf"(.*?){re.escape(entry.id)}[a-z]{{0,2}}", stem)
        if found and found.group(1).startswith(prefix):
            return entry, found.group(1)
    return None, ""


def voice_group(path: Path, meta: dict, take_prefix: str, group_by: str) -> str:
    if group_by == "none":
        return "all"
    if group_by == "folder":
        return path.parent.name
    if group_by == "prefix":
        found = re.match(r"(.+?)[-_]", path.stem)
        return found.group(1) if found else path.parent.name
    return meta.get("voice_id") or take_prefix.rstrip("-_ ") or path.parent.name


def resolve_take(path: Path, entries: list[ScriptEntry], prefix: str, text: str | None, group_by: str) -> Take:
    meta = _read_json(path.with_suffix(".meta.json"))
    alignment = _read_json(path.with_suffix(".json"))
    entry, take_prefix = match_script(path.stem, entries, prefix)
    script_text = (entry.text or (entry.forms[0] if entry.forms else None)) if entry else None
    intended = text or meta.get("line_text") or meta.get("text") or alignment.get("text") or script_text
    return Take(path, path.stem, voice_group(path, meta, take_prefix, group_by), intended, meta.get("language"))


def resolve_takes(paths: list[Path], script: Path | None, prefix: str, text: str | None, group_by: str) -> list[Take]:
    entries = load_script(script)
    takes = [resolve_take(path, entries, prefix, text, group_by) for path in paths]
    stems = [take.name for take in takes]
    return [replace(take, name=f"{take.path.parent.name}/{take.name}") if stems.count(take.name) > 1 else take for take in takes]
