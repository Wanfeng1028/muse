#!/bin/bash
# Render a project: bundle → silent video → mux with build/mix.wav → out/<name>.mp4 + cover PNG.
# usage: render.sh <proj> <output_name> [frames e.g. 0-338 for a partial preview]
# Optional: BROWSER=/path/to/chrome-headless-shell (otherwise Remotion downloads its own)
set -e
P=$(cd "$1" && pwd); NAME="$2"; FR="$3"
cd "$P/video"
BX=(); [ -n "$BROWSER" ] && BX=(--browser-executable="$BROWSER")
CONC=${CONC:-2}
npx remotion bundle src/index.ts --out-dir="$P/build/bundle" --log=error
mkdir -p "$P/out"
if [ -n "$FR" ]; then
  npx remotion render "$P/build/bundle" Main "$P/out/${NAME}_preview.mp4" --frames="$FR" --concurrency=$CONC --crf=20 "${BX[@]}" --log=error
  echo "preview: $P/out/${NAME}_preview.mp4"; exit 0
fi
npx remotion render "$P/build/bundle" Main "$P/build/silent.mp4" --muted --concurrency=$CONC --crf=16 "${BX[@]}" --log=error
ffmpeg -y -loglevel error -i "$P/build/silent.mp4" -i "$P/build/mix.wav" -map 0:v -map 1:a -c:v libx264 -crf 19 -preset slow \
  -pix_fmt yuv420p -c:a aac -b:a 256k -shortest -movflags +faststart "$P/out/$NAME.mp4"
npx remotion still "$P/build/bundle" Cover "$P/out/${NAME}_封面.png" "${BX[@]}" --log=error
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$P/out/$NAME.mp4")
echo "done: $P/out/$NAME.mp4 (${D}s) + cover"
