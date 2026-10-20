"""Take planning and recording for vo_record.py: request bodies, seeds, retake-ladder slots, audio + alignment + meta files."""
import base64
import io
import json
import random
import string
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

import _voice_eleven as eleven
import _voice_text as text_tools
from _vo_record_voice import Direction

SEED_LIMIT = 4294967295


class ScriptLine(BaseModel):
    id: str
    text: str | None = None
    forms: list[str] = []
    previous: str | None = None
    next: str | None = None

    @property
    def spoken(self) -> str:
        return self.text if self.text is not None else self.forms[0]

    @property
    def ladder(self) -> list[str]:
        return self.forms or [self.spoken]


@dataclass
class Attempt:
    name: str
    line: ScriptLine
    form_index: int
    text: str
    body: dict
    extra: dict = field(default_factory=dict)


def context(lines: list[ScriptLine], index: int, direction: Direction) -> tuple[str | None, str | None]:
    line = lines[index]
    neighbour_before = text_tools.strip_tags(lines[index - 1].spoken) if index > 0 else None
    neighbour_after = text_tools.strip_tags(lines[index + 1].spoken) if index + 1 < len(lines) else None
    before = line.previous if line.previous is not None else " ".join(filter(None, [direction.context_before, neighbour_before]))
    after = line.next if line.next is not None else " ".join(filter(None, [neighbour_after, direction.context_after]))
    return before or None, after or None


def request_body(text: str, before: str | None, after: str | None, direction: Direction, seed: int) -> dict:
    body: dict = {"text": text, "model_id": direction.model, "voice_settings": direction.settings, "seed": seed}
    if direction.send_language:
        body["language_code"] = direction.language
    if before:
        body["previous_text"] = before
    if after:
        body["next_text"] = after
    if direction.dictionaries:
        body["pronunciation_dictionary_locators"] = direction.dictionaries
    if direction.normalization:
        body["apply_text_normalization"] = direction.normalization
    return body


def take_slots(line: ScriptLine, wanted: int, until_pass: bool, per_form: int, retakes: int) -> list[tuple[int, str]]:
    if not until_pass:
        return [(0, line.ladder[0])] * wanted
    if len(line.ladder) == 1:
        return [(0, line.ladder[0])] * (wanted + retakes)
    return [(index, form) for index, form in enumerate(line.ladder) for _ in range(max(per_form, wanted))]


def plan_line(lines: list[ScriptLine], index: int, direction: Direction, prefix: str, slots: list[tuple[int, str]],
              base_seed: int | None) -> list[Attempt]:
    if len(slots) > len(string.ascii_lowercase):
        raise SystemExit(f"error: {lines[index].id}: {len(slots)} takes planned, at most 26 per line")
    before, after = context(lines, index, direction)
    attempts = []
    for take_index, (form_index, text) in enumerate(slots):
        seed = (base_seed + take_index) % (SEED_LIMIT + 1) if base_seed is not None else random.randint(0, SEED_LIMIT)
        name = f"{prefix}{lines[index].id}{string.ascii_lowercase[take_index]}"
        attempts.append(Attempt(name, lines[index], form_index, text, request_body(text, before, after, direction, seed)))
    return attempts


def audio_suffix(output_format: str) -> str:
    if output_format.startswith("mp3_"):
        return ".mp3"
    if output_format.startswith("pcm_"):
        return ".wav"
    raise SystemExit(f"error: --output-format {output_format} is not supported for takes (use mp3_* or pcm_*)")


def existing_audio(out: Path, name: str) -> Path | None:
    for suffix in (".mp3", ".wav"):
        if (out / f"{name}{suffix}").is_file() and (out / f"{name}.json").is_file():
            return out / f"{name}{suffix}"
    return None


def pcm_to_wav(raw: bytes, output_format: str) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(int(output_format.split("_")[1]))
        writer.writeframes(raw)
    return buffer.getvalue()


def meta_for(attempt: Attempt, direction: Direction, usage: dict, script: Path) -> dict:
    body = attempt.body
    return {
        "take": attempt.name, "line": attempt.line.id, "text": attempt.text, "line_text": attempt.line.spoken,
        "form_index": attempt.form_index, "voice_id": direction.voice_id, "voice_name": direction.voice_name,
        "voice_file": direction.voice_file, "model": direction.model, "settings": direction.settings,
        "seed": body["seed"], "language": direction.language, "language_code_sent": direction.send_language,
        "previous_text": body.get("previous_text"), "next_text": body.get("next_text"),
        "previous_request_ids": body.get("previous_request_ids"),
        "dictionaries": direction.dictionaries, "normalization": direction.normalization,
        "output_format": direction.output_format, "script": script.name, **usage,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def record(attempt: Attempt, key: str, out: Path, direction: Direction, script: Path) -> tuple[Path | None, dict, str]:
    url = f"{eleven.API_ROOT}/text-to-speech/{direction.voice_id}/with-timestamps?output_format={direction.output_format}"
    reply = eleven.send("POST", url, key, f"  {attempt.name}: ", json=attempt.body)
    if not reply.ok:
        return None, {}, f"FAIL {attempt.name}: HTTP {reply.status} {reply.error}"
    data = reply.json()
    audio = base64.b64decode(data["audio_base64"])
    if direction.output_format.startswith("pcm_"):
        audio = pcm_to_wav(audio, direction.output_format)
    audio_path = out / f"{attempt.name}{audio_suffix(direction.output_format)}"
    audio_path.write_bytes(audio)
    alignment = data.get("alignment") or data.get("normalized_alignment")
    alignment_payload = {"text": attempt.text, "model": direction.model, "alignment": alignment}
    (out / f"{attempt.name}.json").write_text(json.dumps(alignment_payload, ensure_ascii=False))
    meta = meta_for(attempt, direction, reply.usage(), script)
    write_meta(out, attempt.name, meta)
    load = f" (concurrent {meta['concurrent_requests']}/{meta['max_concurrent_requests']})" if meta.get("concurrent_requests") else ""
    return audio_path, meta, f"ok   {attempt.name}: wrote {audio_path}, .json, .meta.json{load}"


def write_meta(out: Path, name: str, meta: dict) -> None:
    (out / f"{name}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")


def read_meta(out: Path, name: str) -> dict:
    path = out / f"{name}.meta.json"
    return json.loads(path.read_text()) if path.is_file() else {}
