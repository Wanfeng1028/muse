#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
export_platforms.sh: derive platform deliverables from one master and report size, duration and cap warnings.

Usage: export_platforms.sh <master.mp4> [targets...] [options]
Targets (default: all): youtube x linkedin web gif poster
  youtube   H.264 high, CRF 18, preset slow, GOP = fps/2, 2 B-frames, audio copied if AAC (else AAC 320k)
  x         H.264 main, CRF 24, long side <= 1280, AAC 128k
  linkedin  H.264 high, CRF 22, long side <= 1920, AAC 192k
  web       MP4 (H.264 main, CRF 26, long side <= 1280, AAC 128k) + WebM (VP9 CRF 30, Opus 128k)
  gif       preview loop: --gif-seconds from --gif-start, 15 fps, --gif-width wide, palette
  poster    PNG of the frame at --poster-time (default 0, the chat thumbnail frame)
Options:
  --out-dir DIR          default out/deliver
  --name BASE            output base name (default: the master's file name)
  --gif-start S          default 0      --gif-seconds S   default 6      --gif-width PX   default 480
  --poster-time S        default 0
  --max-seconds T=N      override a duration cap (seconds, 0 = none), repeatable
  --max-mb T=N           override a size cap (MB, 0 = none), repeatable
Default caps (x 140 s / 512 MB, linkedin 600 s / 5120 MB, web 15 MB, gif 10 MB) are a starting point only:
platform limits change often, so verify the current ones before delivery and pass them with --max-*.
All MP4s: yuv420p, BT.709 tags, 48 kHz audio, +faststart. Outputs: <out-dir>/<base>-<target>.<ext>.
Example: export_platforms.sh out/final/film-16x9.mp4 youtube x gif --gif-start 2 --max-seconds x=140
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
if [ "$#" -lt 1 ]; then usage >&2; exit 2; fi

master="$1"; shift
[ -f "$master" ] || { echo "master not found: $master" >&2; exit 1; }
targets=(); out_dir="out/deliver"; base=""; gif_start=0; gif_seconds=6; gif_width=480; poster_time=0; cap_overrides=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    youtube|x|linkedin|web|gif|poster) targets+=("$1"); shift ;;
    --out-dir) out_dir="$2"; shift 2 ;;
    --name) base="$2"; shift 2 ;;
    --gif-start) gif_start="$2"; shift 2 ;;
    --gif-seconds) gif_seconds="$2"; shift 2 ;;
    --gif-width) gif_width="$2"; shift 2 ;;
    --poster-time) poster_time="$2"; shift 2 ;;
    --max-seconds) cap_overrides="$cap_overrides"$'\n'"seconds:$2"; shift 2 ;;
    --max-mb) cap_overrides="$cap_overrides"$'\n'"mb:$2"; shift 2 ;;
    *) echo "unknown target or option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[ "${#targets[@]}" -gt 0 ] || targets=(youtube x linkedin web gif poster)

ffmpeg_binary=$(resolve_tool FFMPEG ffmpeg)
ffprobe_binary=$(resolve_tool FFPROBE ffprobe)
base="${base:-$(basename "${master%.*}")}"
mkdir -p "$out_dir"

probe_value() { "$ffprobe_binary" -v error -select_streams "$1" -show_entries "$2" -of csv=p=0 "$3" | head -1 | tr -d ',\r'; }
fps=$(probe_value v:0 stream=avg_frame_rate "$master" | awk -F/ '{ if ($2 > 0) printf "%d", $1 / $2 + 0.5; else printf "%d", $1 }')
audio_codec=$(probe_value a:0 stream=codec_name "$master" || true)
gop=$(( fps / 2 > 0 ? fps / 2 : 1 ))

default_cap() {
  case "$1:$2" in
    seconds:x) echo 140 ;; mb:x) echo 512 ;;
    seconds:linkedin) echo 600 ;; mb:linkedin) echo 5120 ;;
    mb:web) echo 15 ;; mb:gif) echo 10 ;;
    *) echo 0 ;;
  esac
}

cap_for() {
  local kind="$1" target="$2" line value
  value=$(default_cap "$kind" "$target")
  while IFS= read -r line; do
    case "$line" in "$kind:$target="*) value="${line#*=}" ;; esac
  done <<< "$cap_overrides"
  echo "$value"
}

colour_args=(-pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv)
colour_filter="setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
fit_filter() { echo "scale='if(gte(iw,ih),min(iw,$1),-2)':'if(gte(iw,ih),-2,min(ih,$1))':flags=lanczos,$colour_filter"; }
encode() { "$ffmpeg_binary" -v error -y -i "$master" "$@"; }

warnings=()
report() {
  local target="$1" path="$2" bytes megabytes duration size_cap seconds_cap dimensions
  bytes=$(wc -c < "$path" | tr -d ' ')
  megabytes=$(awk -v b="$bytes" 'BEGIN { printf "%.2f", b / 1048576 }')
  duration=$(probe_value v:0 stream=duration "$path" || true)
  [ -n "$duration" ] && [ "$duration" != "N/A" ] || duration=$("$ffprobe_binary" -v error -show_entries format=duration -of csv=p=0 "$path" | tr -d '\r')
  [ -n "$duration" ] && [ "$duration" != "N/A" ] || duration=0
  dimensions=$("$ffprobe_binary" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$path" | head -1)
  printf '%-9s %s  %s MB  %.2f s  %s\n' "$target" "$path" "$megabytes" "$duration" "$dimensions"
  size_cap=$(cap_for mb "$target"); seconds_cap=$(cap_for seconds "$target")
  if awk -v v="$megabytes" -v c="$size_cap" 'BEGIN { exit !(c > 0 && v > c) }'; then
    warnings+=("$target: $megabytes MB exceeds the $size_cap MB cap")
  fi
  if awk -v v="$duration" -v c="$seconds_cap" 'BEGIN { exit !(c > 0 && v > c) }'; then
    warnings+=("$target: $duration s exceeds the $seconds_cap s cap")
  fi
}

export_youtube() {
  local path="$out_dir/$base-youtube.mp4" audio=(-c:a aac -b:a 320k -ar 48000)
  [ "$audio_codec" = "aac" ] && audio=(-c:a copy)
  encode -map 0:v:0 -map '0:a:0?' -vf "$colour_filter" -c:v libx264 -preset slow -crf 18 -profile:v high -bf 2 -g "$gop" \
    "${colour_args[@]}" "${audio[@]}" -movflags +faststart "$path"
  report youtube "$path"
}

export_h264() {
  local target="$1" long_side="$2" crf="$3" profile="$4" audio_rate="$5" path="$out_dir/$base-$1.mp4"
  encode -map 0:v:0 -map '0:a:0?' -vf "$(fit_filter "$long_side")" -c:v libx264 -preset slow -crf "$crf" -profile:v "$profile" \
    "${colour_args[@]}" -c:a aac -b:a "$audio_rate" -ar 48000 -movflags +faststart "$path"
  report "$target" "$path"
}

export_webm() {
  local path="$out_dir/$base-web.webm"
  if ! "$ffmpeg_binary" -hide_banner -encoders 2>/dev/null | grep -q libvpx-vp9; then
    warnings+=("web: this ffmpeg has no libvpx-vp9, WebM skipped"); return
  fi
  encode -map 0:v:0 -map '0:a:0?' -vf "$(fit_filter 1280)" -c:v libvpx-vp9 -crf 30 -b:v 0 -row-mt 1 -deadline good -cpu-used 4 \
    "${colour_args[@]}" -c:a libopus -b:a 128k -ar 48000 "$path"
  report web "$path"
}

export_gif() {
  local path="$out_dir/$base-preview.gif"
  "$ffmpeg_binary" -v error -y -ss "$gif_start" -t "$gif_seconds" -i "$master" -filter_complex \
    "fps=15,scale=$gif_width:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a" \
    -loop 0 "$path"
  report gif "$path"
}

export_poster() {
  local path="$out_dir/$base-poster.png"
  "$ffmpeg_binary" -v error -y -ss "$poster_time" -i "$master" -frames:v 1 -update 1 "$path"
  printf '%-9s %s  %s\n' poster "$path" "$("$ffprobe_binary" -v error -show_entries stream=width,height -of csv=p=0:s=x "$path")"
}

for target in "${targets[@]}"; do
  case "$target" in
    youtube) export_youtube ;;
    x) export_h264 x 1280 24 main 128k ;;
    linkedin) export_h264 linkedin 1920 22 high 192k ;;
    web) export_h264 web 1280 26 main 128k; export_webm ;;
    gif) export_gif ;;
    poster) export_poster ;;
  esac
done

if [ "${#warnings[@]}" -gt 0 ]; then
  printf 'WARN: %s\n' "${warnings[@]}"
  echo "Caps are defaults; verify current platform limits and pass them with --max-seconds/--max-mb."
fi
