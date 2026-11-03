#!/bin/zsh
# Render a reel (camera + overlays in one pass) in P parallel frame ranges, then concat losslessly.
# Usage: render_ov_parts.sh <props_abs.json> <overlays.json> <out_video_only.mp4> <total_frames> <parts>
set -e
props="$1"; ov="$2"; out="$3"; N="$4"; P="$5"
T="$(dirname "$0")"
dir="${out%.mp4}_parts"; mkdir -p "$dir"; : > "$dir/list.txt"
step=$(( (N + P - 1) / P ))
pids=()
for i in $(seq 0 $((P - 1))); do
  a=$(( i * step )); b=$(( a + step - 1 )); [ $b -ge $N ] && b=$(( N - 1 ))
  [ $a -gt $b ] && continue
  node "$T/subpixel_render_ov.mjs" "$props" "$dir/p$i.mp4" $a $b 16 "$ov" 2> "$dir/p$i.log" &
  pids+=($!)
  echo "file 'p$i.mp4'" >> "$dir/list.txt"
done
fail=0
for p in $pids; do wait $p || fail=1; done
[ $fail = 0 ] || { echo "a part failed"; tail -3 "$dir"/p*.log; exit 1; }
ffmpeg -nostdin -v error -y -f concat -safe 0 -i "$dir/list.txt" -c copy "$out"
n=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$out")
echo "$out: $n frames (expected $N)"
[ "$n" = "$N" ]
