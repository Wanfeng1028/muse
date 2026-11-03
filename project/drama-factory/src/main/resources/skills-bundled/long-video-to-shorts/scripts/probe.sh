#!/usr/bin/env bash
# Emit specs + a 1fps contact sheet the agent reads to classify facecam vs screen.
set -euo pipefail
PROJ="${1:?usage: probe.sh <project-dir>}"
SRC="$PROJ/work/source.mp4"
[ -f "$SRC" ] || { echo "missing $SRC"; exit 2; }

ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,avg_frame_rate:format=duration \
  -of json "$SRC" > "$PROJ/work/probe.json"

# 1 fps contact sheet, 6 columns. tile=6x0 auto-rows on newer ffmpeg; fall back to a fixed grid.
ffmpeg -y -i "$SRC" -vf "fps=1,scale=240:-1,tile=6x0" -frames:v 1 \
  "$PROJ/work/contactsheet.png" 2>/dev/null || \
ffmpeg -y -i "$SRC" -vf "fps=1,scale=240:-1,tile=6x10" -frames:v 1 "$PROJ/work/contactsheet.png"
echo "probe.json + contactsheet.png written to $PROJ/work/"
