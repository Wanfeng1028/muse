#!/bin/zsh
# Polished audio swap with a sync proof: cross correlate the camera audio against the polished WAV
# in three 40 s windows (start, middle, end; mono 8 kHz, sub sample peak, xcorr.mjs) and, when every
# offset and the drift are inside one frame (42 ms), mux the camera video stream COPIED (never a 4K
# re-encode) with the WAV. Otherwise it stops and prints the offsets: shift (and if drifting, stretch)
# the WAV yourself, then run it again.
# Usage: audio_swap.sh <camera_video> <polished.wav> <out_master.mov> <work_dir>
# Writes <work_dir>/sync-proof.json. Exit 0 muxed, 1 usage, 2 out of sync (nothing muxed).
set -u
cam="$1"; wav="$2"; out="$3"; wd="$4"
[ -f "$cam" ] && [ -f "$wav" ] || { echo "usage: audio_swap.sh <camera_video> <polished.wav> <out_master.mov> <work_dir>"; exit 1; }
T="$(dirname "$0")"; mkdir -p "$wd"
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$cam")
rows=()
for st in $(python3 -c "print(*sorted({0, max(0, int($dur / 2) - 20), max(0, int($dur) - 45)}))"); do  # start, middle, end (fewer on a short file)
  ffmpeg -nostdin -v error -y -ss $st -t 40 -i "$cam" -map 0:a:0 -ac 1 -ar 8000 -f s16le "$wd/cam_$st.raw"
  ffmpeg -nostdin -v error -y -ss $st -t 40 -i "$wav" -ac 1 -ar 8000 -f s16le "$wd/wav_$st.raw"
  r=$(node "$T/xcorr.mjs" "$wd/cam_$st.raw" "$wd/wav_$st.raw" 8000 500)
  rows+=("{\"window_s\": $st, \"result\": $r}")
  printf 'window %s s: %s\n' $st "$r"
done
printf '[%s]\n' "${(j:, :)rows}" > "$wd/sync-proof.json"
verdict=$(python3 -c "
import json; r=json.load(open('$wd/sync-proof.json')); ms=[x['result']['lagMs'] for x in r]
ok = all(abs(m) < 42 for m in ms) and max(ms) - min(ms) < 42
print(('IN SYNC' if ok else 'OUT OF SYNC') + f': offsets {ms} ms, drift {max(ms) - min(ms):.3f} ms')")
echo "$verdict"
[[ $verdict == IN* ]] || exit 2
ffmpeg -nostdin -v error -y -i "$cam" -i "$wav" -map 0:v:0 -map 1:a:0 -c:v copy -c:a pcm_s16le "$out" || exit 2
echo "muxed $out (video stream copied)"
