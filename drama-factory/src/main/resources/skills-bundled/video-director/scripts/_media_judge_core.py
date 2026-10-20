"""Helpers for media_judge.py: ffmpeg lookup, media packaging for OpenRouter, the HTTP client and answer parsing."""
import base64
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


@dataclass
class Request:
    key: str
    parts: list[dict]
    meta: dict = field(default_factory=dict)


@dataclass
class Answer:
    request: Request
    text: str
    cost: float = 0.0
    model: str = ""
    error: str = ""


def find_binary(name: str) -> str:
    override = os.environ.get(name.upper())
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    sys.exit(f"error: {name} not found on PATH; install ffmpeg or set ${name.upper()}")


def load_env_file(path: Path | None) -> None:
    if not path:
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_key(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: {name} is not set (export it or pass --env-file)")
    return value


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_SUFFIXES


def probe_duration(path: Path) -> float:
    command = [find_binary("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    return float(subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip())


@functools.lru_cache(maxsize=256)
def audio_part(path: Path, start: float | None = None, length: float | None = None) -> dict:
    window = (["-ss", f"{start:.3f}"] if start is not None else []) + (["-t", f"{length:.3f}"] if length is not None else [])
    command = [find_binary("ffmpeg"), "-v", "error", *window, "-i", str(path), "-vn", "-ac", "1", "-b:a", "96k", "-f", "mp3", "-"]
    mp3 = subprocess.run(command, capture_output=True, check=True).stdout
    return {"type": "input_audio", "input_audio": {"data": base64.b64encode(mp3).decode(), "format": "mp3"}}


@functools.lru_cache(maxsize=16)
def video_part(path: Path, height: int, mute: bool) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "clip.mp4"
        audio = ["-an"] if mute else ["-c:a", "aac", "-b:a", "96k", "-ac", "1"]
        command = [
            find_binary("ffmpeg"), "-v", "error", "-y", "-i", str(path), "-vf", f"scale=-2:{height}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p", *audio,
            "-movflags", "+faststart", str(target),
        ]
        subprocess.run(command, check=True)
        data = base64.b64encode(target.read_bytes()).decode()
    return {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{data}"}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def media_bytes(part: dict) -> tuple[bytes, str]:
    if part["type"] == "input_audio":
        return base64.b64decode(part["input_audio"]["data"]), "mp3"
    return base64.b64decode(part["video_url"]["url"].split(",", 1)[1]), "mp4"


def describe_part(part: dict) -> str:
    if part["type"] == "text":
        return f"text: {part['text']}"
    payload, suffix = media_bytes(part)
    with tempfile.NamedTemporaryFile(suffix=f".{suffix}") as handle:
        handle.write(payload)
        handle.flush()
        command = [find_binary("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,sample_rate,channels",
                   "-show_entries", "format=duration", "-of", "compact=p=0:nk=0", handle.name]
        info = subprocess.run(command, capture_output=True, text=True, check=False).stdout.strip().replace("\n", "; ")
    encoded = len(payload) * 4 // 3 // 1024
    return f"{part['type']} {suffix}: {len(payload) // 1024} KB decoded, ~{encoded} KB base64, ffprobe [{info or 'UNREADABLE'}]"


def ask(request: Request, model: str, key: str, retries: int = 2) -> Answer:
    body = {"model": model, "messages": [{"role": "user", "content": request.parts}], "usage": {"include": True}}
    for attempt in range(retries + 1):
        try:
            response = httpx.post(OPENROUTER, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=600)
        except httpx.HTTPError as error:
            failure = f"network error: {error}"
        else:
            if response.status_code == 200:
                return parse_response(request, response.json())
            failure = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code not in (429, 500, 502, 503, 504):
                break
        time.sleep(4 * (attempt + 1))
    return Answer(request=request, text="", error=failure)


def parse_response(request: Request, data: dict) -> Answer:
    choices = data.get("choices") or [{}]
    content = (choices[0].get("message") or {}).get("content") or ""
    text = re.sub(r"\s*\n\s*", " ", content).strip()
    usage = data.get("usage") or {}
    return Answer(request=request, text=text, cost=float(usage.get("cost") or 0), model=str(data.get("model") or ""))


def field_text(answer: str, name: str) -> str:
    match = re.search(rf"{re.escape(name)}[^:|]*:\s*([^|]+)", answer, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def field_number(answer: str, name: str) -> float | None:
    match = re.search(rf"{re.escape(name)}[^:|]*:\s*(\d+(?:\.\d+)?)", answer, re.IGNORECASE)
    return float(match.group(1)) if match else None


def save(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    print(f"wrote {path}")


def save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {path}")
