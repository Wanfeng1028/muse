#!/usr/bin/env python3
"""Generate one narration clip per visible step (feature-demo voiceover).

USAGE
  tts.py RUN_DIR                                   # default: piper Ngọc Lan for lang vi if installed, else macOS say
  tts.py RUN_DIR --provider piper --voice ngoclan  # local Vietnamese (install once: install_tts.py)
  tts.py RUN_DIR --provider piper --voice quanghuy --speed 1.0
  tts.py RUN_DIR --provider say --voice Linh       # macOS built-in voice
  tts.py RUN_DIR --provider openai --allow-cloud   # needs OPENAI_API_KEY; sends the script text to OpenAI
  tts.py RUN_DIR --provider elevenlabs --voice <voice_id> --allow-cloud   # needs ELEVENLABS_API_KEY

Piper voices: ngoclan (nữ, default), minhanh (nữ), thuha (nữ), yennhi (nữ), quanghuy (nam).
Text per step: the step's `say:` field, else its caption. For piper, numbers, %, $ and đ are spelled out
in Vietnamese first ("1.500" -> "một nghìn năm trăm"). Every clip is loudness-normalised to -16 LUFS.
Writes RUN_DIR/narration/stepNN.m4a and narration/manifest.json; edl.py then holds each step at least as
long as its clip and mixes the audio. Cloud providers send text off this machine: ask the user before
passing --allow-cloud (Hard rule 2).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import die, load_storyboard, need, probe_summary, run_ffmpeg, run_paths, save_json  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
from install_tts import MODEL as PIPER_MODEL, SPEAKERS as PIPER_VOICES, installed as piper_installed, venv_python  # noqa: E402

PIPER_PY = venv_python()
SAY_VOICES = {"vi": "Linh", "en": "Samantha"}
CLOUD = ("openai", "elevenlabs")
LOUDNESS = "loudnorm=I=-16:TP=-1.5:LRA=11"

# ---------- Vietnamese text normalisation (numbers) ----------

DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
SCALES = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ"]


def _group(n: int, full: bool) -> str:
    """Read 0..999. full=True when a higher group precedes it ('không trăm', 'linh')."""
    h, t, u = n // 100, n // 10 % 10, n % 10
    out = []
    if h or full:
        out += [DIGITS[h], "trăm"]
    if t == 0:
        if u:
            out += (["linh"] if (h or full) else []) + [DIGITS[u]]
    elif t == 1:
        out += ["mười"] + ([] if u == 0 else ["lăm"] if u == 5 else [DIGITS[u]])
    else:
        out += [DIGITS[t], "mươi"] + ([] if u == 0 else ["mốt"] if u == 1 else ["lăm"] if u == 5 else [DIGITS[u]])
    return " ".join(out)


def num_to_vi(n: int) -> str:
    if n == 0:
        return "không"
    if n < 0:
        return "âm " + num_to_vi(-n)
    groups = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    words = []
    for idx in range(len(groups) - 1, -1, -1):
        g = groups[idx]
        if g == 0:
            continue
        higher = idx < len(groups) - 1
        scale = SCALES[idx]
        words.append(_group(g, higher) + (" " + scale if scale else ""))
    return " ".join(words)


NUM_RE = re.compile(r"(\$)?(\d{1,3}(?:[.,]\d{3})+(?![\d.,]\d)|\d+(?:[.,]\d+)?)\s*(%|\$|USD|VNĐ|VND|đ\b)?")


def normalize_vi(text: str) -> str:
    def rep(m):
        pre, num, unit = m.group(1), m.group(2), m.group(3)
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", num):
            words = num_to_vi(int(re.sub(r"[.,]", "", num)))
        elif re.search(r"[.,]", num):
            a, b = re.split(r"[.,]", num, maxsplit=1)
            words = num_to_vi(int(a)) + " phẩy " + (num_to_vi(int(b)) if not b.startswith("0")
                                                     else " ".join(DIGITS[int(c)] for c in b))
        else:
            words = num_to_vi(int(num))
        tail = {"%": " phần trăm", "$": " đô la", "USD": " đô la", "VNĐ": " đồng", "VND": " đồng", "đ": " đồng"}
        if pre:
            words += " đô la"
        elif unit:
            words += tail[unit]
        return words + (" " if m.group(0).endswith(" ") else "")
    return re.sub(r"\s+", " ", NUM_RE.sub(rep, text)).strip()


# ---------- providers ----------

def to_m4a(src: pathlib.Path, out: pathlib.Path):
    run_ffmpeg(["-i", str(src), "-af", LOUDNESS, "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "160k", str(out)])


def say(text: str, out: pathlib.Path, voice: str, rate: int):
    if not shutil.which("say"):
        die("`say` is macOS only; use --provider piper (install_tts.py)")
    voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    if not any(line.split()[0] == voice for line in voices.splitlines() if line.strip()):
        die(f"voice '{voice}' not installed. System Settings > Accessibility > Spoken Content > Manage Voices")
    with tempfile.TemporaryDirectory() as td:
        aiff = pathlib.Path(td) / "s.aiff"
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text], check=True)
        to_m4a(aiff, out)


def piper_batch(items: list[tuple[str, pathlib.Path]], voice: str, speed: float):
    """All clips in one worker process (the model loads once)."""
    if not piper_installed():
        die(f"piper voice not installed. Run: python {HERE / 'install_tts.py'}")
    sid = PIPER_VOICES.get(voice.lower().replace(" ", "")) if not voice.isdigit() else int(voice)
    if sid is None:
        die(f"unknown piper voice '{voice}'. Choose: {', '.join(PIPER_VOICES)}")
    with tempfile.TemporaryDirectory() as td:
        jobs = [{"text": t, "out": str(pathlib.Path(td) / f"{k}.wav")} for k, (t, _) in enumerate(items)]
        jf = pathlib.Path(td) / "jobs.json"
        jf.write_text(json.dumps({"sid": sid, "speed": speed, "jobs": jobs}, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([str(PIPER_PY), str(HERE / "piper_worker.py"), str(PIPER_MODEL), str(jf)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            die("piper worker failed:\n" + r.stderr[-2000:])
        for job, (_, out) in zip(jobs, items):
            to_m4a(pathlib.Path(job["out"]), out)


def http_audio(url: str, headers: dict, payload: dict, out: pathlib.Path):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r, tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(r.read())
        tmp = pathlib.Path(f.name)
    try:
        to_m4a(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=pathlib.Path)
    ap.add_argument("--provider", choices=["piper", "say", "openai", "elevenlabs"])
    ap.add_argument("--voice")
    ap.add_argument("--rate", type=int, default=180, help="words per minute for `say`")
    ap.add_argument("--speed", type=float, default=0.9, help="piper speed (default 0.9 ≈ 3.5-4 words/s; 1.0 faster)")
    ap.add_argument("--allow-cloud", action="store_true", help="the user agreed to send the text to the provider")
    a = ap.parse_args()
    need("ffmpeg")
    p = run_paths(a.run)
    sb = load_storyboard(p["storyboard"])
    if sb["mode"] != "feature-demo":
        die("narration is for feature-demo only")
    lang = str(sb.get("lang", "en"))[:2]
    provider = a.provider or ("piper" if lang == "vi" and piper_installed() else "say")
    if provider in CLOUD and not a.allow_cloud:
        die(f"--provider {provider} sends the narration text to an external service. "
            "Ask the user first, then re-run with --allow-cloud.")
    voice = a.voice or {"piper": "ngoclan", "say": SAY_VOICES.get(lang, "Samantha"),
                        "openai": "alloy", "elevenlabs": None}[provider]
    if provider == "elevenlabs" and not voice:
        die("--voice <voice_id> is required for elevenlabs")
    ndir = a.run / "narration"
    ndir.mkdir(exist_ok=True)
    todo = []
    for i, step in enumerate(sb["steps"]):
        if step.get("hidden"):
            continue
        text = str(step.get("say") or step.get("caption") or "").strip()
        if not text:
            continue
        spoken = normalize_vi(text) if provider == "piper" and lang == "vi" else text
        out = ndir / f"step{i:02d}.m4a"
        out.unlink(missing_ok=True)
        todo.append((i, text, spoken, out))

    if provider == "piper":
        piper_batch([(s, o) for _, _, s, o in todo], voice, a.speed)
    for i, text, spoken, out in todo:
        if provider == "say":
            say(spoken, out, voice, a.rate)
        elif provider == "openai":
            key = os.environ.get("OPENAI_API_KEY") or die("OPENAI_API_KEY is not set")
            http_audio("https://api.openai.com/v1/audio/speech",
                       {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       {"model": "gpt-4o-mini-tts", "voice": voice, "input": spoken, "response_format": "mp3"}, out)
        elif provider == "elevenlabs":
            key = os.environ.get("ELEVENLABS_API_KEY") or die("ELEVENLABS_API_KEY is not set")
            http_audio(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                       {"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                       {"text": spoken, "model_id": "eleven_multilingual_v2"}, out)

    clips = []
    for i, text, spoken, out in todo:
        d = probe_summary(out)["duration"]
        clips.append({"i": i, "file": f"narration/{out.name}", "duration": round(d, 3), "text": text,
                      **({"spoken": spoken} if spoken != text else {})})
        print(f"step {i + 1}: {d:.2f}s, {len(spoken.split()) / d:.1f} words/s  {spoken}")
    save_json(ndir / "manifest.json", {"provider": provider, "voice": voice, "clips": clips})
    print(f"{provider}/{voice}: wrote {ndir / 'manifest.json'}; now run edl.py (it holds steps to fit each clip)")


if __name__ == "__main__":
    main()
