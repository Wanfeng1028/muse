"""Locked project voice (voice.json) and the resolved direction vo_record.py sends: model rules, drops and context."""
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, ValidationError

DEFAULTS = {"model": "eleven_v4", "stability": 0.5, "similarity": 0.75, "output_format": "mp3_44100_128"}
NO_LANGUAGE_CODE = {"eleven_multilingual_v2", "eleven_flash_v2", "eleven_turbo_v2", "eleven_monolingual_v1", "eleven_multilingual_v1"}


class VoiceSettings(BaseModel):
    stability: float | None = None
    similarity: float | None = Field(None, validation_alias=AliasChoices("similarity", "similarity_boost"))
    style: float | None = None
    speed: float | None = None
    speaker_boost: bool | None = Field(None, validation_alias=AliasChoices("speaker_boost", "use_speaker_boost"))


class VoiceContext(BaseModel):
    before: str | None = None
    after: str | None = None


class VoiceFile(BaseModel):
    id: str = Field(validation_alias=AliasChoices("id", "voice_id"))
    name: str = ""
    model: str | None = None
    language: str | None = None
    settings: VoiceSettings = VoiceSettings()
    context: VoiceContext = VoiceContext()
    tags: list[str] = []
    dictionaries: list[str] = []
    normalization: Literal["auto", "on", "off"] | None = None
    output_format: str | None = None
    references: list[str] = []
    notes: str = ""


@dataclass
class Direction:
    voice_id: str
    voice_name: str
    model: str
    language: str | None
    send_language: bool
    settings: dict
    context_before: str | None
    context_after: str | None
    tags: list[str]
    dictionaries: list[dict]
    normalization: str | None
    output_format: str
    voice_file: str | None
    warnings: list[str] = field(default_factory=list)


def load_voice_file(value: str) -> VoiceFile | None:
    path = Path(value)
    if not (path.suffix == ".json" or path.is_file()):
        return None
    if not path.is_file():
        sys.exit(f"error: voice file {path} not found")
    try:
        return VoiceFile.model_validate_json(path.read_text())
    except ValidationError as error:
        sys.exit(f"error: {path} is not a valid voice file:\n{error}")


def load_context_file(path: Path | None) -> VoiceContext:
    if not path:
        return VoiceContext()
    raw = path.read_text()
    if path.suffix == ".json":
        return VoiceContext.model_validate(json.loads(raw))
    before, _, after = raw.partition("\n---\n")
    return VoiceContext(before=before.strip() or None, after=after.strip() or None)


def dictionary_locator(value: str) -> dict:
    dictionary_id, _, version = value.partition(":")
    locator = {"pronunciation_dictionary_id": dictionary_id}
    if version:
        locator["version_id"] = version
    return locator


def first(*values: object) -> object:
    return next((value for value in values if value is not None), None)


def build_settings(args: argparse.Namespace, saved: VoiceSettings, model: str, warnings: list[str]) -> dict:
    settings: dict = {
        "stability": first(args.stability, saved.stability, DEFAULTS["stability"]),
        "similarity_boost": first(args.similarity, saved.similarity, DEFAULTS["similarity"]),
    }
    optional = {"style": first(args.style, saved.style), "speed": first(args.speed, saved.speed),
                "use_speaker_boost": first(args.speaker_boost, saved.speaker_boost)}
    for name, value in optional.items():
        if value is None:
            continue
        if model.startswith("eleven_v4"):
            warnings.append(f"dropped {name}={value}: {model} supports only stability and similarity (fix pace with vo_build tempo)")
            continue
        settings[name] = value
    return settings


def resolve(args: argparse.Namespace) -> Direction:
    loaded = load_voice_file(args.voice)
    saved = loaded or VoiceFile(id=args.voice)
    from_file = args.voice if loaded else None
    model = str(first(args.model, saved.model, DEFAULTS["model"]))
    language = None if args.no_language else first(args.language, saved.language)
    if not language and not args.no_language:
        sys.exit("error: --language is required (ISO 639-1, e.g. es); pass --no-language to send none")
    warnings: list[str] = []
    send_language = bool(language) and model not in NO_LANGUAGE_CODE
    if language and not send_language:
        warnings.append(f"not sending language_code: {model} does not accept it (the API returns an error)")
    context_file = load_context_file(args.context_file)
    dictionaries = args.dictionary or saved.dictionaries
    if len(dictionaries) > 3:
        sys.exit("error: at most 3 pronunciation dictionaries per request")
    return Direction(
        voice_id=saved.id, voice_name=saved.name, model=model, language=language, send_language=send_language,
        settings=build_settings(args, saved.settings, model, warnings),
        context_before=first(args.context_before, context_file.before, saved.context.before),
        context_after=first(args.context_after, context_file.after, saved.context.after),
        tags=saved.tags, dictionaries=[dictionary_locator(value) for value in dictionaries],
        normalization=first(args.normalization, saved.normalization),
        output_format=str(first(args.output_format, saved.output_format, DEFAULTS["output_format"])),
        voice_file=from_file, warnings=warnings,
    )
