#!/usr/bin/env bash
# Phase 0.5 (Tier 2) — transcribe the source audio with whisper.cpp.
#
# Produces a timestamped transcript that seeds the shot list: Claude reads what's said
# and when, so cut decisions follow the narration, not just the visuals. Optional — if
# whisper.cpp or a model isn't present, it prints setup steps and no-ops (exit 0) so the
# pipeline keeps going without a transcript.
#
# Usage:
#   transcribe.sh --video source.mov --out-prefix mydemo-transcript
#
# Options:
#   --model PATH   ggml model (default: $WHISPER_MODEL, else ~/.cache/whisper-cpp/ggml-base.en.bin)
#   --lang CODE    language (default: en)
#
# Emits <out-prefix>.json (segments with start/end) and <out-prefix>.srt.
set -euo pipefail

VIDEO="" PREFIX="" MODEL="${WHISPER_MODEL:-$HOME/.cache/whisper-cpp/ggml-base.en.bin}" LANG="en"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --video) VIDEO="$2"; shift 2;;
    --out-prefix) PREFIX="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    --lang) LANG="$2"; shift 2;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done
[[ -z "$VIDEO" || -z "$PREFIX" ]] && { echo "need --video --out-prefix" >&2; exit 1; }

# Find the whisper.cpp CLI (name varies across versions).
CLI=""
for c in whisper-cli whisper-cpp main; do command -v "$c" >/dev/null 2>&1 && { CLI="$c"; break; }; done

if [[ -z "$CLI" ]]; then
  cat >&2 <<'MSG'
[transcribe] whisper.cpp not found — skipping transcription (Tier 1 silence detection still works).
To enable:  brew install whisper-cpp
Then fetch a model, e.g.:
  mkdir -p ~/.cache/whisper-cpp
  curl -L -o ~/.cache/whisper-cpp/ggml-base.en.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
MSG
  exit 0
fi

if [[ ! -f "$MODEL" ]]; then
  cat >&2 <<MSG
[transcribe] model not found at: $MODEL — skipping transcription.
Fetch one (base.en is a good default):
  mkdir -p "$(dirname "$MODEL")"
  curl -L -o "$MODEL" \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
Or point --model / \$WHISPER_MODEL at an existing ggml model.
MSG
  exit 0
fi

# whisper.cpp wants 16 kHz mono WAV.
WAV="$(dirname "$PREFIX")/.$(basename "$PREFIX").wav"
ffmpeg -y -hide_banner -loglevel error -i "$VIDEO" -ar 16000 -ac 1 -c:a pcm_s16le "$WAV"

"$CLI" -m "$MODEL" -f "$WAV" -l "$LANG" -oj -osrt -of "$PREFIX" >/dev/null 2>&1

rm -f "$WAV"
echo "Done → ${PREFIX}.json + ${PREFIX}.srt"
