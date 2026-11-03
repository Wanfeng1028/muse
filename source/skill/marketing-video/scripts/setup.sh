#!/usr/bin/env bash
# Create a self-contained video project: the scene template, the scripts and a
# local Playwright, so the project re-renders from its own folder months later.
# Usage: setup.sh <project-dir>
set -euo pipefail
PROJECT="${1:?usage: setup.sh <project-dir>   (a lowercase slug, no spaces)}"
SKILL="$(cd "$(dirname "$0")/.." && pwd)"

bash "$SKILL/scripts/check_deps.sh" || { echo "setup stopped: install the missing tools listed above, then rerun"; exit 2; }

mkdir -p "$PROJECT"/{assets,fonts,footage,audio,out,preview,versions}
[ -f "$PROJECT/scene.html" ] || cp "$SKILL/templates/scene.html" "$PROJECT/scene.html"
cp "$SKILL"/scripts/{build.py,preview.mjs,checks.mjs,render.mjs,audio.py,frames.py,inspect_inspiration.py} "$PROJECT/"
[ -f "$PROJECT/fonts.json" ] || echo '[]' > "$PROJECT/fonts.json"

cd "$PROJECT"
[ -f package.json ] || npm init -y >/dev/null
npm install --no-audit --no-fund playwright@^1 >/dev/null
npx playwright install chromium >/dev/null
echo "ready: $PROJECT"
