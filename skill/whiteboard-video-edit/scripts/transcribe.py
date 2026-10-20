# Ported from browser-use/video-use (MIT License, Copyright (c) 2026 Browser Use)
# https://github.com/browser-use/video-use at 9575612f066aa517354790a645fd90f9f95a743b
# Source files: helpers/transcribe.py and helpers/transcribe_batch.py. Adapted: curl upload
# (python urllib/requests can hit SSL certificate errors on a Mac with no CA bundle), the key
# read from the environment only, a source fingerprint on the cache, and a required --edit-dir
# so nothing lands next to the footage.
"""Word-level verbatim transcription with ElevenLabs Scribe, cached per source.

For each video: extract mono 16 kHz PCM with ffmpeg, refuse a silent track, upload to
Scribe (word timestamps, speaker labels, audio events; fillers kept, since Scribe is
verbatim by default), write the raw response to <edit-dir>/transcripts/<stem>.json.

Cache: a transcript is reused while its source fingerprint (absolute path, size, mtime)
still matches <stem>.source.json. A changed source is re-transcribed; a DIFFERENT source
with the same stem is refused, so two files that share a name cannot overwrite each other.

Usage:
    python3 transcribe.py --edit-dir <dir> <video> [<video> ...]
    python3 transcribe.py --edit-dir <dir> --language en --num-speakers 1 <video>
"""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
DEFAULT_MODEL = "scribe_v1"


def load_api_key() -> str:
    """ELEVENLABS_API_KEY from the environment, and nowhere else. Never printed."""
    v = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if v:
        return v
    sys.exit("ELEVENLABS_API_KEY is not set. Export it first: export ELEVENLABS_API_KEY=<your key> "
             "(an ElevenLabs key with Speech to Text access)")


def count_audio_tracks(video: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    return len([ln for ln in out.stdout.splitlines() if ln.strip()])


def peak_dbfs(wav_path: Path) -> float:
    peak = 0
    with wave.open(str(wav_path), "rb") as w:
        while frames := w.readframes(1 << 16):
            samples = array.array("h", frames)
            peak = max(peak, max(samples), -min(samples))
    return 20 * math.log10(peak / 32768) if peak > 0 else float("-inf")


def extract_audio(video: Path, dest: Path, audio_track: int = 0) -> None:
    # -vn plus an explicit audio map: without them the mp4-family muxers pick up the
    # 4K video stream too (the skill's measured 202 MB .m4a trap).
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-map", f"0:a:{audio_track}",
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        check=True,
    )


def call_scribe(audio: Path, api_key: str, model: str, language: str | None,
                num_speakers: int | None, out_json: Path) -> dict:
    """Upload with curl. The key goes in a 0600 header file, never on the command line."""
    fd, hdr_path = tempfile.mkstemp(prefix="xi-hdr-")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(f"xi-api-key: {api_key}\n")
        os.chmod(hdr_path, 0o600)
        cmd = [
            "curl", "-sS", "-X", "POST", SCRIBE_URL, "-H", f"@{hdr_path}",
            "-F", f"model_id={model}", "-F", "diarize=true", "-F", "tag_audio_events=true",
            "-F", "timestamps_granularity=word",
            "-F", f"file=@{audio};type=audio/wav",
            "-o", str(out_json), "-w", "%{http_code}", "--max-time", "1800",
        ]
        if language:
            cmd[cmd.index("-o"):cmd.index("-o")] = ["-F", f"language_code={language}"]
        if num_speakers:
            cmd[cmd.index("-o"):cmd.index("-o")] = ["-F", f"num_speakers={num_speakers}"]
        r = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        os.unlink(hdr_path)
    code = r.stdout.strip()
    if r.returncode != 0 or code != "200":
        body = out_json.read_text()[:500] if out_json.exists() else r.stderr[:500]
        out_json.unlink(missing_ok=True)
        raise RuntimeError(f"Scribe returned HTTP {code or '?'} (curl exit {r.returncode}): {body}")
    return json.loads(out_json.read_text())


def fingerprint(video: Path, model: str, audio_track: int) -> dict:
    st = video.stat()
    return {"path": str(video), "size": st.st_size, "mtime_ns": st.st_mtime_ns,
            "model": model, "audio_track": audio_track}


def transcribe_one(video: Path, edit_dir: Path, api_key: str, model: str = DEFAULT_MODEL,
                   language: str | None = None, num_speakers: int | None = None,
                   audio_track: int = 0) -> Path:
    tdir = edit_dir / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    suffix = "" if audio_track == 0 else f".track{audio_track}"
    out_path = tdir / f"{video.stem}{suffix}.json"
    fp_path = tdir / f"{video.stem}{suffix}.source.json"
    fp = fingerprint(video, model, audio_track)

    if out_path.exists():
        old = json.loads(fp_path.read_text()) if fp_path.exists() else None
        if old is None:
            print(f"cached (no fingerprint on file, kept): {out_path.name}")
            fp_path.write_text(json.dumps(fp, indent=2))
            return out_path
        if old.get("path") != fp["path"]:
            same = all(old.get(k) == fp[k] for k in ("size", "mtime_ns", "model", "audio_track"))
            if same:
                # moved (say from a download folder into the work folder), not changed
                print(f"cached (source moved, same size and mtime, fingerprint updated): {out_path.name}")
                fp_path.write_text(json.dumps(fp, indent=2))
                return out_path
            sys.exit(f"stem collision: {out_path.name} belongs to {old.get('path')}, not {video}. "
                     "Use a separate --edit-dir or rename the file. If it is the same recording "
                     f"copied, delete {fp_path.name} to reuse the transcript.")
        if old == fp:
            print(f"cached: {out_path.name}")
            return out_path
        print(f"source changed since the cached transcript, re-transcribing: {video.name}")

    n_tracks = count_audio_tracks(video)
    if n_tracks == 0:
        sys.exit(f"{video.name} has no audio track")
    if n_tracks > 1:
        print(f"  note: {video.name} has {n_tracks} audio tracks, using track {audio_track}")

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / f"{video.stem}.wav"
        extract_audio(video, wav, audio_track)
        peak = peak_dbfs(wav)
        if peak < -60.0:
            sys.exit(f"audio track {audio_track} of {video.name} is silent (peak {peak:.1f} dBFS), not uploading")
        print(f"  uploading {video.stem}.wav ({wav.stat().st_size / 1048576:.1f} MB) to Scribe ({model})", flush=True)
        tmp_json = Path(tmp) / "resp.json"
        payload = call_scribe(wav, api_key, model, language, num_speakers, tmp_json)

    out_path.write_text(json.dumps(payload, indent=2))
    fp_path.write_text(json.dumps(fp, indent=2))
    words = [w for w in payload.get("words", []) if w.get("type") == "word"]
    print(f"  saved {out_path.name}: {len(words)} words, language {payload.get('language_code')}, "
          f"{time.time() - t0:.1f}s")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Scribe word-level transcription, cached per source")
    ap.add_argument("videos", type=Path, nargs="+")
    ap.add_argument("--edit-dir", type=Path, required=True,
                    help="The folder that gets transcripts/ (the work folder's rough-cut/, captions/ or checks/)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--language", default=None, help="ISO code, e.g. en. Omit to auto-detect.")
    ap.add_argument("--num-speakers", type=int, default=None)
    ap.add_argument("--audio-track", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    videos = [v.resolve() for v in args.videos]
    for v in videos:
        if not v.exists():
            sys.exit(f"video not found: {v}")
    stems = [f"{v.stem}{'' if args.audio_track == 0 else f'.track{args.audio_track}'}" for v in videos]
    dupes = sorted({x for x in stems if stems.count(x) > 1})
    if dupes:
        # checked before any upload: two threads would each pay for a call and the last
        # writer would silently win the shared transcripts/<stem>.json
        sys.exit(f"two sources share a file name ({', '.join(dupes)}); "
                 "transcribe them into separate --edit-dir folders or rename one")
    edit_dir = args.edit_dir.expanduser().resolve()
    key = load_api_key()

    def one(v: Path) -> Path:
        return transcribe_one(v, edit_dir, key, args.model, args.language,
                              args.num_speakers, args.audio_track)

    if len(videos) == 1:
        one(videos[0])
        return
    failed = 0
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, len(videos)))) as ex:
        for v, fut in [(v, ex.submit(one, v)) for v in videos]:
            try:
                fut.result()
            except (RuntimeError, SystemExit) as e:
                failed += 1
                print(f"FAILED {v.name}: {e}", file=sys.stderr)
    if failed:
        sys.exit(f"{failed} of {len(videos)} transcriptions failed")


if __name__ == "__main__":
    main()
