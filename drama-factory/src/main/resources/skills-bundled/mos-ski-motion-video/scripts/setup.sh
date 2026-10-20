#!/usr/bin/env bash
# Motion Video: one-time project setup. Run from the folder where you'll make videos:
#   bash <path-to-skill>/scripts/setup.sh [--beats]
# --beats also installs librosa, for measuring the beat grid of a music track.
set -euo pipefail
SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="$(pwd)"
BEATS=0; [ "${1:-}" = "--beats" ] && BEATS=1
ok() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
note() { printf '  \033[33m!\033[0m %s\n' "$1"; }
die() { printf '  \033[31m✗\033[0m %s\n' "$1"; exit 1; }

echo "Checking tools"
command -v ffmpeg >/dev/null || die "ffmpeg not found (macOS: brew install ffmpeg; Ubuntu: apt install ffmpeg)"
FILTERS="$(ffmpeg -hide_banner -filters 2>/dev/null)"
for f in loudnorm sidechaincompress amix tile; do
  grep -q " $f " <<<"$FILTERS" || die "ffmpeg is missing the '$f' filter; install ffmpeg 6+"
done
ok "ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"
command -v node >/dev/null || die "Node.js not found (https://nodejs.org, v18+)"
ok "node $(node -v)"
command -v python3 >/dev/null || die "python3 not found (3.9+)"
ok "python $(python3 --version | awk '{print $2}')"

echo "Python environment (.motion/venv)"
[ -x "$PROJ/.motion/venv/bin/python" ] || python3 -m venv "$PROJ/.motion/venv"
"$PROJ/.motion/venv/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
"$PROJ/.motion/venv/bin/pip" install -q numpy scipy
ok "numpy, scipy"
if [ "$BEATS" = 1 ]; then
  "$PROJ/.motion/venv/bin/pip" install -q librosa
  ok "librosa (beat measuring)"
fi

echo "Remotion studio (./studio)"
if [ ! -d "$PROJ/studio" ]; then
  cp -R "$SKILL/engine" "$PROJ/studio"
  ok "created studio/ from the engine"
elif [ ! -d "$PROJ/studio/src/motion" ]; then
  mkdir -p "$PROJ/studio/src"
  cp -R "$SKILL/engine/src/motion" "$PROJ/studio/src/motion"
  note "studio/ already existed: copied src/motion/ in. Render <MotionCompositions /> (from"
  note "motion/register.tsx) inside your studio/src/Root.tsx, and make sure remotion,"
  note "@remotion/cli and @remotion/google-fonts are in studio/package.json"
else
  ok "studio/src/motion exists; not overwritten (compare with $SKILL/engine/src/motion to update)"
fi
(cd "$PROJ/studio" && npm install --no-audit --no-fund --silent)
ok "npm packages"

echo "Project folders"
mkdir -p "$PROJ/references" "$PROJ/demos" "$PROJ/work" "$PROJ/output" "$PROJ/sfx" "$PROJ/music" "$PROJ/studio/public"
ok "references/ demos/ work/ output/ sfx/ music/ studio/public/"

echo
echo "Done. Next: put 5-10 clips of the motion style you want in references/, and any product"
echo "prototype or screen recordings in demos/. Optional: licensed SFX in sfx/, tracks in music/."
echo "Sound + delivery tools:  .motion/venv/bin/python \"$SKILL/scripts/motion.py\" --help"
echo "Preview the example:     cd studio && npx remotion studio src/index.ts"
