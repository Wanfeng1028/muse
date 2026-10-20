#!/usr/bin/env bash
# Mix separate stems into one master, with the music side-chain DUCKED under the voiceover so
# narration always leads. Outputs are also useful on their own as separate stems.
#   usage: ./mix.sh music.mp3 voiceover.mp3 sfx.mp3 master.mp3
# All inputs should already be the same length as the video timeline (pad/trim with afade+apad).
set -e
MUSIC="$1"; VO="$2"; SFX="$3"; OUT="${4:-master.mp3}"
ffmpeg -y -i "$MUSIC" -i "$VO" -i "$SFX" -filter_complex "
  [1:a]asplit=2[vo1][vo2];
  [vo1]volume=1.25[voMain];
  [2:a]volume=0.9[sfx];
  [0:a]volume=0.6[mus0];
  [mus0][vo2]sidechaincompress=threshold=0.025:ratio=8:attack=5:release=320:makeup=1[musd];
  [musd][voMain][sfx]amix=inputs=3:normalize=0:dropout_transition=0[mx];
  [mx]alimiter=limit=0.95,aresample=44100[out]" \
  -map "[out]" -c:a libmp3lame -q:a 2 "$OUT" -loglevel error
echo "wrote $OUT"; ffmpeg -i "$OUT" -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
