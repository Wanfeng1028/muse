#!/bin/zsh
# Render a reel's headline variants in one pass of work: the frames after the headline (identical in
# every variant) are rendered ONCE in P parallel parts; frames 0 to HF-1 are rendered per variant.
# Each variant = its own head part + the shared tail parts, concatenated losslessly (every part is its
# own encode that starts on a keyframe), so the variants are byte identical after the headline.
# Usage: render_variants.sh <props_abs.json> <overlay_dir> <out_dir> <total_frames> <head_frames> <P> [stage]
#   overlay_dir holds overlays_h1.json .. overlays_hK.json (overlay_build.py)
#   stage: tail | heads | concat | all (default all), so a slow machine can run it in bounded steps
set -e
props="$1"; ov="$2"; out="$3"; N="$4"; HF="$5"; P="$6"; stage="${7:-all}"
T="$(dirname "$0")"
mkdir -p "$out/parts"
variants=( $(cd "$ov" && ls overlays_h*.json 2>/dev/null | sed 's/overlays_\(h[0-9]*\)\.json/\1/' | sort) )
[ ${#variants} -gt 0 ] || { echo "no overlays_h*.json in $ov (run overlay_build.py first)"; exit 1; }
if [[ $stage == tail || $stage == all ]]; then
  n=$(( N - HF )); step=$(( (n + P - 1) / P )); pids=()
  for i in $(seq 0 $((P - 1))); do
    a=$(( HF + i * step )); b=$(( a + step - 1 )); [ $b -ge $N ] && b=$(( N - 1 )); [ $a -gt $b ] && continue
    s=$(printf '%05d' $a)
    node "$T/subpixel_render_ov.mjs" "$props" "$out/parts/t_$s.mp4" $a $b 16 "$ov/overlays_h1.json" 2> "$out/parts/t_$s.log" &
    pids+=($!)
  done
  fail=0; for p in $pids; do wait $p || fail=1; done
  [ $fail = 0 ] || { echo "a tail part failed"; tail -3 "$out"/parts/t_*.log; exit 1; }
  tail -qn1 "$out"/parts/t_*.log
fi
if [[ $stage == heads || $stage == all ]]; then
  pids=()
  for v in $variants; do
    node "$T/subpixel_render_ov.mjs" "$props" "$out/parts/head_$v.mp4" 0 $(( HF - 1 )) 16 "$ov/overlays_$v.json" 2> "$out/parts/head_$v.log" &
    pids+=($!)
  done
  fail=0; for p in $pids; do wait $p || fail=1; done
  [ $fail = 0 ] || { echo "a head part failed"; tail -3 "$out"/parts/head_*.log; exit 1; }
  tail -qn1 "$out"/parts/head_*.log
fi
if [[ $stage == concat || $stage == all ]]; then
  for v in $variants; do
    { echo "file 'parts/head_$v.mp4'"; for t in $(cd "$out" && ls parts/t_*.mp4); do echo "file '$t'"; done; } > "$out/list_$v.txt"
    ffmpeg -nostdin -v error -y -f concat -safe 0 -i "$out/list_$v.txt" -c copy "$out/video_$v.mp4"
    n=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$out/video_$v.mp4")
    echo "$out/video_$v.mp4: $n frames (expected $N)"
    [ "$n" = "$N" ]
  done
fi
