#!/usr/bin/env bash
# Orchestrate one clip: cut -> reframe(9:16) -> captions -> (hook) -> OUT.
#
# usage:
#   build_clip.sh <project-dir> --start HH:MM:SS.mmm --end HH:MM:SS.mmm \
#       --kind facecam|screen [--title "..."] [--hook true|false] \
#       [--face-cx 0..1] [--caption-mode ass|embedded|none] --out <path.mp4>
#
# Uses <project>/work/source.mp4 and <project>/work/transcript.json.
# facecam + caption-mode=embedded  -> reframes, then PRINTS a HANDOFF line
#   (the agent runs the embedded-captions skill on *_reframed.mp4, then hook_title.sh).
set -euo pipefail
PROJ="${1:?project dir}"; shift
START=""; END=""; KIND="screen"; TITLE=""; HOOK="true"; FACE_CX="0.5"; CAPMODE="ass"; OUT=""; STYLE=""
while [ $# -gt 0 ]; do case "$1" in
  --start) START="$2";shift 2;; --end) END="$2";shift 2;; --kind) KIND="$2";shift 2;;
  --title) TITLE="$2";shift 2;; --hook) HOOK="$2";shift 2;; --face-cx) FACE_CX="$2";shift 2;;
  --caption-mode) CAPMODE="$2";shift 2;; --style) STYLE="$2";shift 2;; --out) OUT="$2";shift 2;;
  *) echo "unknown arg: $1"; exit 2;; esac; done
[ -n "$START" ] && [ -n "$END" ] && [ -n "$OUT" ] || { echo "need --start --end --out"; exit 2; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$PROJ/work/source.mp4"; TR="$PROJ/work/transcript.json"
FONT="$(node "$HERE/lib_config.cjs" font_abs)"   # font path from config.json
mkdir -p "$(dirname "$OUT")"
OUT_DIR="$(cd "$(dirname "$OUT")" && pwd)"; OUT_ABS="$OUT_DIR/$(basename "$OUT")"
TMP="$PROJ/work/_clip_$$"; mkdir -p "$TMP"

# HH:MM:SS(.mmm) -> seconds (awk, no CR issues since args are clean)
to_sec(){ awk -v t="$1" 'BEGIN{n=split(t,p,":"); print p[1]*3600+p[2]*60+p[3]}'; }
S0="$(to_sec "$START")"; S1="$(to_sec "$END")"

bash "$HERE/cut.sh" "$SRC" "$START" "$END" "$TMP/cut.mp4" >/dev/null

if [ "$KIND" = "facecam" ]; then
  bash "$HERE/reframe_facecam.sh" "$TMP/cut.mp4" "$FACE_CX" "$TMP/reframed.mp4" >/dev/null
else
  bash "$HERE/reframe_gameplay.sh" "$TMP/cut.mp4" "$TMP/reframed.mp4" >/dev/null
fi

# facecam + embedded-captions skill: stop after reframe, hand off to the agent.
if [ "$KIND" = "facecam" ] && [ "$CAPMODE" = "embedded" ]; then
  cp "$TMP/reframed.mp4" "${OUT_ABS%.mp4}_reframed.mp4"
  rm -rf "$TMP"
  echo "HANDOFF: run the embedded-captions skill on ${OUT_ABS%.mp4}_reframed.mp4, then:"
  echo "         bash scripts/hook_title.sh <captioned.mp4> \"$TITLE\" $OUT_ABS $FONT"
  exit 0
fi

# caption stage
if [ "$CAPMODE" = "none" ]; then
  cp "$TMP/reframed.mp4" "$TMP/capped.mp4"
else
  bash "$HERE/captions_burn.sh" "$TMP/reframed.mp4" "$TR" "$S0" "$S1" "$TMP/capped.mp4" "$FONT" "" "$STYLE" >/dev/null
fi

# hook stage
if [ "$HOOK" = "true" ] && [ -n "$TITLE" ]; then
  bash "$HERE/hook_title.sh" "$TMP/capped.mp4" "$TITLE" "$OUT_ABS" "$FONT" >/dev/null
else
  cp "$TMP/capped.mp4" "$OUT_ABS"
fi

rm -rf "$TMP"
echo "$OUT_ABS"
