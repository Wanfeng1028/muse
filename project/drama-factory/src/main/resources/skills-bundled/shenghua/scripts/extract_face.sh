#!/usr/bin/env bash
# extract_face.sh <video> <work-dir> <vertical|landscape> <from> <to> [<from> <to> …]
#
# Writes the camera frames for each face shot to <work-dir>/face/fNNNNN.jpg, numbered by edit frame,
# so frame N of the edit shows frame N of the recording and voice and lips stay in sync.
# When <work-dir>/take.json exists (trim_take.py ran), the from/to times are edit times and the
# source seek is shifted by its firstFrame; without it the video is read untrimmed, as before.
set -euo pipefail

VIDEO="$1"
WORK="$2"
FORMAT="$3"
shift 3
FPS=30

[[ -f "$VIDEO" ]] || { echo "No such video: $VIDEO"; echo "Next: pass the to-camera recording the audio came from"; exit 1; }
case "$FORMAT" in
  vertical) WIDTH=1080; HEIGHT=1920 ;;
  landscape) WIDTH=1920; HEIGHT=1080 ;;
  *) echo "Unknown format: $FORMAT"; echo "Next: pass vertical or landscape"; exit 1 ;;
esac
if (( $# == 0 || $# % 2 != 0 )); then
  echo "Face ranges come in <from> <to> pairs, got $# value(s)"
  echo "Next: e.g. extract_face.sh take.mp4 work vertical 0 2.4 84.1 87.6"
  exit 1
fi
if ! ffprobe -v error -select_streams v:0 -show_entries stream=codec_type -of csv=p=0 "$VIDEO" | grep -q video; then
  echo "$VIDEO has no video stream"
  echo "Next: record to camera, or run the skill with audio only and no face shots"
  exit 1
fi

LENGTH=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO")
labels=()
ranges=()

# Validate every pair before extracting any, so a bad sign-off range doesn't leave a half-written face/
while (( $# >= 2 )); do
  FROM="$1"; TO="$2"; shift 2
  RANGE=$(python3 - "$FROM" "$TO" "$LENGTH" "$FPS" "$WORK/take.json" <<'PY'
import json, math, os, sys
start, end, length, fps = (float(v) for v in sys.argv[1:5])
# trim_take.py cut the take so edit t=0 is source frame firstFrame; face frames stay edit-numbered
offset = 0
take_path = sys.argv[5]
if os.path.isfile(take_path):
    with open(take_path, encoding="utf-8") as handle:
        take = json.load(handle)
    offset = int(take["firstFrame"])
    length = float(take["duration"])
if not 0 <= start < end:
    sys.exit(f"Face range {start}-{end} is empty or negative")
if end > length:
    sys.exit(f"Face range ends at {end}s but the take is only {length:.2f}s")
first = math.floor(start * fps)
# renderAt rounds t*30, so the frame just before the shot's out point can be ceil(end*30)
last = min(math.ceil(end * fps), math.ceil(length * fps) - 1)
print(first, last - first + 1, f"{(offset + first) / fps:.6f}")
PY
  ) || { echo "Next: end the face shot at or before the take's length (after trimming, the take.json duration)"; exit 1; }
  labels+=("${FROM}-${TO}s")
  ranges+=("$RANGE")
done

mkdir -p "$WORK/face"
expected=0

for i in "${!ranges[@]}"; do
  read -r FIRST COUNT SEEK <<< "${ranges[$i]}"
  ffmpeg -v error -y -ss "$SEEK" -i "$VIDEO" -an \
    -vf "fps=$FPS,scale=$WIDTH:$HEIGHT:force_original_aspect_ratio=increase:flags=lanczos,crop=$WIDTH:$HEIGHT,setsar=1" \
    -frames:v "$COUNT" -start_number "$FIRST" -q:v 2 "$WORK/face/f%05d.jpg"
  echo "face ${labels[$i]} → frames $FIRST…$(( FIRST + COUNT - 1 ))"
  expected=$(( expected + COUNT ))
done

# Every expected filename is known, so count those; portable where find -newermt "@…" is GNU-only
written=$(python3 - "$WORK/face" "${ranges[@]}" <<'PY'
import os, sys
d = sys.argv[1]
n = 0
for spec in sys.argv[2:]:
    first, count = spec.split()[:2]
    n += sum(os.path.isfile(os.path.join(d, f"f{f:05d}.jpg"))
             for f in range(int(first), int(first) + int(count)))
print(n)
PY
)
echo "$written/$expected face frames → $WORK/face"
if (( written < expected )); then
  echo "Next: the recording ran out early; end the face shot sooner and re-run with the same pairs"
  exit 1
fi
echo "Next: author each face shot with faceCam(id, from, to) using the same times"
