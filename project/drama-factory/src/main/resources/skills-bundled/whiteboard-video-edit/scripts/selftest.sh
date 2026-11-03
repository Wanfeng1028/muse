#!/bin/zsh
# Standalone proof of the whole whiteboard-video-edit rail, run FROM THE SKILL PATH on a short slice of
# one whiteboard take into a scratch dir (never the folder that holds your footage): rough cut, pose,
# zoom plan, the house grade (measure, LUT), sub pixel long form render with eased zooms, audio master,
# then a vertical reel with 3 headline variants, word timed captions and covers. It is also the
# reference command sequence for a real video.
#
# Usage: selftest.sh <source_4k.mp4> <start_s> <dur_s> <scratch_dir> <board.json> <focus.json> <clips.json> <headlines>
#   board.json  item rects in 4K source px, measured on THIS take (times in focus/clips are on the
#               rough cut timeline of the slice)
#   headlines   "H1||H2||H3" in overlay_build.py syntax ("NN:line|NN:line" per variant)
# Stages run in order; each writes <scratch>/logs/<stage>.log. STAGE=<name> resumes from a stage and
# STOP=<name> stops after one (slice rough pose plan grade render audio reel cover), so each run stays
# under a 10 minute tool ceiling and you can write clips.json after reading output_transcript.txt.
# CAP_OVERRIDE=<json> pins caption centres per shot (overlay_build.py's optional 6th argument).
# PY=<python command> picks the interpreter (default python3; it needs Pillow).
# Needs ELEVENLABS_API_KEY in the environment: it costs one or two ElevenLabs Scribe calls.
# The last line counts the stages that are green so far across runs: "9 of 9 stages" is a full pass.
# Exit 0 = every stage that ran passed its gate (cut boundaries, cut changes, faces, frame counts,
# loudness, smoothness, the 5 colour gates on the encoded long form and on every reel variant, overlay
# overlaps, variant identity, the reel stream header, OCR read back, the reel safe zones); exit 2 names
# the stage that failed. The cover stage only warns when no frame passes the expression gate (pick a
# frame by hand).
set -u
S="$(cd "$(dirname "$0")" && pwd)"
PY=${PY:-python3}
[ $# -ge 8 ] || { echo "usage: selftest.sh <source_4k.mp4> <start_s> <dur_s> <scratch_dir> <board.json> <focus.json> <clips.json> <headlines>"; exit 1; }
src="$1"; st="$2"; dur="$3"; W="$4"; board="$5"; focus="$6"; clips="$7"; heads="$8"
srcdir="$(cd "$(dirname "$src")" && pwd)"
case "$W" in "$srcdir"|"$srcdir"/*|*/Downloads|*/Downloads/*) echo "refusing: the scratch dir must be outside the folder that holds the footage and outside Downloads"; exit 1;; esac
for t in pose ocr face-screen; do [ -x "$S/$t" ] || { echo "missing $S/$t: run $S/setup.sh once"; exit 1; }; done
mkdir -p "$W/logs" "$W/tools" "$W/rough-cut" "$W/audio" "$W/previews" "$W/checks" "$W/captions"
cp "$board" "$W/tools/board.json"; cp "$focus" "$W/tools/focus_proof.json"
cd "$W" || exit 1
ORDER=(slice rough pose plan grade render audio reel cover)
from="${STAGE:-slice}"; to="${STOP:-cover}"
(( ${ORDER[(Ie)$from]} && ${ORDER[(Ie)$to]} )) || { echo "STAGE and STOP must be one of: $ORDER"; exit 1; }
stage() { (( ${ORDER[(i)$1]} >= ${ORDER[(i)$from]} && ${ORDER[(i)$1]} <= ${ORDER[(i)$to]} )); }
fail() { echo "FAIL at $1 (see $W/logs/$1.log)"; tail -5 "$W/logs/$1.log"; exit 2; }
ran=()
# a stage that runs again voids its own pass mark and the mark of every stage after it (they depend on it)
begin() { for s in ${ORDER[${ORDER[(i)$1]},-1]}; do rm -f "logs/.passed-$s"; done; }
pass() { : > "logs/.passed-$1"; ran+=($1); }

if stage slice; then begin slice  # a frame accurate 4K slice, re-encoded near lossless (a stream copy would start on a keyframe)
  ffmpeg -nostdin -v error -y -ss "$st" -t "$dur" -i "$src" -map 0:v:0 -map 0:a:0 -c:v libx264 -preset veryfast -crf 12 \
    -pix_fmt yuv420p -c:a pcm_s16le slice.mov > logs/slice.log 2>&1 || fail slice
  echo "slice: $(ffprobe -v error -show_entries stream=width,height,r_frame_rate -of csv=p=0 slice.mov | head -1)"
  pass slice
fi
if stage rough; then begin rough  # the rough cut: transcribe, plan, render (landscape at --height 1920), verify every cut
  { ${=PY} $S/transcribe.py --edit-dir rough-cut --language en --num-speakers 1 "$W/slice.mov" &&
    ${=PY} $S/rough_cut.py plan --edit-dir rough-cut --source "$W/slice.mov" --fps 24000/1001 --keep-events &&
    ${=PY} $S/rough_cut.py render --edit-dir rough-cut --fps 24000/1001 --height 1920 &&
    ${=PY} $S/rough_cut.py verify --edit-dir rough-cut; } > logs/rough.log 2>&1 || fail rough
  grep -E "cuts, A/V|boundaries" logs/rough.log
  ${=PY} $S/segments.py rough-cut > logs/segments.log 2>&1 || fail segments
  ${=PY} $S/phrases.py rough-cut > /dev/null 2>&1
  ${=PY} $S/cut_list.py "selftest slice" "rough-cut/transcripts/slice.json" > logs/cutlist.log 2>&1 || fail cutlist
  echo "cut list: $(cat logs/cutlist.log)"
  pass rough
fi
if stage pose; then begin pose
  ${=PY} $S/pose_track.py . > logs/pose.log 2>&1 || fail pose
  echo "pose: $(cat logs/pose.log)"
  pass pose
fi
if stage plan; then begin plan  # zoom plan before rendering, then the gates on the plan
  { ${=PY} $S/plan_zooms.py . proof && ${=PY} $S/fix_cuts.py . proof; } > logs/plan.log 2>&1 || fail plan
  echo "plan: $(head -1 logs/plan.log)"
  ${=PY} $S/cut_change_check.py . proof > checks/cut-change.json; cat checks/cut-change.json
  ${=PY} $S/face_cut_audit.py . camera_proof.json 16/9 lf > checks/face-audit-lf.json; cat checks/face-audit-lf.json
  ${=PY} -c "import json,sys; c=json.load(open('checks/cut-change.json')); f=json.load(open('checks/face-audit-lf.json'))
sys.exit(0 if not c['fail'] and f['half_cut_face'] == 0 else 1)" || { cp checks/cut-change.json logs/gate-plan.log; fail gate-plan; }
  pass plan
fi
if stage grade; then begin grade  # house grade F: measure the take (board white, shadows, skin, face), build its LUT
  { ${=PY} $S/grade.py measure . proof "$W/slice.mov" && ${=PY} $S/grade.py lut . proof; } > logs/grade.log 2>&1 || fail grade
  cut -c1-230 logs/grade.log
  pass grade
fi
if stage render; then begin render
  ${=PY} $S/make_props.py . proof "$W/slice.mov" > logs/render.log 2>&1 || fail render
  ${=PY} $S/grade.py props grade/house_proof.cube props_proof_abs.json >> logs/render.log 2>&1 || fail render
  N=$(${=PY} -c "import json; print(len(json.load(open('camera_proof.json'))['camera']))")
  $S/render_range.sh props_proof_abs.json render/parts 0 $((N - 1)) 4 >> logs/render.log 2>&1 || fail render
  (cd render/parts && ls r_*.mp4 | sed "s/.*/file '&'/" > list.txt)
  ffmpeg -nostdin -v error -y -f concat -safe 0 -i render/parts/list.txt -c copy render/proof_video.mp4 >> logs/render.log 2>&1 || fail render
  n=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 render/proof_video.mp4)
  echo "render: $n of $N frames"
  [ "$n" = "$N" ] || fail render
  pass render
fi
if stage audio; then begin audio
  ${=PY} $S/master_audio.py rough-cut/rough_cut_master.mov audio/proof_master_audio.wav > logs/audio.log 2>&1 || fail audio
  ffmpeg -nostdin -v error -y -i render/proof_video.mp4 -i audio/proof_master_audio.wav -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 320k \
    -ar 48000 -movflags +faststart proof-lf.mp4 >> logs/audio.log 2>&1 || fail audio
  ffmpeg -nostdin -hide_banner -i proof-lf.mp4 -map 0:a -af ebur128=peak=true -f null - 2>&1 | grep -A20 Summary | grep -E "I:|Peak:" > checks/loudness-lf.txt
  cat checks/loudness-lf.txt
  ${=PY} -c "import re,sys; t=open('checks/loudness-lf.txt').read(); i=float(re.search(r'I:\s+(-?[\d.]+)',t).group(1)); p=float(re.search(r'Peak:\s+(-?[\d.]+)',t).group(1))
sys.exit(0 if abs(i + 14) <= 1.0 and p <= -1.0 else 1)" || { cp checks/loudness-lf.txt logs/gate-loudness.log; fail gate-loudness; }
  # the 5 colour gates on the ENCODED long form (white board, skin hue, face luma, board clip, cut jumps)
  ${=PY} $S/grade.py gates proof-lf.mp4 props_proof_abs.json . proof --out checks/grade-gates-lf.json > logs/gate-grade-lf.log 2>&1 || fail gate-grade-lf
  cat logs/gate-grade-lf.log
  mv=$(${=PY} -c "
import json; p=json.load(open('zoom-plan.json'))
m=[m for s in p['shots'] for m in s['moves']]
print(f\"{m[0]['start_frame'] - 2} {m[0]['start_frame'] + m[0]['frames'] + 2}\" if m else '')")
  if [ -n "$mv" ]; then
    node $S/measure_motion.mjs proof-lf.mp4 ${=mv} camera_proof.json 1920 1080 > checks/smoothness.txt 2>&1 || { cp checks/smoothness.txt logs/gate-smooth.log; fail gate-smooth; }
    ${=PY} $S/smooth_table.py checks/smoothness.txt "selftest, first eased move" > checks/smoothness.md
    rc=$?; tail -1 checks/smoothness.md; [ $rc = 0 ] || { cp checks/smoothness.md logs/gate-smooth.log; fail gate-smooth; }
  fi
  pass audio
fi
if stage reel; then begin reel  # vertical reel: plan, faces, caption words, 3 headline overlays, one render pass with the variants
  { ${=PY} $S/reel_build.py . "$clips" audio/proof_master_audio.wav "$W/slice.mov" &&
    ${=PY} $S/reel_faces.py reel/props_reel_vertical_abs.json reel &&
    ${=PY} $S/reel_words.py . captions/expected_words.json &&
    ${=PY} $S/grade.py props grade/house_proof.cube reel/props_reel_vertical_abs.json; } > logs/reel.log 2>&1 || fail reel
  { ${=PY} $S/transcribe.py --edit-dir captions --language en --num-speakers 1 "$W/reel/reel_audio.wav" &&
    ${=PY} $S/caption_words.py captions/expected_words.json captions/transcripts/reel_audio.json captions/words_reel.json &&
    ${=PY} $S/overlay_build.py . vertical captions/words_reel.json "$heads" captions/vertical ${CAP_OVERRIDE:+"$CAP_OVERRIDE"}; } >> logs/reel.log 2>&1 || fail reel
  grep -E "matched|headlines centred|overlapping|pinned" logs/reel.log
  ${=PY} -c "import json,sys; a=json.load(open('captions/vertical/audit.json'))['frames']
bad=[x['f'] for x in a if x.get('headline_overlap_px_no_air',0) > 0 or x.get('chip_overlap_px_no_air',0) > 0 or x.get('chip_headline_overlap_px',0) > 0 or x.get('chip_in_safe') is False]
print('overlay audit: frames with an overlap or outside the safe box:', len(bad), bad[:10]); sys.exit(1 if bad else 0)" > logs/gate-overlay.log 2>&1 || fail gate-overlay
  cat logs/gate-overlay.log
  N=$(${=PY} -c "import json; print(json.load(open('reel/reel-plan.json'))['total_frames'])")
  HF=$(${=PY} -c "import json; print(json.load(open('captions/vertical/audit.json'))['headline_frames'])")
  $S/render_variants.sh reel/props_reel_vertical_abs.json captions/vertical captions/render $N $HF 4 all >> logs/reel.log 2>&1 || fail reel
  for v in $(cd captions/vertical && ls overlays_h*.json | sed 's/overlays_\(h[0-9]*\)\.json/\1/'); do
    ffmpeg -nostdin -v error -y -i captions/render/video_$v.mp4 -i reel/reel_audio.wav -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 320k \
      -ar 48000 -movflags +faststart proof-reel-$v.mp4 >> logs/reel.log 2>&1 || fail reel
    printf '%s tail md5 %s audio md5 %s\n' $v "$(ffmpeg -nostdin -v error -i proof-reel-$v.mp4 -map 0:v:0 -vf "select=gte(n\,$HF)" -fps_mode passthrough -f framemd5 - | grep -v '^#' | awk -F, '{print $6}' | md5)" \
      "$(ffmpeg -nostdin -v error -i proof-reel-$v.mp4 -map 0:a:0 -f md5 - | sed 's/MD5=//')"
  done > checks/reel-variants-identity.txt
  cat checks/reel-variants-identity.txt
  # after the headline every variant must be the same picture, and the same audio from the first sample
  [ "$(awk '{print $4}' checks/reel-variants-identity.txt | sort -u | wc -l | tr -d ' ')" = 1 ] || { cp checks/reel-variants-identity.txt logs/gate-identity.log; fail gate-identity; }
  [ "$(awk '{print $7}' checks/reel-variants-identity.txt | sort -u | wc -l | tr -d ' ')" = 1 ] || { cp checks/reel-variants-identity.txt logs/gate-identity.log; fail gate-identity; }
  for v in $(cd captions/vertical && ls overlays_h*.json | sed 's/overlays_h\([0-9]*\)\.json/\1/'); do
    ${=PY} $S/chip_readback.py proof-reel-h$v.mp4 captions/vertical checks/readback $v > logs/gate-readback-h$v.log 2>&1 || fail gate-readback-h$v
    grep -E "chips read back|headline OCR" logs/gate-readback-h$v.log
    ${=PY} $S/grade.py gates proof-reel-h$v.mp4 reel/props_reel_vertical_abs.json . proof --overlays captions/vertical/overlays_h$v.json \
      --skip-head $HF --out checks/grade-gates-reel-h$v.json > logs/gate-grade-reel-h$v.log 2>&1 || fail gate-grade-reel-h$v
    cat logs/gate-grade-reel-h$v.log
    ${=PY} $S/check-reel-safe-zones.py proof-reel-h$v.mp4 --frames 12 > logs/gate-safe-h$v.log 2>&1 || fail gate-safe-h$v
    cat logs/gate-safe-h$v.log
  done
  # the stream header: every variant carries the same H.264 header, tagged BT.709 limited range, so the
  # variants stay interchangeable and a clip made on this rail can be stream copied onto any of them
  for v in $(cd captions/vertical && ls overlays_h*.json | sed 's/overlays_\(h[0-9]*\)\.json/\1/'); do
    printf '%s %s %s\n' $v "$(ffprobe -v error -select_streams v:0 -show_entries stream=extradata_hash -show_data_hash md5 -of csv=p=0 proof-reel-$v.mp4)" \
      "$(ffprobe -v error -select_streams v:0 -show_entries stream=color_space,color_range -of csv=p=0 proof-reel-$v.mp4)"
  done > logs/gate-header.log
  cat logs/gate-header.log
  [ "$(awk '{print $2}' logs/gate-header.log | sort -u | wc -l | tr -d ' ')" = 1 ] || fail gate-header
  [ "$(awk '{print $3}' logs/gate-header.log | sort -u)" = "tv,bt709" ] || fail gate-header
  ffmpeg -nostdin -hide_banner -i proof-reel-h1.mp4 -map 0:a -af ebur128=peak=true -f null - 2>&1 | grep -A20 Summary | grep -E "I:|Peak:" > checks/loudness-reel.txt
  cat checks/loudness-reel.txt
  ${=PY} -c "import re,sys; t=open('checks/loudness-reel.txt').read(); p=float(re.search(r'Peak:\s+(-?[\d.]+)',t).group(1))
sys.exit(0 if p <= -1.0 else 1)" || { cp checks/loudness-reel.txt logs/gate-loudness-reel.log; fail gate-loudness-reel; }
  pass reel
fi
if stage cover; then begin cover
  ${=PY} $S/reel_cover.py cands . vertical captions/vertical covers 2 > logs/cover.log 2>&1 || fail cover
  grep candidates logs/cover.log
  f=$(${=PY} -c "
import json; r=[x for x in json.load(open('covers/cands.json'))['rows'] if x['pass']]
print(max(r, key=lambda x: float(x['screen'].split('face_px=')[1].split()[0]))['frame'] if r else '')")
  if [ -z "$f" ]; then echo "cover: WARNING no frame passed the expression gate (pick by hand or widen the search)"; else
    ${=PY} $S/reel_cover.py compose . vertical captions/vertical covers $f proof-reel >> logs/cover.log 2>&1 || fail cover
    tail -1 logs/cover.log
  fi
  pass cover
fi
green=(); for s in $ORDER; do [ -e "logs/.passed-$s" ] && green+=($s); done
echo "SELFTEST DONE: this run ${#ran} of ${#ran} stages passed ($ran); green so far: ${#green} of ${#ORDER} stages ($green) in $W"
