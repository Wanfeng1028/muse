#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
strip.sh: render every Nth frame of a time range and tile it 6 wide, to inspect fast motion frame by frame.

Usage: strip.sh <composition> <start_s> <end_s> <out.png> [--fps 30] [--nth 2] [--scale 0.25]
                [--columns 6] [--props JSON] [--entry src/index.ts] [--verbose]
Run from the Remotion project root. Frames go to a temp dir that is cleared each run.
Output: one PNG strip (read left to right, top to bottom).
Example: strip.sh Wide 12.0 13.5 out/review/dive-strip.png --fps 30 --nth 2
EOF
}

resolve_ffmpeg() {
  if [ -n "${FFMPEG:-}" ]; then echo "$FFMPEG"; return; fi
  if command -v ffmpeg >/dev/null 2>&1; then command -v ffmpeg; return; fi
  echo "ffmpeg not found: set \$FFMPEG or install ffmpeg (brew install ffmpeg / apt install ffmpeg)" >&2
  exit 1
}

for argument in "$@"; do
  case "$argument" in -h|--help) usage; exit 0 ;; esac
done
if [ "$#" -lt 4 ]; then usage >&2; exit 2; fi

composition="$1"; start_seconds="$2"; end_seconds="$3"; output="$4"; shift 4
fps=30; nth=2; scale=0.25; columns=6; props=""; entry=""; verbose=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --fps) fps="$2"; shift 2 ;;
    --nth) nth="$2"; shift 2 ;;
    --scale) scale="$2"; shift 2 ;;
    --columns) columns="$2"; shift 2 ;;
    --props) props="$2"; shift 2 ;;
    --entry) entry="$2"; shift 2 ;;
    --verbose) verbose=1; shift ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

ffmpeg_binary=$(resolve_ffmpeg)
[ "$verbose" = 1 ] && echo "using ffmpeg: $ffmpeg_binary" >&2

first_frame=$(awk -v t="$start_seconds" -v f="$fps" 'BEGIN { printf "%d", t * f + 0.5 }')
last_frame=$(awk -v t="$end_seconds" -v f="$fps" 'BEGIN { printf "%d", t * f + 0.5 }')
if [ "$last_frame" -lt "$first_frame" ]; then echo "end must be after start" >&2; exit 2; fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/strip-XXXXXX")
trap 'rm -rf "$work_dir"' EXIT
folder="$work_dir/frames"

command=(npx remotion render)
[ -n "$entry" ] && command+=("$entry")
command+=("$composition" "$folder" --sequence "--frames=$first_frame-$last_frame" "--scale=$scale" --image-format=jpeg --log=error)
[ -n "$props" ] && command+=("--props=$props")
[ "$verbose" = 1 ] && echo "\$ ${command[*]}" >&2
"${command[@]}"

count=$(find "$folder" -name '*.jpeg' | wc -l | tr -d ' ')
if [ "$count" -eq 0 ]; then echo "remotion rendered no frames" >&2; exit 1; fi
kept=$(( (count + nth - 1) / nth ))
rows=$(( (kept + columns - 1) / columns ))

mkdir -p "$(dirname "$output")"
"$ffmpeg_binary" -v error -y -pattern_type glob -i "$folder/*.jpeg" \
  -vf "select=not(mod(n\,$nth)),tile=${columns}x${rows}:padding=4:color=white" -frames:v 1 -update 1 "$output"
echo "$output (frames $first_frame-$last_frame, 1 in $nth kept: $kept of $count, ${columns}x${rows})"
