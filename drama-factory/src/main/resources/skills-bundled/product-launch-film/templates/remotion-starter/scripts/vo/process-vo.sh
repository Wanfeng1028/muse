#!/usr/bin/env bash
# Gentle VO dynamics before the mix: high-pass 70 Hz, 2.5:1 compression, +7 dB make-up, soft limit.
# Lowers speech crest ~2.5-3 dB at equal RMS, so the master limiter barely works.
# Needs a FULL ffmpeg (acompressor + alimiter); Remotion's bundled ffmpeg lacks alimiter.
# Usage: scripts/vo/process-vo.sh vo-takes/picked   (every *.mp3 -> same-name 48 kHz mono .wav)
set -euo pipefail
dir=${1:?usage: process-vo.sh DIR}
for f in "$dir"/*.mp3; do
  n=$(basename "$f" .mp3)
  ffmpeg -y -loglevel error -i "$f" \
    -af "highpass=f=70,acompressor=threshold=-26dB:ratio=2.5:attack=4:release=90:knee=6,volume=7dB,alimiter=limit=0.63:attack=2:release=40:level=disabled" \
    -ar 48000 -ac 1 -c:a pcm_s16le "$dir/$n.wav"
  echo "$n.wav"
done
