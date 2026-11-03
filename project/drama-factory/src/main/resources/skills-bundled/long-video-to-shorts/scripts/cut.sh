#!/usr/bin/env bash
# Frame-accurate segment extraction (re-encode, not stream-copy).
set -euo pipefail
SRC="${1:?src}"; START="${2:?start}"; END="${3:?end}"; OUT="${4:?out}"
ffmpeg -y -i "$SRC" -ss "$START" -to "$END" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -avoid_negative_ts make_zero "$OUT"
echo "$OUT"
