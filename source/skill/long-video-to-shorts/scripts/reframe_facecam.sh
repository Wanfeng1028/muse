#!/usr/bin/env bash
# Crop a 9:16 window (full source height) centered on face_center_x, then scale to 1080x1920.
# Falls back to width-scale + pad when the source is narrower than the 9:16 window.
set -euo pipefail
IN="${1:?in}"; CX="${2:?center_x 0..1}"; OUT="${3:?out}"

WH="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$IN" | tr -d '\r')"
IW="${WH%%,*}"; IH="${WH##*,}"

# compute crop width (even) and clamped x with awk (handles the float CX)
read CW X < <(awk -v iw="$IW" -v ih="$IH" -v cx="$CX" 'BEGIN{
  cw=int(ih*9/16); if(cw%2)cw--;
  x=int(iw*cx - cw/2); if(x<0)x=0; if(x>iw-cw)x=iw-cw;
  print cw, x
}')

if [ "$CW" -le "$IW" ]; then
  ffmpeg -y -i "$IN" -vf "crop=${CW}:${IH}:${X}:0,scale=1080:1920:flags=lanczos,setsar=1" \
    -c:v libx264 -pix_fmt yuv420p -c:a aac "$OUT"
else
  # source narrower than a 9:16 slice: scale to width and pad top/bottom
  ffmpeg -y -i "$IN" -vf "scale=1080:-2,pad=1080:1920:0:(oh-ih)/2:color=black,setsar=1" \
    -c:v libx264 -pix_fmt yuv420p -c:a aac "$OUT"
fi
echo "$OUT"
