#!/bin/bash
# One-time setup: Python deps + offline ASR model (SenseVoice via sherpa-onnx, ~230 MB) used for subtitle alignment.
set -e
python3 -m pip install --quiet sherpa-onnx soundfile numpy scipy pypinyin pyloudnorm pillow 2>/dev/null \
  || python3 -m pip install --quiet --break-system-packages sherpa-onnx soundfile numpy scipy pypinyin pyloudnorm pillow
D=~/.cache/kol-video; mkdir -p $D; cd $D
M=sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17
if [ ! -f $M/model.int8.onnx ]; then
  echo "downloading ASR model…"
  curl -sSL -o sv.tar.bz2 https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$M.tar.bz2
  tar xjf sv.tar.bz2 && rm sv.tar.bz2
fi
command -v ffmpeg >/dev/null || echo "WARNING: ffmpeg not found (brew install ffmpeg / apt install ffmpeg)"
command -v node >/dev/null || echo "WARNING: Node.js 18+ not found"
echo "setup ok — ASR model at $D/$M"
