#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
sheets.sh: review sheets from a rendered video (overview, phone readability, a move, the beat grid).

Usage:
  sheets.sh contact <video.mp4> <out.png> [--rate 2] [--width 270] [--grid 6x5]
  sheets.sh phone   <video.mp4> <out.png> [--rate 1] [--width 360] [--grid 5x3]
  sheets.sh around  <video.mp4> <out.png> <t_seconds> [--count 12] [--width 320] [--grid 6x2]
  sheets.sh beats   <video.mp4> <out.png> <bpm> <offset_seconds> [--every 1] [--width 270] [--grid 8x4]
Modes:
  contact  frames at --rate per second; the whole film at a glance.
  phone    one frame per second at 360 px wide; text that does not read here fails on a phone.
  around   --count consecutive frames centred on t (every frame of a move, from the encoded file).
  beats    one frame on every --every beats starting at offset (first downbeat); judges rhythm and continuity.
Output: <out.png>, or <out>-01.png, <out>-02.png ... when the film needs several pages. Tiles read left to right,
top to bottom; the printed legend maps each page to its time span (this ffmpeg may lack drawtext, so tiles are unlabelled).
Example: sheets.sh beats out/final/film-16x9.mp4 out/review/beats.png 120 0.48
EOF
}

resolve_tool() {
  local variable="$1" name="$2"
  if [ -n "${!variable:-}" ]; then echo "${!variable}"; return; fi
  if command -v "$name" >/dev/null 2>&1; then command -v "$name"; return; fi
  echo "$name not found: set \$$variable or install ffmpeg (brew install ffmpeg / apt install ffmpeg)" >&2
  exit 1
}

for argument in "$@"; do
  case "$argument" in -h|--help) usage; exit 0 ;; esac
done
if [ "$#" -lt 3 ]; then usage >&2; exit 2; fi

mode="$1"; video="$2"; output="$3"; shift 3
[ -f "$video" ] || { echo "video not found: $video" >&2; exit 1; }
ffmpeg_binary=$(resolve_tool FFMPEG ffmpeg)
ffprobe_binary=$(resolve_tool FFPROBE ffprobe)

around_time=""; bpm=""; offset=""
case "$mode" in
  contact) rate=2; width=270; grid=6x5 ;;
  phone) rate=1; width=360; grid=5x3 ;;
  around) width=320; grid=6x2; count=12; around_time="${1:?around needs <t_seconds>}"; shift ;;
  beats) width=270; grid=8x4; every=1; bpm="${1:?beats needs <bpm>}"; offset="${2:?beats needs <offset_seconds>}"; shift 2 ;;
  *) echo "unknown mode: $mode" >&2; usage >&2; exit 2 ;;
esac

while [ "$#" -gt 0 ]; do
  case "$1" in
    --rate) rate="$2"; shift 2 ;;
    --width) width="$2"; shift 2 ;;
    --grid) grid="$2"; shift 2 ;;
    --count) count="$2"; shift 2 ;;
    --every) every="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

probe() { "$ffprobe_binary" -v error -select_streams v:0 -show_entries "$1" -of csv=p=0 "$video" | head -1 | tr -d ',\r'; }
duration=$("$ffprobe_binary" -v error -show_entries format=duration -of csv=p=0 "$video" | tr -d '\r')
frame_rate=$(probe stream=avg_frame_rate | awk -F/ '{ if ($2 > 0) printf "%.6f", $1 / $2; else print $1 }')

columns="${grid%x*}"; rows="${grid#*x}"
per_page=$(( columns * rows ))
start=0
case "$mode" in
  around)
    start=$(awk -v t="$around_time" -v c="$count" -v f="$frame_rate" 'BEGIN { s = t - (c / 2) / f; if (s < 0) s = 0; printf "%.4f", s }')
    rate="$frame_rate" ;;
  beats)
    start="$offset"
    rate=$(awk -v b="$bpm" -v e="$every" 'BEGIN { printf "%.6f", b / 60 / e }') ;;
esac

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/sheets-XXXXXX")
trap 'rm -rf "$work_dir"' EXIT

tiling="scale=$width:-2,tile=${columns}x${rows}:padding=4:color=white"
step=$(awk -v r="$rate" 'BEGIN { printf "%.6f", 1 / r }')
grid_select="select=isnan(prev_selected_t)+gt(floor((t+0.0005)/$step)\\,floor((prev_selected_t+0.0005)/$step))"
filters="$grid_select,$tiling"
[ "$mode" = "around" ] && filters="trim=end_frame=$count,$tiling"
"$ffmpeg_binary" -v error -y -ss "$start" -i "$video" -vf "$filters" -fps_mode passthrough -an "$work_dir/page-%03d.png"

pages=$(find "$work_dir" -name 'page-*.png' | sort)
page_count=$(echo "$pages" | grep -c . || true)
[ "$page_count" -gt 0 ] || { echo "ffmpeg produced no sheet" >&2; exit 1; }
mkdir -p "$(dirname "$output")"
stem="${output%.png}"
index=0
for page in $pages; do
  index=$(( index + 1 ))
  if [ "$page_count" -eq 1 ]; then target="$output"; else target=$(printf "%s-%02d.png" "$stem" "$index"); fi
  mv "$page" "$target"
  span=$(awk -v s="$start" -v r="$rate" -v p="$per_page" -v i="$index" -v d="$duration" 'BEGIN {
    a = s + (i - 1) * p / r; b = s + (i * p - 1) / r; if (b > d) b = d; printf "%.2f-%.2f s", a, b }')
  echo "$target ($mode, ${columns}x${rows}, tile k = $(printf '%.3f' "$start") s + k / $rate s; covers $span)"
done
