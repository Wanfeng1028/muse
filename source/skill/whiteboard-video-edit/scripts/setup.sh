#!/bin/zsh
# One time setup, and a check you can run again at any time.
#   1. checks the tools the rail needs (ffmpeg, ffprobe, node, python3 with Pillow, swiftc, curl)
#   2. compiles the three Apple Vision helpers next to their sources (the binaries are not in git):
#        pose         face box and body joints per image (JSON lines)
#        ocr          Vision text recognition per image
#        face-screen  the cover expression gate (eyes open, mouth closed, facing the lens)
#   3. reports the caption font it found (look.json) and whether ELEVENLABS_API_KEY is set
# Run it again after editing a .swift file. Exit 0 = ready, 1 = something is missing (named above the exit).
set -u
cd "$(dirname "$0")"
PY=${PY:-python3}
miss=0
[ "$(uname -s)" = Darwin ] || { echo "MISSING macOS: the pose, OCR and face gates use Apple Vision"; miss=1; }
for t in ffmpeg ffprobe node swiftc curl; do
  if command -v $t > /dev/null; then echo "ok      $t ($(command -v $t))"; else echo "MISSING $t"; miss=1; fi
done
if ${=PY} -c "import PIL" 2> /dev/null; then echo "ok      ${PY} with Pillow $(${=PY} -c 'import PIL; print(PIL.__version__)')"
else echo "MISSING Pillow for ${PY} (${PY} -m pip install pillow; on a Mac whose python3 runs under Rosetta, set PY='arch -arm64 python3')"; miss=1; fi
for t in pose ocr face-screen; do
  if [ ! -x "$t" ] || [ "$t.swift" -nt "$t" ]; then
    if swiftc -O "$t.swift" -o "$t" 2> /tmp/whiteboard-setup-$t.log; then echo "built   $t"; else echo "MISSING $t (swiftc failed, see /tmp/whiteboard-setup-$t.log)"; miss=1; fi
  else echo "ok      $t (up to date)"; fi
done
if [ $miss = 0 ]; then
  ${=PY} look.py > /tmp/whiteboard-setup-look.json 2> /tmp/whiteboard-setup-look.err && \
    echo "ok      caption font: $(${=PY} -c "import json; print(json.load(open('/tmp/whiteboard-setup-look.json'))['font_name'])")" || { echo "MISSING caption font: $(cat /tmp/whiteboard-setup-look.err)"; miss=1; }
  [ -s /tmp/whiteboard-setup-look.err ] && cat /tmp/whiteboard-setup-look.err
fi
if [ -n "${ELEVENLABS_API_KEY:-}" ]; then echo "ok      ELEVENLABS_API_KEY is set"
else echo "note    ELEVENLABS_API_KEY is not set: transcribe.py needs it (export ELEVENLABS_API_KEY=<your key>)"; fi
if command -v whisper-cli > /dev/null; then echo "ok      whisper-cli (optional tie breaker for a disputed caption word)"
else echo "note    whisper-cli not found (optional: brew install whisper-cpp)"; fi
[ $miss = 0 ] && echo "READY" || echo "NOT READY"
exit $miss
