#!/usr/bin/env bash
# Render the full film and produce QA artefacts.
#   tools/qa.sh [name=film] [extra remotion flags...]
# → out/<name>.mp4, out/qa/<name>_sheet.jpg (1 fps contact sheet), loudness + stream report.
set -e
cd "$(dirname "$0")/.."
NAME=${1:-film}; shift || true
OUT=out/$NAME.mp4
ROWS=$(node -e "console.log(Math.ceil(JSON.parse(require('fs').readFileSync('scenes.json','utf8')).duration / 6))")
npx remotion render Main $OUT --codec=h264 --crf=16 --pixel-format=yuv420p --audio-codec=aac --audio-bitrate=320k "$@"
mkdir -p out/qa
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate,sample_rate,channels -of compact $OUT
ffmpeg -y -loglevel error -i $OUT -vf "fps=1,scale=320:180,tile=6x${ROWS}:padding=4:color=white" -frames:v 1 out/qa/${NAME}_sheet.jpg
ffmpeg -nostats -i $OUT -filter_complex ebur128=peak=true -f null - 2>&1 | grep -E "I:|Peak:|LRA:" | tail -3 || true
echo "QA done: $OUT, out/qa/${NAME}_sheet.jpg  (targets: I ≈ -14 LUFS, Peak ≤ -1 dBFS)"
