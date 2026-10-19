#!/usr/bin/env bash
# Draw a top-CENTER hook title with one accent-coloured word, shown for a few seconds then gone.
# usage: hook_title.sh <in.mp4> "<title with *accent* word>" <out.mp4> <font.ttf> [seconds]
#
# Mark the main word with *asterisks*: "Feeling awkward is *normal*".
# ASS-based (centers natively, colours a word, supports timed display). Uses the chdir+
# relative-path trick so the subtitles filter never sees a Windows drive colon.
set -euo pipefail
IN="${1:?in}"; TITLE="${2:?title}"; OUT="${3:?out}"; FONT="${4:?font}"; SECONDS_SHOW="${5:-}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IN_ABS="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"
mkdir -p "$(dirname "$OUT")"
OUT_DIR="$(cd "$(dirname "$OUT")" && pwd)"; OUT_ABS="$OUT_DIR/$(basename "$OUT")"

# font family + duration come from config.json (empty args -> config defaults)
FONTFAM="$(node "$HERE/lib_config.cjs" font_family)"
WORK="$(mktemp -d)"
cp "$FONT" "$WORK/font.ttf"
node "$HERE/hook_ass.cjs" "$TITLE" "$FONTFAM" "$SECONDS_SHOW" > "$WORK/hook.ass"

( cd "$WORK" && ffmpeg -y -i "$IN_ABS" -vf "subtitles=hook.ass:fontsdir=." \
  -c:v libx264 -pix_fmt yuv420p -c:a copy "$OUT_ABS" )

rm -rf "$WORK"
echo "$OUT_ABS"
