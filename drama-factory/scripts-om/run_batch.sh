#!/bin/bash
# usage: run_batch.sh <batch> [--skip-dpsk]
set -u
cd "$(dirname "$0")/.." || exit 1
B="$1"
SKIP="${2:-}"
if [ "$SKIP" != "--skip-dpsk" ]; then
  python3 scripts-om/make_prompt.py "$B" || exit 1
  python3 ~/workspace/muse-build/scripts/dpsk-call.py \
    --prompt-file "scripts-om/work/prompt-$B.txt" \
    --out "scripts-om/work/out-$B.txt" \
    --max-tokens 24576 --timeout 600 || exit 1
fi
python3 scripts-om/apply_out.py "$B"
