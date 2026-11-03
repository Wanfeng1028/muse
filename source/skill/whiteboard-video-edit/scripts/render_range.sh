#!/bin/zsh
# Render output frames [A, B] of a props file in P parallel sub ranges into <parts_dir>/r_<start>.mp4 (no overlays).
# Usage: render_range.sh <props_abs.json> <parts_dir> <A> <B> <P>
set -e
props="$1"; dir="$2"; A=$3; B=$4; P=$5
T="$(dirname "$0")"; mkdir -p "$dir"
n=$(( B - A + 1 )); step=$(( (n + P - 1) / P )); pids=()
for i in $(seq 0 $((P - 1))); do
  a=$(( A + i * step )); b=$(( a + step - 1 )); [ $b -gt $B ] && b=$B; [ $a -gt $b ] && continue
  s=$(printf '%06d' $a)
  node "$T/subpixel_render.mjs" "$props" "$dir/r_$s.mp4" $a $b 16 2> "$dir/r_$s.log" &
  pids+=($!)
done
fail=0; for p in $pids; do wait $p || fail=1; done
[ $fail = 0 ] || { echo "a part failed"; tail -3 "$dir"/r_*.log; exit 1; }
tail -qn1 "$dir"/r_*.log
