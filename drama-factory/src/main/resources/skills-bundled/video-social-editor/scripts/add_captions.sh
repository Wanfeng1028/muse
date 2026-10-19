#!/usr/bin/env bash
# Phase 5b (optional) — burn caption cards onto a video.
#
# Composites the caption PNGs from generate_captions.py onto a video, each shown during
# its segment window. Runs AFTER add_voiceover.sh so captions sit on top of the bubble.
# Kept separate from the VO mux so each stage stays simple and reviewable.
#
# Usage:
#   add_captions.sh --video final-vo.mp4 --lines captions.json --out final-vo-cc.mp4
#
# captions.json is the same {text,start,end} array fed to generate_captions.py.
# A single JSON is the source of truth: this script regenerates the PNGs from it and
# reads each card's height to position it --bottom-margin px above the bottom edge.
set -euo pipefail

VIDEO="" LINES="" OUT="" BOTTOM=210
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --video) VIDEO="$2"; shift 2;;
    --lines) LINES="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --bottom-margin) BOTTOM="$2"; shift 2;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done
[[ -z "$VIDEO" || -z "$LINES" || -z "$OUT" ]] && { echo "need --video --lines --out" >&2; exit 1; }

read -r W H < <(ffprobe -v quiet -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$VIDEO" | tr ',' ' ')
CAPDIR="$(dirname "$OUT")/.captions"
rm -rf "$CAPDIR"; mkdir -p "$CAPDIR"

uv run --with pillow python "$SCRIPT_DIR/generate_captions.py" \
  --lines "$LINES" --out "$CAPDIR" --frame-h "$H" --bottom-margin "$BOTTOM" >/dev/null

# Emit the caption PNG paths and the overlay chain from the JSON + each PNG's height.
# Paths and filter are separated by a tab; paths are \x1f-joined to survive spaces.
OUTLINE="$(uv run --with pillow python - "$LINES" "$CAPDIR" "$H" "$BOTTOM" <<'PY'
import json, sys
from pathlib import Path
from PIL import Image
lines = json.loads(Path(sys.argv[1]).read_text())
capdir, frame_h, bottom = Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
paths, chain, prev = [], [], "0:v"
for i, item in enumerate(lines, 1):
    png = capdir / f"caption_{i:02d}.png"
    paths.append(str(png))
    y = frame_h - Image.open(png).height - bottom
    label = f"c{i}"
    chain.append(f"[{prev}][{i}:v]overlay=0:{y}:enable='between(t,{item['start']},{item['end']})'[{label}]")
    prev = label
chain_str = ";".join(chain) + f";[{prev}]format=yuv420p[out]"
print("\x1f".join(paths) + "\t" + chain_str)
PY
)"

CAP_RAW="${OUTLINE%%$'\t'*}"
FILTER="${OUTLINE#*$'\t'}"

IN_ARGS=(-i "$VIDEO")
IFS=$'\x1f' read -r -a CAP_PATHS <<< "$CAP_RAW"
for p in "${CAP_PATHS[@]}"; do IN_ARGS+=(-i "$p"); done

ffmpeg -y "${IN_ARGS[@]}" -filter_complex "$FILTER" \
  -map "[out]" -map 0:a? -c:v libx264 -crf 20 -preset medium -c:a copy "$OUT"

rm -rf "$CAPDIR"
echo "Done → $OUT"
