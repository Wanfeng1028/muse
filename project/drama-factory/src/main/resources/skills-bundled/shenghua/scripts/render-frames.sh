#!/usr/bin/env bash
# render-frames.sh [--blur N] [--resolution 1080|4k] [--force] <index.html> <frames-dir> <duration-seconds> [workers] [from-frame to-frame]
#
# Renders frames in parallel. Pass a frame range to re-render one shot after a fix.
# Frames already complete on disk at the requested quality are skipped, so re-running a killed render
# continues where it stopped; --force re-renders everything (needed after a composition change).
# Frames are supersampled lossless PNG; VV_QUALITY=draft renders fast 1x JPEG for a preview cut.
# --blur N (1-16) blends N sub-frames per frame into motion blur; --blur 4 renders ~8× slower.
# --resolution 4k exports VV_SCALE=2 so render.js saves the 2x device pixels at 2x (no downscale).
# Without --resolution the scale falls back to the fill's render.json next to index.html.
set -euo pipefail

BLUR=1
SCALE=""
FORCE=0
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --blur)
      BLUR="${2:-}"
      if ! [[ "$BLUR" =~ ^[1-9][0-9]*$ ]] || (( BLUR > 16 )); then
        echo "--blur must be an integer from 1 to 16, got: $BLUR"
        echo "Next: pass --blur 4 as the first two arguments, or drop it for a sharp render"
        exit 1
      fi
      shift 2 ;;
    --resolution)
      case "${2:-}" in
        1080|1080p) SCALE=1 ;;
        4k|2160|2160p) SCALE=2 ;;
        *) echo "--resolution must be 1080 or 4k, got: ${2:-<empty>}"
           echo "Next: pass --resolution 4k for a 4K master, or drop it for 1080p"
           exit 1 ;;
      esac
      shift 2 ;;
    --force) FORCE=1; shift ;;
    *) echo "Unknown option: $1"
       echo "Next: options are --blur N, --resolution 1080|4k and --force, then the positional arguments"
       exit 1 ;;
  esac
done

HTML="$1"
OUT="$2"
DURATION="$3"
WORKERS="${4:-10}"
FPS=30
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --resolution wins; otherwise the fill's render.json decides, so a 4k fill renders 4k by default
if [[ -z "$SCALE" ]]; then
  RENDER_JSON="$(dirname "$HTML")/render.json"
  if [[ -f "$RENDER_JSON" ]]; then
    SCALE=$(python3 -c "
import json, sys
try: print(json.load(open(sys.argv[1])).get('scale', 1))
except (OSError, ValueError): print(1)" "$RENDER_JSON")
    [[ "$SCALE" =~ ^[12]$ ]] || SCALE=1
  else
    SCALE=1
  fi
fi

if ! [[ "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "workers must be a positive integer, got: $WORKERS"
  echo "Next: pass a positive integer like 8 or 10"
  exit 1
fi

TOTAL=$(python3 -c "import math; print(math.ceil($DURATION * $FPS))")
FROM="${5:-0}"
TO="${6:-$TOTAL}"

if ! [[ "$FROM" =~ ^[0-9]+$ ]] || ! [[ "$TO" =~ ^[0-9]+$ ]]; then
  echo "frame range must be non-negative integers, got: $FROM $TO"
  echo "Next: pass the range as two integer frame numbers"
  exit 1
fi
if (( FROM >= TO )); then
  echo "frame range must satisfy from < to, got: $FROM $TO"
  echo "Next: pass a valid range, or omit the range to render all frames"
  exit 1
fi

SPAN=$(( TO - FROM ))
EXT=png
[[ "${VV_QUALITY:-}" == "draft" ]] && EXT=jpg
# render.js reads VV_SCALE: 1 saves the 2x device pixels supersampled to 1x, 2 saves them at 2x (4K)
export VV_SCALE="$SCALE"

mkdir -p "$OUT"

# Say what the frames will cost before spending it: PNG ~0.7 bytes/px, JPEG ~0.24 (measured on the demo shots)
python3 - "$(dirname "$HTML")/render.json" "$SPAN" "$SCALE" "$EXT" "$SCRIPTS_DIR" <<'PY'
import json, os, sys

render_json, span, scale, ext, scripts = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
width, height = 1080, 1920
try:
    info = json.load(open(render_json))
    width, height = int(info["width"]), int(info["height"])
except (OSError, ValueError, KeyError):
    pass
per_frame = width * height * scale * scale * (0.24 if ext == "jpg" else 0.7)
total = per_frame * span
print(f"{span} frames · ~{total / 1e9:.1f} GB of {ext.upper()}s in the frames dir")
if total > 4e9 and ext == "png":
    print(f"tip: {scripts}/render-chunks.sh renders the same video with no frames directory at all "
          f"(frames stream from Chromium into the encoder)")
PY

# A frame counts as done only if its file is whole: PNG ends in IEND, JPEG in EOI. A render killed
# mid-write leaves a truncated last frame, which must be re-rendered, not skipped.
PLAN=$(python3 - "$OUT" "$EXT" "$FROM" "$TO" "$WORKERS" "$FORCE" <<'PY'
import os, sys

out, ext, first, to, workers, force = sys.argv[1], sys.argv[2], *map(int, sys.argv[3:6]), sys.argv[6] == "1"

def complete(path):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if ext == "png":
                if size < 20:
                    return False
                handle.seek(-12, os.SEEK_END)
                return handle.read(12)[4:8] == b"IEND"
            if size < 4:
                return False
            handle.seek(-2, os.SEEK_END)
            return handle.read(2) == b"\xff\xd9"
    except OSError:
        return False

done, missing = 0, []
for f in range(first, to):
    if not force and complete(os.path.join(out, f"f{f:05d}.{ext}")):
        done += 1
    else:
        missing.append(f)

runs = []
for f in missing:
    if runs and f == runs[-1][1]:
        runs[-1][1] += 1
    else:
        runs.append([f, f + 1])

# Biggest runs first onto the least-loaded worker, so one long gap doesn't strand a single worker
buckets, load = [[] for _ in range(workers)], [0] * workers
for run in sorted(runs, key=lambda r: r[0] - r[1]):
    i = load.index(min(load))
    buckets[i].append(run)
    load[i] += run[1] - run[0]

print(done)
for bucket in buckets:
    print(",".join(f"{a}:{b}" for a, b in sorted(bucket)))
PY
) || { echo "Could not plan the render in $OUT"; echo "Next: check the frames directory is writable"; exit 1; }

PLAN_LINES=()
while IFS= read -r line; do PLAN_LINES+=("$line"); done <<< "$PLAN"
DONE_BASE="${PLAN_LINES[0]}"
WORKER_RUNS=("${PLAN_LINES[@]:1}")

pids=()
for (( i = 0; i < WORKERS; i++ )); do
  runs="${WORKER_RUNS[$i]:-}"
  [[ -z "$runs" ]] && continue
  (
    IFS=',' read -ra LIST <<< "$runs"
    for run in "${LIST[@]}"; do
      # Bounds are separate arguments on purpose: a single quoted "a b" renders zero frames silently
      node "$SCRIPTS_DIR/render.js" frames "$HTML" "$OUT" "${run%%:*}" "${run##*:}" "$BLUR"
    done
  ) &
  pids+=($!)
done

count_complete() {
  python3 - "$OUT" "$EXT" "$FROM" "$TO" <<'PY'
import os, sys
out, ext, first, to = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
n = 0
for f in range(first, to):
    path = os.path.join(out, f"f{f:05d}.{ext}")
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if ext == "png":
                ok = size >= 20 and (handle.seek(-12, os.SEEK_END) or True) and handle.read(12)[4:8] == b"IEND"
            else:
                ok = size >= 4 and (handle.seek(-2, os.SEEK_END) or True) and handle.read(2) == b"\xff\xd9"
        n += ok
    except OSError:
        pass
print(n)
PY
}

started=$(date +%s)
if (( ${#pids[@]} > 0 )); then
  # Poll the frames directory so an agent reading the log can see rate and time left
  while :; do
    alive=0
    for pid in "${pids[@]}"; do kill -0 "$pid" 2>/dev/null && alive=1 && break; done
    (( alive )) || break
    sleep 5
    now=$(date +%s)
    elapsed=$(( now - started ))
    (( elapsed > 0 )) || continue
    done_now=$(count_complete)
    rendered=$(( done_now - DONE_BASE ))
    python3 -c "
done_now, span, rendered, elapsed = $done_now, $SPAN, $rendered, $elapsed
fps = rendered / elapsed
left = (span - done_now) / fps if fps > 0 else 0
print(f'progress {done_now}/{span} frames · {fps:.1f} fps · {left / 60:.0f}m{left % 60:02.0f}s left' if fps > 0
      else f'progress {done_now}/{span} frames · starting…')"
  done
fi

failed=0
for pid in "${pids[@]:-}"; do [[ -n "$pid" ]] && { wait "$pid" || failed=$(( failed + 1 )); }; done

COMPLETE=$(count_complete)
ELAPSED=$(( $(date +%s) - started ))
RENDERED=$(( COMPLETE - DONE_BASE ))
(( FORCE )) && RENDERED=$COMPLETE
blur_note=""
(( BLUR > 1 )) && blur_note=" · blur $BLUR"
res_note=""
(( SCALE > 1 )) && res_note=" · 4k"
echo "$COMPLETE/$SPAN frames complete · $RENDERED rendered in ${ELAPSED}s$blur_note$res_note · $failed worker(s) failed · ${VV_QUALITY:-high} quality"
if (( COMPLETE < SPAN || failed > 0 )); then
  echo "Next: fix the first error printed above (PAGE ERROR = composition bug, Executable doesn't exist = run setup.sh), then re-run with the same range — complete frames are skipped"
  exit 1
fi
# render-chunks.sh encodes the frames itself, so the mix-encode pointer only makes sense standalone
[[ -n "${VV_FROM_CHUNKS:-}" ]] || echo "Next: run mix-encode.sh"

