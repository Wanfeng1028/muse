#!/usr/bin/env bash
# Phase 0.5 (Tier 1) — find dead air in the source to seed the shot list.
#
# Pure ffmpeg, zero extra dependencies. First gates on whether the source has any
# meaningful audio at all (silent screen recordings → nothing to do). Then runs
# silencedetect and turns the gaps into candidate actions:
#   - long silence  → "cut"     (drop it)
#   - short silence → "speedup" (montage / 8x candidate)
#   - speech spans  → "keep"    (real-time, likely 1x)
#
# Usage:
#   detect_silence.sh --video source.mov [options]
#
# Options:
#   --noise DB         silence threshold, e.g. -35dB (default -35dB)
#   --min-silence S    minimum gap to count as silence (default 1.2)
#   --cut-threshold S  silence >= this is suggested "cut", else "speedup" (default 4.0)
#   --gate DB          mean_volume below this = treat as silent, skip (default -50)
#   --out FILE         write JSON here (default: stdout)
set -euo pipefail

VIDEO="" NOISE="-35dB" MINSIL=1.2 CUT=4.0 GATE=-50 OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --video) VIDEO="$2"; shift 2;;
    --noise) NOISE="$2"; shift 2;;
    --min-silence) MINSIL="$2"; shift 2;;
    --cut-threshold) CUT="$2"; shift 2;;
    --gate) GATE="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done
[[ -z "$VIDEO" ]] && { echo "need --video" >&2; exit 1; }

DUR=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$VIDEO")
HAS_AUDIO=$(ffprobe -v quiet -select_streams a -show_entries stream=index -of csv=p=0 "$VIDEO" | head -1)

emit() { if [[ -n "$OUT" ]]; then cat > "$OUT"; echo "wrote $OUT" >&2; else cat; fi; }

# No audio stream at all → nothing to listen to.
if [[ -z "$HAS_AUDIO" ]]; then
  echo "{\"has_audio\": false, \"reason\": \"no audio stream\", \"duration\": $DUR}" | emit
  exit 0
fi

# Gate: is the audio effectively silent?
MEANVOL=$(ffmpeg -hide_banner -i "$VIDEO" -af volumedetect -f null - 2>&1 | sed -n 's/.*mean_volume: \(-*[0-9.]*\) dB.*/\1/p' | head -1)
MEANVOL=${MEANVOL:--99}
if awk "BEGIN{exit !($MEANVOL < $GATE)}"; then
  echo "{\"has_audio\": false, \"reason\": \"effectively silent (mean_volume ${MEANVOL} dB < gate ${GATE} dB)\", \"mean_volume\": $MEANVOL, \"duration\": $DUR}" | emit
  exit 0
fi

# Run silencedetect and parse start/end pairs into a segmentation.
RAW=$(ffmpeg -hide_banner -i "$VIDEO" -af "silencedetect=noise=${NOISE}:d=${MINSIL}" -f null - 2>&1 || true)

echo "$RAW" | awk -v dur="$DUR" -v cut="$CUT" -v mv="$MEANVOL" -v noise="$NOISE" -v minsil="$MINSIL" '
  /silence_start:/ { s=$NF; starts[ns++]=s }
  /silence_end:/   { for(i=0;i<NF;i++) if($i=="silence_end:"){e=$(i+1)} ends[ne++]=e }
  END {
    printf "{\n"
    printf "  \"has_audio\": true,\n  \"mean_volume\": %s,\n  \"duration\": %s,\n", mv, dur
    printf "  \"params\": {\"noise\": \"%s\", \"min_silence\": %s, \"cut_threshold\": %s},\n", noise, minsil, cut
    # Build alternating speech/silence timeline.
    printf "  \"segments\": [\n"
    pos=0; first=1
    for(i=0;i<ns;i++){
      ss=starts[i]; se=(i<ne?ends[i]:dur)
      # speech span before this silence
      if(ss-pos>0.05){ if(!first)printf ",\n"; first=0;
        printf "    {\"start\": %.2f, \"end\": %.2f, \"kind\": \"speech\", \"action\": \"keep\"}", pos, ss }
      # the silence span
      d=se-ss; act=(d>=cut?"cut":"speedup")
      if(!first)printf ",\n"; first=0;
      printf "    {\"start\": %.2f, \"end\": %.2f, \"kind\": \"silence\", \"dur\": %.2f, \"action\": \"%s\"}", ss, se, d, act
      pos=se
    }
    # trailing speech
    if(dur-pos>0.05){ if(!first)printf ",\n"; first=0;
      printf "    {\"start\": %.2f, \"end\": %.2f, \"kind\": \"speech\", \"action\": \"keep\"}", pos, dur }
    printf "\n  ]\n}\n"
  }' | emit
