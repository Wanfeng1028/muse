#!/usr/bin/env bash
# mix-audio.sh <work-dir> <voice-audio> <duration> [music-file]
#
# The audio half of mix-encode.sh and render-chunks.sh, so the two can never drift apart. Writes
# <work-dir>/mix.wav. Voice is denoised, de-essed, compressed and normalised; clip audio and music duck
# under it via sidechain, SFX sit on top, and the mix is padded/trimmed to the exact duration, then
# measured, then given one linear gain to −14 LUFS with a −1.5 dBFS peak limiter. When mix.json carries
# a duck array (synth_audio.py found pauses in words.js), the music also swells toward full level inside
# each pause, on 150 ms ramps.
# Music and SFX levels come from <work-dir>/mix.json (synth_audio.py writes it from the kit's
# audio.levels); the music is the explicit music-file, else mix.json's music_file, else none.
set -euo pipefail

if (( $# < 3 || $# > 4 )); then
  echo "Usage: mix-audio.sh <work-dir> <voice-audio> <duration> [music-file]"
  echo "Next: pass the work dir, the voice audio and the duration in seconds"
  exit 1
fi
WORK="$1"
VOICE="$2"
DURATION="$3"
MUSIC_ARG="${4:-}"
trap 'rm -f "$WORK/premix.wav"' EXIT

[[ -f "$WORK/sfx.wav" ]] || { echo "No sfx.wav in $WORK"; echo "Next: run synth_audio.py"; exit 1; }

# A work dir from before mix.json falls back to the old fixed levels and music.wav if it exists
if ! MIX_SETTINGS=$(python3 - "$WORK/mix.json" <<'PY'
import json, sys
try:
    mix = json.load(open(sys.argv[1], encoding="utf-8"))
except FileNotFoundError:
    mix = {"music_file": "music.wav"}
except (json.JSONDecodeError, OSError) as error:
    print(f"cannot read {sys.argv[1]}: {error}", file=sys.stderr)
    sys.exit(1)
music, sfx = mix.get("music", 0.22), mix.get("sfx", 0.5)
for name, level in (("music", music), ("sfx", sfx)):
    if not isinstance(level, (int, float)) or not 0 <= level <= 2:
        print(f"mix.json {name} must be a number from 0 to 2, got {level!r}", file=sys.stderr)
        sys.exit(1)
print(music, sfx, mix.get("music_file") or "")
PY
); then
  echo "Next: re-run synth_audio.py, which rewrites mix.json from the kit"
  exit 1
fi
read -r MUSIC_LEVEL SFX_LEVEL MUSIC_FILE <<< "$MIX_SETTINGS"
MUSIC=""
if [[ -n "$MUSIC_ARG" ]]; then
  [[ -f "$MUSIC_ARG" ]] || { echo "No such music file: $MUSIC_ARG"; echo "Next: pass an existing track, or leave it out to use synth_audio.py's music"; exit 1; }
  MUSIC="$MUSIC_ARG"
elif [[ -n "$MUSIC_FILE" && -f "$WORK/$MUSIC_FILE" ]]; then
  MUSIC="$WORK/$MUSIC_FILE"
fi

# Clip audio from extract_clip.sh --audio: a speaking founder, a crowd, a product sound
shopt -s nullglob
CLIP_WAVS=("$WORK"/clips/*.wav)
shopt -u nullglob

INPUTS=(-i "$VOICE")
FILTER="[0:a]aresample=48000,apad=whole_dur=${DURATION},highpass=f=80,afftdn=nr=12:nf=-40:tn=1,deesser=i=0.4,equalizer=f=3500:t=q:w=1.2:g=2,acompressor=threshold=-18dB:ratio=3:attack=5:release=120,loudnorm=I=-16:TP=-2,aresample=48000,asplit=3[voice][vkey][ckey];"
LAYERS="[voice]"
COUNT=1
NEXT=1

if (( ${#CLIP_WAVS[@]} > 0 )); then
  CLIP_LABELS=""
  for wav in "${CLIP_WAVS[@]}"; do
    INPUTS+=(-i "$wav")
    FILTER+="[${NEXT}:a]aresample=48000[c${NEXT}];"
    CLIP_LABELS+="[c${NEXT}]"
    NEXT=$(( NEXT + 1 ))
  done
  # Narration wins where they overlap; over a pause in the voice the clip plays at full level
  FILTER+="${CLIP_LABELS}amix=inputs=${#CLIP_WAVS[@]}:normalize=0:duration=longest,apad=whole_dur=${DURATION},asplit=2[craw][cclip];"
  FILTER+="[craw][ckey]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=250[clips];"
  FILTER+="[vkey][cclip]amix=inputs=2:normalize=0:duration=first[key];"
  LAYERS+="[clips]"
  COUNT=$(( COUNT + 1 ))
else
  FILTER+="[ckey]anullsink;[vkey]anull[key];"
fi

if [[ -n "$MUSIC" ]]; then
  INPUTS+=(-i "$MUSIC")
  # mix.json's duck array (synth_audio.py, from words.js pauses): swell the bed toward full level in
  # each gap, 150 ms ramps in and out; the sidechain below still ducks it under the voice
  DUCK_EXPR=$(python3 - "$WORK/mix.json" "$MUSIC_LEVEL" "$0" <<'PY'
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[3])))
from synth_audio import build_duck_expr
try:
    mix = json.load(open(sys.argv[1], encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError, OSError):
    sys.exit(0)
expr = build_duck_expr(mix.get("duck") or [], sys.argv[2])
if expr:
    print(expr)
PY
  )
  if [[ -n "$DUCK_EXPR" ]]; then
    FILTER+="[${NEXT}:a]aresample=48000,volume=${MUSIC_LEVEL},volume='${DUCK_EXPR}':eval=frame[mus];"
  else
    FILTER+="[${NEXT}:a]aresample=48000,volume=${MUSIC_LEVEL}[mus];"
  fi
  FILTER+="[mus][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];"
  LAYERS+="[duck]"
  COUNT=$(( COUNT + 1 ))
  NEXT=$(( NEXT + 1 ))
else
  FILTER+="[key]anullsink;"
fi

INPUTS+=(-i "$WORK/sfx.wav")
FILTER+="[${NEXT}:a]aresample=48000,volume=${SFX_LEVEL}[fx];"
LAYERS+="[fx]"
COUNT=$(( COUNT + 1 ))

ffmpeg -v error -y "${INPUTS[@]}" -filter_complex "\
${FILTER}\
${LAYERS}amix=inputs=${COUNT}:normalize=0:duration=longest,alimiter=limit=0.95,aresample=48000,atrim=0:${DURATION}[out]" \
  -map "[out]" -c:a pcm_f32le "$WORK/premix.wav"

# Measuring first lets pass 2 apply one static gain; loudnorm linear=true falls back to dynamic when the limited premix can't take the gain within TP
MEASURED=$(ffmpeg -hide_banner -nostats -i "$WORK/premix.wav" -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null - 2>&1) || {
  printf '%s\n' "$MEASURED" | tail -n 15 >&2
  echo "loudnorm measurement failed on $WORK/premix.wav"; echo "Next: fix the ffmpeg error above and check that the voice file is valid audio"; exit 1; }
GAIN_DB=$(printf '%s\n' "$MEASURED" | python3 -c '
import json, re, sys
match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", sys.stdin.read(), re.S)
if not match:
    sys.exit(1)
print("{:.2f}".format(-14 - float(json.loads(match.group(0))["input_i"])))
') || { echo "Could not parse loudnorm measurement JSON for $WORK/premix.wav"; echo "Next: run ffmpeg -i premix.wav -af loudnorm=print_format=json -f null - and check its output"; exit 1; }

# 0.8414 = -1.5 dBFS ceiling; the limiter catches peaks the gain pushes over it
ffmpeg -v error -y -i "$WORK/premix.wav" \
  -af "volume=${GAIN_DB}dB,alimiter=limit=0.8414:level=disabled,aresample=48000,apad=whole_dur=${DURATION},atrim=0:${DURATION}" "$WORK/mix.wav"

MUSIC_NOTE="none"
[[ -n "$MUSIC" ]] && MUSIC_NOTE="$(basename "$MUSIC") at $MUSIC_LEVEL"
[[ -n "${DUCK_EXPR:-}" ]] && MUSIC_NOTE+=" · swells in pauses"
echo "mix.wav · music $MUSIC_NOTE · sfx at $SFX_LEVEL"
