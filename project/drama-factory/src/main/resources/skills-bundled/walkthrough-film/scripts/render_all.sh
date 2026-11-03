#!/bin/bash
# Render EVERY scene of the film with render_scene_step.mjs, N scenes at a time (N Chrome instances).
#
# INPUT   $TIMING (timing.json) and a page that exposes seek()/render()
# OUTPUT  $FILM_ROOT/renders_${VER}/NN_<id>.mp4  +  renders_${VER}/_logs/NN_<id>.log
#
#   VER=v3 THEME=light WORKERS=3 bash render_all.sh
#
# SKIP-EXISTING is the whole re-render workflow: after changing one scene, delete that scene's clip
# (and its twin in warped_${VER}/) and run this again — everything else is left alone.
# WARNING: an interrupted render leaves a truncated MP4 that looks "existing". Probe durations and
# delete the broken ones before resuming (see the probe loop at the bottom).

set -e
FILM_ROOT=${FILM_ROOT:-$(pwd)}
cd "$FILM_ROOT"
TIMING=${TIMING:-$FILM_ROOT/audio/timing.json}
VER=${VER:-v1}
WORKERS=${WORKERS:-3}
SCRIPT=${SCRIPT:-$FILM_ROOT/scripts/render_scene_step.mjs}

OUT="$FILM_ROOT/renders_${VER}"
LOG="$OUT/_logs"
mkdir -p "$LOG"

N=$(node -e "console.log(require('$TIMING').scenes.length)")
echo "rendering $N scenes into $OUT  (VER=$VER THEME=${THEME:-default} WORKERS=$WORKERS)"

worker() {
  local w=$1
  for (( i=w; i<N; i+=WORKERS )); do
    id=$(node -e "console.log(require('$TIMING').scenes[$i].id)")
    f="$OUT/$(printf %02d $i)_$id.mp4"
    if [ -s "$f" ]; then echo "skip $f"; continue; fi
    FILM_ROOT="$FILM_ROOT" TIMING="$TIMING" VER="$VER" \
      node "$SCRIPT" "$i" "$f" > "$LOG/$(printf %02d $i)_$id.log" 2>&1 \
      || echo "FAILED $i $id  (see $LOG/$(printf %02d $i)_$id.log)"
    echo "done $i $id $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null)"
  done
}

for (( w=0; w<WORKERS; w++ )); do worker "$w" & done
wait

# Integrity pass: every clip must match its scene duration (catches truncated files from a killed run).
TIMING="$TIMING" OUT="$OUT" node -e '
const fs=require("fs"),cp=require("child_process");
const T=require(process.env.TIMING), out=process.env.OUT;
let bad=0;
T.scenes.forEach((s,i)=>{
  const f=`${out}/${String(i).padStart(2,"0")}_${s.id}.mp4`;
  if(!fs.existsSync(f)){ console.log("MISSING",f); bad++; return; }
  const d=+cp.execSync(`ffprobe -v error -show_entries format=duration -of csv=p=0 "${f}"`).toString().trim();
  if(Math.abs(d-s.dur)>0.15){ console.log("LENGTH MISMATCH",f,d,"expected",s.dur); bad++; }
});
console.log(bad?`${bad} bad clip(s): delete them and re-run`:"all clips OK");
'

echo ALL_DONE
