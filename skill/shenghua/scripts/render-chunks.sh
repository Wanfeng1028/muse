#!/usr/bin/env bash
# render-chunks.sh [--blur N] [--resolution 1080|4k] [--force] [--workers N] [--chunk SECONDS] [--music FILE] [--png]
#                  <index.html> <work-dir> <duration-seconds> <voice-audio> <out.mp4>
#
# Renders and encodes in chunks (default 30 s). By default each chunk's frames stream straight from
# Chromium into ffmpeg (render.js stream | ffmpeg -f image2pipe), so no frames directory ever exists
# — peak scratch is the chunk mp4s, not the ~21 GB of PNGs a 7-minute final used to need. Chunks are
# concatenated without re-encoding and the audio is mixed and muxed once. A killed run re-encodes
# only chunks whose mp4 is missing or has the wrong frame count; a chunk killed mid-stream is
# re-rendered from its first frame.
# --png (or VV_PNG_FRAMES=1) keeps the old path — render.js frames writes PNGs to <work-dir>/frames,
# then ffmpeg encodes them — for debugging (contact sheets, re-rendering a single frame by number).
set -euo pipefail

RF_OPTS=()
FORCE=0
WORKERS=10
CHUNK=30
MUSIC=""
BLUR=1
SCALE=""
PNG="${VV_PNG_FRAMES:-0}"
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --blur) BLUR="${2:?--blur needs a value}"; RF_OPTS+=(--blur "$BLUR"); shift 2 ;;
    --resolution) SCALE="${2:?--resolution needs a value}"; RF_OPTS+=(--resolution "$SCALE"); shift 2 ;;
    --force) FORCE=1; shift ;;
    --workers) WORKERS="${2:?--workers needs a value}"; shift 2 ;;
    --chunk) CHUNK="${2:?--chunk needs a value}"; shift 2 ;;
    --music) MUSIC="${2:?--music needs a value}"; shift 2 ;;
    --png) PNG=1; shift ;;
    *) echo "Unknown option: $1"
       echo "Next: options are --blur N, --resolution 1080|4k, --force, --workers N, --chunk SECONDS, --music FILE and --png"
       exit 1 ;;
  esac
done

if (( $# != 5 )); then
  echo "Usage: render-chunks.sh [options] <index.html> <work-dir> <duration-seconds> <voice-audio> <out.mp4>"
  echo "Next: pass the five positional arguments; options come first"
  exit 1
fi
HTML="$1"
WORK="$2"
DURATION="$3"
VOICE="$4"
OUT="$5"
FPS=30
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[[ -f "$HTML" ]] || { echo "No such composition: $HTML"; echo "Next: run fill_template.py first"; exit 1; }
[[ -f "$VOICE" ]] || { echo "No such voice audio: $VOICE"; echo "Next: pass the voice.wav from trim_take.py (or the original recording)"; exit 1; }
[[ -f "$WORK/sfx.wav" ]] || { echo "No sfx.wav in $WORK"; echo "Next: run synth_audio.py"; exit 1; }
if ! [[ "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "workers must be a positive integer, got: $WORKERS"
  echo "Next: pass a positive integer like 8 or 10"
  exit 1
fi
if ! [[ "$CHUNK" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "--chunk must be a positive number of seconds, got: $CHUNK"
  echo "Next: e.g. --chunk 30"
  exit 1
fi
read -r TOTAL CHUNK_FRAMES <<< "$(python3 -c "
import math
print(math.ceil($DURATION * $FPS), max(1, round($CHUNK * $FPS)))")"

# The fill scales the bitrate cap with the canvas in render.json's encode block; 16M when absent
MAXRATE_KBPS=$(python3 - "$(dirname "$HTML")/render.json" <<'PY'
import json, sys
try:
    print(int(json.load(open(sys.argv[1]))["encode"]["maxrate_kbps"]))
except (OSError, ValueError, KeyError, TypeError):
    print(16000)
PY
)
[[ "$MAXRATE_KBPS" =~ ^[1-9][0-9]*$ ]] || MAXRATE_KBPS=16000
BUFSIZE_KBPS=$(( MAXRATE_KBPS * 2 ))

[[ "$PNG" == "1" ]] || PNG=0

EXT=png
[[ "${VV_QUALITY:-}" == "draft" ]] && EXT=jpg

CHUNKS_DIR="$WORK/chunks"
mkdir -p "$CHUNKS_DIR"
(( PNG )) && mkdir -p "$WORK/frames"

# A finished chunk has exactly its frames in the container; a killed encode leaves fewer and is redone
chunk_ok() {
  [[ -f "$1" ]] || return 1
  local n
  n=$(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of csv=p=0 "$1" 2>/dev/null)
  [[ "$n" =~ ^[0-9]+$ && "$n" == "$2" ]]
}

CHUNK_COUNT=$(( (TOTAL + CHUNK_FRAMES - 1) / CHUNK_FRAMES ))
(( FORCE )) && RF_OPTS+=(--force)

if (( PNG )); then
for (( c = 0; c < CHUNK_COUNT; c++ )); do
  FIRST=$(( c * CHUNK_FRAMES ))
  LAST=$(( FIRST + CHUNK_FRAMES < TOTAL ? FIRST + CHUNK_FRAMES : TOTAL ))
  WANT=$(( LAST - FIRST ))
  CHUNK_MP4="$CHUNKS_DIR/$(printf 'chunk-%03d.mp4' "$c")"
  if (( ! FORCE )) && chunk_ok "$CHUNK_MP4" "$WANT"; then
    echo "chunk $(( c + 1 ))/$CHUNK_COUNT already encoded ($WANT frames) — skipped"
    continue
  fi
  VV_FROM_CHUNKS=1 bash "$SCRIPTS_DIR/render-frames.sh" ${RF_OPTS[@]+"${RF_OPTS[@]}"} \
    "$HTML" "$WORK/frames" "$DURATION" "$WORKERS" "$FIRST" "$LAST"
  # Same video settings as mix-encode.sh, minus the audio; the tmp file keeps a killed encode
  # from looking complete, and chunk_ok's frame count is the second line of defence
  ffmpeg -v error -y -framerate "$FPS" -start_number "$FIRST" -i "$WORK/frames/f%05d.$EXT" \
    -frames:v "$WANT" -an \
    -vf "scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p" \
    -c:v libx264 -preset slow -crf 16 -maxrate "${MAXRATE_KBPS}k" -bufsize "${BUFSIZE_KBPS}k" -x264-params aq-mode=3 \
    -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
    "$CHUNK_MP4.tmp.mp4"
  mv "$CHUNK_MP4.tmp.mp4" "$CHUNK_MP4"
  for (( f = FIRST; f < LAST; f++ )); do rm -f "$WORK/frames/$(printf 'f%05d' "$f").$EXT"; done
  echo "chunk $(( c + 1 ))/$CHUNK_COUNT encoded ($WANT frames)"
done
else
# Streamed default: no frames directory at all, so there is no frame-disk cost to estimate
echo "$TOTAL frames in $CHUNK_COUNT chunk(s) · streamed Chromium → ffmpeg · ~0 GB frame disk"

# --resolution wins; otherwise the fill's render.json decides, as render-frames.sh does
if [[ -z "$SCALE" ]]; then
  RENDER_JSON="$(dirname "$HTML")/render.json"
  if [[ -f "$RENDER_JSON" ]]; then
    SCALE=$(python3 -c "
import json, sys
try: print(json.load(open(sys.argv[1])).get('scale', 1))
except (OSError, ValueError): print(1)" "$RENDER_JSON")
    [[ "$SCALE" =~ ^[12]$ ]] || SCALE=1
  else
    SCALE=1
  fi
fi
case "$SCALE" in
  1080|1080p|1) SCALE=1 ;;
  4k|2160|2160p|2) SCALE=2 ;;
  *) echo "--resolution must be 1080 or 4k, got: $SCALE"
     echo "Next: pass --resolution 4k for a 4K master, or drop it for 1080p"
     exit 1 ;;
esac
# render.js reads VV_SCALE: 1 supersamples the 2x device pixels to 1x, 2 keeps them (4K master)
export VV_SCALE="$SCALE"
# render.js stream writes JPEG bytes under VV_QUALITY=draft, PNG otherwise; name the decoder so the
# pipe never depends on ffmpeg's probe
VCODEC=png
[[ "$EXT" == jpg ]] && VCODEC=mjpeg

# Chunks are independent mp4s, so the parallelism moves from frames-within-a-chunk to whole chunks:
# up to WORKERS render→encode pipelines run at once, and concat restores the order
pids=()
failed=0
for (( c = 0; c < CHUNK_COUNT; c++ )); do
  FIRST=$(( c * CHUNK_FRAMES ))
  LAST=$(( FIRST + CHUNK_FRAMES < TOTAL ? FIRST + CHUNK_FRAMES : TOTAL ))
  WANT=$(( LAST - FIRST ))
  CHUNK_MP4="$CHUNKS_DIR/$(printf 'chunk-%03d.mp4' "$c")"
  if (( ! FORCE )) && chunk_ok "$CHUNK_MP4" "$WANT"; then
    echo "chunk $(( c + 1 ))/$CHUNK_COUNT already encoded ($WANT frames) — skipped"
    continue
  fi
  (
    # Bounds are separate arguments, as in render-frames.sh: one quoted "a b" renders zero frames
    node "$SCRIPTS_DIR/render.js" stream "$HTML" "$FIRST" "$LAST" "$BLUR" | \
    # Same video settings as mix-encode.sh, minus the audio; the tmp file keeps a killed encode
    # from looking complete, and chunk_ok's frame count is the second line of defence
    ffmpeg -v error -y -f image2pipe -vcodec "$VCODEC" -framerate "$FPS" -i - \
      -frames:v "$WANT" -an \
      -vf "scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p" \
      -c:v libx264 -preset slow -crf 16 -maxrate "${MAXRATE_KBPS}k" -bufsize "${BUFSIZE_KBPS}k" -x264-params aq-mode=3 \
      -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
      "$CHUNK_MP4.tmp.mp4" && \
    mv "$CHUNK_MP4.tmp.mp4" "$CHUNK_MP4" && \
    echo "chunk $(( c + 1 ))/$CHUNK_COUNT encoded ($WANT frames)"
  ) &
  pids+=($!)
  while (( $(jobs -rp | wc -l) >= WORKERS )); do sleep 1; done
done
for pid in "${pids[@]:-}"; do [[ -n "$pid" ]] && { wait "$pid" || failed=$(( failed + 1 )); }; done
if (( failed > 0 )); then
  echo "$failed of $CHUNK_COUNT chunk(s) failed"
  echo "Next: fix the first error printed above (PAGE ERROR = composition bug, Executable doesn't exist = run setup.sh), then re-run — complete chunks are skipped"
  exit 1
fi
fi

# Identical codec and settings in every chunk, so the concat demuxer can copy without re-encoding
CONCAT="$CHUNKS_DIR/concat.txt"
: > "$CONCAT"
for (( c = 0; c < CHUNK_COUNT; c++ )); do
  printf "file '%s'\n" "$(printf 'chunk-%03d.mp4' "$c")" >> "$CONCAT"
done
ffmpeg -v error -y -f concat -safe 0 -i "$CONCAT" -c copy "$CHUNKS_DIR/video.mp4"

bash "$SCRIPTS_DIR/mix-audio.sh" "$WORK" "$VOICE" "$DURATION" ${MUSIC:+"$MUSIC"}

ffmpeg -v error -y -i "$CHUNKS_DIR/video.mp4" -i "$WORK/mix.wav" \
  -map 0:v -map 1:a -c:v copy \
  -c:a aac -b:a 256k -t "$DURATION" -movflags +faststart "$OUT"

LOUDNESS=$(ffmpeg -hide_banner -i "$WORK/mix.wav" -af ebur128 -f null - 2>&1 | awk '/I:/{v=$2} END{print v}')
INFO=$(ffprobe -v error -show_entries stream=width,height:format=duration,size -of default=nw=1 "$OUT" | tr '\n' ' ')
echo "$(basename "$OUT") · ${LOUDNESS} LUFS · ${INFO}"
echo "Next: extract a frame from $(basename "$OUT") at a shot you changed and verify it"
