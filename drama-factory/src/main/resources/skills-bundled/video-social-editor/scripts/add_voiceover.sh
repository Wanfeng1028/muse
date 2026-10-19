#!/usr/bin/env bash
# Phase 5a — mux a QuickTime face+voice recording onto the finished silent video.
#
# The recording (a QuickTime "New Movie Recording" .mov) carries BOTH the voice-over
# (its audio) and the face (its video). We overlay the face as a circular bubble in a
# user-chosen corner and use the recording's audio as the sound track. Because the user
# narrated against the playing final cut, the two are already in sync; --offset nudges
# the start if the take began a beat early or late.
#
# Usage:
#   add_voiceover.sh --video final.mp4 --rec facecam.mov --corner br --out final-vo.mp4
#
# Options:
#   --corner tl|tr|bl|br   Bubble corner (default br)
#   --size N               Bubble diameter px (default 320)
#   --pad N                Padding from frame edges px (default 40)
#   --offset S             Shift the recording (audio+face) by S seconds, +/- (default 0)
#   --ring-width N         Ring border px (default 6); 0 disables the ring
#   --no-face              Audio only — mux the voice-over, skip the bubble
set -euo pipefail

VIDEO="" REC="" OUT="" CORNER="br" SIZE=320 PAD=40 OFFSET=0 RINGW=6 NOFACE=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --video) VIDEO="$2"; shift 2;;
    --rec) REC="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --corner) CORNER="$2"; shift 2;;
    --size) SIZE="$2"; shift 2;;
    --pad) PAD="$2"; shift 2;;
    --offset) OFFSET="$2"; shift 2;;
    --ring-width) RINGW="$2"; shift 2;;
    --no-face) NOFACE=1; shift;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done
[[ -z "$VIDEO" || -z "$REC" || -z "$OUT" ]] && { echo "need --video --rec --out" >&2; exit 1; }

# --offset shifts both the recording's video and audio together.
OFFOPT=()
[[ "$OFFSET" != "0" ]] && OFFOPT=(-itsoffset "$OFFSET")

# Audio-only path: keep the video untouched, add the narration track.
if [[ "$NOFACE" == "1" ]]; then
  ffmpeg -y -i "$VIDEO" ${OFFOPT[@]+"${OFFOPT[@]}"} -i "$REC" \
    -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest "$OUT"
  echo "Done (audio only) → $OUT"
  exit 0
fi

read -r W H < <(ffprobe -v quiet -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$VIDEO" | tr ',' ' ')
case "$CORNER" in
  tl) BX=$PAD;                BY=$PAD;;
  tr) BX=$((W-SIZE-PAD));     BY=$PAD;;
  bl) BX=$PAD;                BY=$((H-SIZE-PAD));;
  br) BX=$((W-SIZE-PAD));     BY=$((H-SIZE-PAD));;
  *) echo "bad --corner: $CORNER" >&2; exit 1;;
esac

MASK="$(dirname "$OUT")/.facecam_mask.png"
if [[ "$RINGW" -gt 0 ]]; then
  RING="$(dirname "$OUT")/.facecam_ring.png"
  uv run --with pillow python "$SCRIPT_DIR/make_circle_mask.py" --size "$SIZE" --out "$MASK" \
    --ring "$RING" --ring-width "$RINGW" >/dev/null
else
  uv run --with pillow python "$SCRIPT_DIR/make_circle_mask.py" --size "$SIZE" --out "$MASK" >/dev/null
fi

# Center-crop the webcam to a square → scale → apply circular alpha → overlay at the corner.
# min(iw,ih) picks the center square for both landscape and portrait sources.
FILTER="[1:v]crop='min(iw\,ih)':'min(iw\,ih)',scale=${SIZE}:${SIZE},format=rgba[fcsq];\
[fcsq][2:v]alphamerge[fc];\
[0:v][fc]overlay=${BX}:${BY}[vb]"

INPUTS=(-i "$VIDEO" ${OFFOPT[@]+"${OFFOPT[@]}"} -i "$REC" -i "$MASK")
LAST="vb"
if [[ "$RINGW" -gt 0 ]]; then
  INPUTS+=(-i "$RING")
  FILTER="${FILTER};[vb][3:v]overlay=${BX}:${BY}[vr]"
  LAST="vr"
fi
FILTER="${FILTER};[${LAST}]format=yuv420p[out]"

ffmpeg -y "${INPUTS[@]}" -filter_complex "$FILTER" \
  -map "[out]" -map 1:a -c:v libx264 -crf 20 -preset medium -c:a aac -b:a 192k -shortest "$OUT"

rm -f "$MASK" "${RING:-}" 2>/dev/null || true
echo "Done → $OUT"
