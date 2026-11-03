#!/usr/bin/env bash
# extract_clip.sh <clip> <work-dir> <vertical|landscape|WxH> <name> <edit-in> <edit-out> [--from <source-seconds>] [--audio] [--loop]
#
# Writes the frames of a fetched clip to <work-dir>/clips/<name>/fNNNNN.jpg, numbered by edit frame, so
# clip("<selector>", "<name>", in, out) in the timeline shows the right frame on every seek. The size is
# the box the clip fills: the full frame, or a picture-in-picture box like 900x620.
# --from is where in the clip to start (default 0). --audio also writes <work-dir>/clips/<name>.wav,
# placed at edit-in, which mix-encode.sh lays under the voice. --loop repeats a clip shorter than the shot,
# for gifs; without it a clip that runs out early is an error.
set -euo pipefail

if (( $# < 6 )); then
  echo "Usage: extract_clip.sh <clip> <work> <vertical|landscape|WxH> <name> <in> <out> [--from s] [--audio] [--loop]"
  echo "Next: pass all six positional arguments"
  exit 1
fi
CLIP="$1"
WORK="$2"
SIZE="$3"
NAME="$4"
EDIT_IN="$5"
EDIT_OUT="$6"
shift 6
FROM=0
AUDIO=0
LOOP=0
FPS=30

while (( $# > 0 )); do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --audio) AUDIO=1; shift ;;
    --loop) LOOP=1; shift ;;
    *) echo "Unknown option: $1"; echo "Next: use --from <seconds>, --audio and/or --loop"; exit 1 ;;
  esac
done

[[ -f "$CLIP" ]] || { echo "No such clip: $CLIP"; echo "Next: fetch it with find_media.py fetch"; exit 1; }
[[ "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "Clip name must be lowercase letters, digits and dashes, got: $NAME"; echo "Next: e.g. torvalds-keynote"; exit 1; }
case "$SIZE" in
  vertical) WIDTH=1080; HEIGHT=1920 ;;
  landscape) WIDTH=1920; HEIGHT=1080 ;;
  *x*) WIDTH="${SIZE%x*}"; HEIGHT="${SIZE#*x}" ;;
  *) echo "Unknown size: $SIZE"; echo "Next: pass vertical, landscape, or the box size like 900x620"; exit 1 ;;
esac
[[ "$WIDTH" =~ ^[0-9]+$ && "$HEIGHT" =~ ^[0-9]+$ ]] || { echo "Size must be WxH in pixels, got: $SIZE"; echo "Next: e.g. 900x620"; exit 1; }

LENGTH=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$CLIP")
RANGE=$(python3 - "$EDIT_IN" "$EDIT_OUT" "$FROM" "$LENGTH" "$FPS" "$LOOP" <<'PY'
import math, sys
start, end, source, length, fps, loop = (float(v) for v in sys.argv[1:])
if not 0 <= start < end:
    sys.exit(f"Clip range {start}-{end} is empty or negative")
if source < 0 or source >= length:
    sys.exit(f"--from {source}s is outside the {length:.2f}s clip")
if loop:
    length = math.inf
if source + (end - start) > length + 0.01:
    sys.exit(f"The clip needs {end - start:.2f}s from {source}s, but the file is only {length:.2f}s long (a gif? add --loop)")
first = math.floor(start * fps)
# renderAt rounds t*30, so the frame just before the out point can be ceil(end*30)
last = math.ceil(end * fps)
count = last - first + 1 if loop else min(last - first + 1, math.floor((length - source) * fps))
print(first, count, f"{source:.6f}", f"{end - start:.6f}", f"{start:.6f}")
PY
) || { echo "Next: shorten the shot, or move --from earlier"; exit 1; }
read -r FIRST COUNT SEEK SPAN START <<< "$RANGE"

if (( LOOP && AUDIO )); then
  echo "--loop and --audio together would repeat the sound"
  echo "Next: drop --audio; a looping gif plays silent"
  exit 1
fi
LOOP_INPUT=()
(( LOOP )) && LOOP_INPUT=(-stream_loop -1)

rm -rf "${WORK:?}/clips/$NAME" "$WORK/clips/$NAME.wav"
mkdir -p "$WORK/clips/$NAME"
ffmpeg -v error -y "${LOOP_INPUT[@]}" -ss "$SEEK" -i "$CLIP" -an \
  -vf "fps=$FPS,scale=$WIDTH:$HEIGHT:force_original_aspect_ratio=increase:flags=lanczos,crop=$WIDTH:$HEIGHT,setsar=1" \
  -frames:v "$COUNT" -start_number "$FIRST" -q:v 2 "$WORK/clips/$NAME/f%05d.jpg"
written=$(find "$WORK/clips/$NAME" -name 'f*.jpg' | wc -l)
echo "clip $NAME ${EDIT_IN}-${EDIT_OUT}s from ${FROM}s → $written frames ($FIRST…$(( FIRST + written - 1 ))) at ${WIDTH}x${HEIGHT}"
if (( written < COUNT )); then
  echo "Next: the clip ran out early; shorten the shot or move --from earlier, then re-run"
  exit 1
fi

if (( AUDIO )); then
  if ! ffprobe -v error -select_streams a:0 -show_entries stream=codec_type -of csv=p=0 "$CLIP" | grep -q audio; then
    echo "$CLIP has no audio track"
    echo "Next: drop --audio; the clip plays silent under the voice"
    exit 1
  fi
  DELAY_MS=$(python3 -c "print(round(float('$START') * 1000))")
  # Levelled to the voice's loudness so a speaking clip sits at the same volume as the narration
  ffmpeg -v error -y -ss "$SEEK" -t "$SPAN" -i "$CLIP" -vn \
    -af "loudnorm=I=-16:TP=-2,aresample=48000,afade=t=in:d=0.08,areverse,afade=t=in:d=0.12,areverse,adelay=${DELAY_MS}:all=1" \
    -ac 2 -ar 48000 "$WORK/clips/$NAME.wav"
  echo "clip audio → $WORK/clips/$NAME.wav, starting at ${EDIT_IN}s"
fi
echo "Next: author the shot with clip(\"<img selector>\", \"$NAME\", $EDIT_IN, $EDIT_OUT) using the same times"
