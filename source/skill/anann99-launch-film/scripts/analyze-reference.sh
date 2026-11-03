#!/usr/bin/env bash
# Analyse a reference video (the user's past launch film, or one they love) before storyboarding.
#
#   analyze-reference.sh ref.mp4 work/ref
#
# Writes to <outDir>:
#   info.txt              duration, resolution, fps, codecs
#   frames/f_NNNN.jpg     1 frame per second (640 px wide)
#   sheet_SSS-EEEs.jpg    contact sheets: 12 seconds per sheet (4×3), read them in order
#   cuts.txt              scene-cut timestamps (ffmpeg scene score > 0.25)
#   audio16k.wav          mono 16 kHz (for transcription)
#   audio48.wav           stereo 48 kHz (reference for scripts/band-match.py)
#   loudness.txt          EBU R128 integrated loudness / LRA / true peak
#   transcript.txt        if whisper-cli + a model are available (WHISPER_MODEL=/path/ggml-base.en.bin):
#                         tells you whether it has voiceover or is music-only
set -euo pipefail
IN=${1:?usage: analyze-reference.sh <video> <outDir>}
OUT=${2:-ref}
mkdir -p "$OUT/frames"

ffprobe -v error -show_entries format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels -of default=nw=1 "$IN" > "$OUT/info.txt"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$IN")
echo "duration: ${DUR}s"

ffmpeg -loglevel error -y -i "$IN" -vf "fps=1,scale=640:-1" "$OUT/frames/f_%04d.jpg"
N=$(ls "$OUT/frames" | wc -l | tr -d ' ')
for ((s=0; s<N; s+=12)); do
  e=$(( s + 11 < N - 1 ? s + 11 : N - 1 ))
  ffmpeg -loglevel quiet -y -start_number $((s + 1)) -i "$OUT/frames/f_%04d.jpg" \
    -vf "tile=4x3:padding=6:color=white" -frames:v 1 "$OUT/sheet_$(printf %03d $s)-$(printf %03d $e)s.jpg" || true
done
echo "contact sheets: $(ls "$OUT"/sheet_*.jpg | wc -l | tr -d ' ') (12 s each)"

ffmpeg -hide_banner -i "$IN" -an -vf "scale=320:-1,select='gt(scene,0.25)',metadata=print:file=$OUT/scenes_meta.txt" -f null - 2>/dev/null || true
grep -o "pts_time:[0-9.]*" "$OUT/scenes_meta.txt" 2>/dev/null | cut -d: -f2 > "$OUT/cuts.txt" || true
echo "scene cuts: $(wc -l < "$OUT/cuts.txt" | tr -d ' ') (a continuous motion-graphics film may show very few)"

if ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$IN" | grep -q audio; then
  ffmpeg -loglevel error -y -i "$IN" -vn -ac 1 -ar 16000 "$OUT/audio16k.wav"
  ffmpeg -loglevel error -y -i "$IN" -vn -ac 2 -ar 48000 "$OUT/audio48.wav"
  ffmpeg -hide_banner -nostats -i "$IN" -filter_complex ebur128=peak=true -f null - 2>&1 | grep -E "I:|LRA:|Peak:" | tail -3 > "$OUT/loudness.txt" || true
  cat "$OUT/loudness.txt"
  if command -v whisper-cli >/dev/null 2>&1 && [ -n "${WHISPER_MODEL:-}" ] && [ -f "$WHISPER_MODEL" ]; then
    whisper-cli -m "$WHISPER_MODEL" -f "$OUT/audio16k.wav" -ml 60 2>/dev/null > "$OUT/transcript.txt" || true
    echo "transcript: $OUT/transcript.txt  (lines like '(upbeat music)' only => music-only film)"
  else
    echo "transcription skipped (install whisper-cpp and set WHISPER_MODEL to a ggml model to detect voiceover)"
  fi
else
  echo "no audio stream"
fi
echo "done → $OUT"
