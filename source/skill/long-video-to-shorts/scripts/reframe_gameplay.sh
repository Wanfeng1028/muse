#!/usr/bin/env bash
# Full 16:9 centered over a blurred cover copy, filling a 1080x1920 frame (nothing cropped off the content).
set -euo pipefail
IN="${1:?in}"; OUT="${2:?out}"
ffmpeg -y -i "$IN" -filter_complex "\
[0:v]split=2[bg][fg];\
[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=24[bg2];\
[fg]scale=1080:-2:flags=lanczos[fg2];\
[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1[v]" \
  -map "[v]" -map 0:a? -c:v libx264 -pix_fmt yuv420p -c:a aac "$OUT"
echo "$OUT"
