#!/usr/bin/env bash
# mix-encode.sh [--10bit] [--embed] <work-dir> <voice-audio> <duration> <out.mp4> [music-file]
#
# mix-audio.sh mixes the soundtrack (voice, ducked clip audio and music, SFX, −14 LUFS); music-file
# overrides the music synth_audio.py recorded in mix.json.
# Draft JPEG frames encode veryfast/CRF 20 (VV_PRESET overrides the preset); --10bit encodes yuv420p10le
# High 10 against banding in dark gradients; --embed muxes captions.srt as a soft subtitle track, and any
# captions.srt/captions.vtt are copied next to the mp4.
set -euo pipefail

TEN_BIT=0
EMBED=0
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --10bit) TEN_BIT=1 ;;
    --embed) EMBED=1 ;;
    *) echo "unknown flag: $1"; echo "Next: pass --10bit or --embed first, then the work dir, voice audio, duration and output mp4"; exit 1 ;;
  esac
  shift
done

WORK="$1"
VOICE="$2"
DURATION="$3"
OUT="$4"
MUSIC="${5:-}"
FPS=30
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[[ -d "$WORK/frames" ]] || { echo "No frames in $WORK/frames"; echo "Next: run render-frames.sh"; exit 1; }
# render.js writes PNG (high) or JPEG (draft); one video must come from one kind
shopt -s nullglob
PNGS=("$WORK"/frames/f*.png); JPGS=("$WORK"/frames/f*.jpg)
shopt -u nullglob
if (( ${#PNGS[@]} > 0 && ${#JPGS[@]} > 0 )); then
  echo "frames/ mixes high-quality PNG and draft JPEG frames"
  echo "Next: re-run render-frames.sh over the whole video with one VV_QUALITY setting"
  exit 1
fi
FRAME_EXT=png
(( ${#PNGS[@]} == 0 )) && FRAME_EXT=jpg
[[ -f "$WORK/sfx.wav" ]] || { echo "No sfx.wav in $WORK"; echo "Next: run synth_audio.py"; exit 1; }

# Draft JPEGs are a throwaway preview cut, so encode speed beats the last bit of quality;
# final PNGs keep the slow preset. VV_PRESET overrides either, e.g. medium on a slow machine.
PRESET=slow
CRF=16
if [[ "$FRAME_EXT" == jpg ]]; then
  PRESET=veryfast
  CRF=20
fi
PRESET="${VV_PRESET:-$PRESET}"

# The fill scales the bitrate cap with the canvas in render.json's encode block; 16M when absent
MAXRATE_KBPS=$(python3 - "$WORK/render.json" <<'PY'
import json, sys
try:
    print(int(json.load(open(sys.argv[1]))["encode"]["maxrate_kbps"]))
except (OSError, ValueError, KeyError, TypeError):
    print(16000)
PY
)
[[ "$MAXRATE_KBPS" =~ ^[1-9][0-9]*$ ]] || MAXRATE_KBPS=16000
BUFSIZE_KBPS=$(( MAXRATE_KBPS * 2 ))

PIX_FMT=yuv420p
X264_PROFILE=()
if (( TEN_BIT )); then
  PIX_FMT=yuv420p10le
  X264_PROFILE=(-profile:v high10)
fi

if (( EMBED )); then
  [[ -f "$WORK/captions.srt" ]] || { echo "--embed needs captions.srt in $WORK"; echo "Next: run build_captions.py so it writes captions.srt, then re-run with --embed"; exit 1; }
  EMBED_ARGS=(-i "$WORK/captions.srt" -map 2 -c:s mov_text -metadata:s:s:0 language=eng)
else
  EMBED_ARGS=()
fi

bash "$SCRIPTS_DIR/mix-audio.sh" "$WORK" "$VOICE" "$DURATION" ${MUSIC:+"$MUSIC"}

TOTAL_FRAMES=$(python3 -c "import math; print(math.ceil($DURATION * $FPS))")

# Frames are RGB; convert with the BT.709 matrix and tag it, or phones shift the brand colours.
# CRF 16 on a slow preset keeps edges clean through the platform's re-encode; grain defeats CRF on
# its own, so the maxrate cap keeps a 108s vertical near 200 MB instead of 800+.
# -progress emits machine-readable blocks; the filter throttles them to a status line every few seconds.
ffmpeg -v error -nostats -progress pipe:1 -y \
  -framerate "$FPS" -i "$WORK/frames/f%05d.$FRAME_EXT" -i "$WORK/mix.wav" \
  ${EMBED_ARGS[@]+"${EMBED_ARGS[@]}"} \
  -map 0:v -map 1:a \
  -vf "scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,format=$PIX_FMT" \
  -c:v libx264 -preset "$PRESET" -crf "$CRF" ${X264_PROFILE[@]+"${X264_PROFILE[@]}"} \
  -maxrate "${MAXRATE_KBPS}k" -bufsize "${BUFSIZE_KBPS}k" -x264-params aq-mode=3 \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 256k -t "$DURATION" -movflags +faststart "$OUT" \
  | python3 -c '
import sys, time
total = int(sys.argv[1])
fields = {}
last = 0.0
for line in sys.stdin:
    key, _, value = line.partition("=")
    fields[key.strip()] = value.strip()
    if key.strip() != "progress":
        continue
    now = time.monotonic()
    if now - last < 3 and fields.get("progress") != "end":
        continue
    last = now
    frame = int(fields.get("frame") or 0)
    try:
        fps = float(fields.get("fps") or 0)
    except ValueError:
        fps = 0.0
    left = int((total - frame) / fps) if fps > 0 else 0
    print("encode: {}/{} frames · {:.0f} fps · ~{}s left".format(frame, total, fps, left), flush=True)
' "$TOTAL_FRAMES"

# Platforms index uploaded caption files; burned-in captions can't be searched, translated or switched off
BASE_OUT="${OUT%.*}"
CAPTIONS=""
for ext in srt vtt; do
  if [[ -f "$WORK/captions.$ext" ]]; then
    cp "$WORK/captions.$ext" "$BASE_OUT.$ext"
    CAPTIONS+="$ext "
  fi
done

LOUDNESS=$(ffmpeg -hide_banner -i "$WORK/mix.wav" -af ebur128 -f null - 2>&1 | awk '/I:/{v=$2} END{print v}')
INFO=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of default=nw=1 "$OUT" | tr '\n' ' ')$(ffprobe -v error -show_entries format=duration,size -of default=nw=1 "$OUT" | tr '\n' ' ')
NOTE=" · preset $PRESET"
(( TEN_BIT )) && NOTE+=" · 10-bit"
(( MAXRATE_KBPS != 16000 )) && NOTE+=" · maxrate $(( MAXRATE_KBPS / 1000 ))M"
[[ -n "$CAPTIONS" ]] && NOTE+=" · captions: ${CAPTIONS% }"
echo "$(basename "$OUT") · ${LOUDNESS} LUFS · ${INFO}${NOTE}"
# The frames dir outlives its usefulness after a verified encode; say what it costs
FRAMES_SIZE=$(du -sh "$WORK/frames" 2> /dev/null | cut -f1)
[[ -n "$FRAMES_SIZE" ]] && echo "frames/ still holds $FRAMES_SIZE — rm -rf \"$WORK/frames\" once the video is verified"
echo "Next: extract a frame from $(basename "$OUT") at a shot you changed and verify it"
