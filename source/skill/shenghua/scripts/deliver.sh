#!/usr/bin/env bash
# deliver.sh [--cover <seconds>] <work-dir> <master.mp4>
#
# Assembles <work-dir>/delivery/: the master mp4, a web copy (~8 Mbps, re-targeted below 40% of the
# master's bitrate when the master is small so the copy lands under half its size), any
# captions.srt/captions.vtt, a cover frame (default 1.0s in, where the title card sits), credits.txt
# from credits.json and a README.txt listing the folder.
set -euo pipefail

COVER=""
if [[ "${1:-}" == "--cover" ]]; then
  COVER="${2:-}"
  if [[ -z "$COVER" ]]; then
    echo "--cover needs a time in seconds"
    echo "Next: pass e.g. --cover 12.5 before the work dir"
    exit 1
  fi
  shift 2
fi

WORK="$1"
MASTER="$2"
[[ -f "$MASTER" ]] || { echo "No master at $MASTER"; echo "Next: run mix-encode.sh first"; exit 1; }

DELIV="$WORK/delivery"
mkdir -p "$DELIV"
BASE="$(basename "$MASTER" .mp4)"

DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$MASTER")
MASTER_BYTES=$(python3 -c "import os; print(os.path.getsize('$MASTER'))")
MASTER_DIMS=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$MASTER")

# Master
if [[ "$MASTER" != "$DELIV/$BASE.mp4" ]]; then
  cp "$MASTER" "$DELIV/$BASE.mp4"
fi

# Web copy: 8 Mbps for platforms and chat apps; a small master gets a smaller target instead,
# because the copy must come out under half the master's size
WEB="$DELIV/$BASE-web.mp4"
WEB_KBPS=$(python3 -c "print(max(200, int(min(8000, 0.4 * $MASTER_BYTES * 8 / 1000 / float('$DUR')))))")
encode_web() {
  ffmpeg -v error -y -i "$MASTER" \
    -map 0:v -map '0:a?' \
    -vf "format=yuv420p" \
    -c:v libx264 -preset slow -b:v "${1}k" -maxrate "${1}k" -bufsize "$(( $1 * 2 ))k" \
    -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
    -c:a aac -b:a 160k -movflags +faststart "$WEB"
}
encode_web "$WEB_KBPS"
WEB_BYTES=$(python3 -c "import os; print(os.path.getsize('$WEB'))")
if (( WEB_BYTES * 2 >= MASTER_BYTES )); then
  encode_web $(( WEB_KBPS / 2 ))
  WEB_BYTES=$(python3 -c "import os; print(os.path.getsize('$WEB'))")
fi
HALF_NOTE=""
if (( WEB_BYTES * 2 >= MASTER_BYTES )); then
  HALF_NOTE=" · ⚠ web copy over half the master size (master too small to undercut)"
fi

# Captions ship as files so platforms can index and translate them
CAPTIONS=""
for ext in srt vtt; do
  if [[ -f "$WORK/captions.$ext" ]]; then
    cp "$WORK/captions.$ext" "$DELIV/$BASE.$ext"
    CAPTIONS+="$ext "
  fi
done

# Cover frame
if [[ -z "$COVER" ]]; then
  COVER=$(python3 -c "print('{:.3f}'.format(min(1.0, max(0.0, float('$DUR') - 0.1))))")
fi
ffmpeg -v error -y -ss "$COVER" -i "$MASTER" -frames:v 1 "$DELIV/$BASE-cover.png"

# credits.txt mirrors find_media.py's credits report so the folder is self-contained
CREDITS=$(python3 - "$WORK" "$DELIV/credits.txt" <<'PY'
import json, sys
work, out = sys.argv[1], sys.argv[2]
try:
    with open(work + "/credits.json", encoding="utf-8") as f:
        entries = json.load(f)
except FileNotFoundError:
    entries = []
lines = []
if entries:
    for c in list({c["source"]: c for c in entries}.values()):
        flag = "  ⚠ unlicensed" if c.get("unlicensed") else ""
        lines.append(f"{c['title']} — {c['author']} — {c['license']} — {c['source']}{flag}")
else:
    lines.append("No external media was fetched for this video.")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(len(entries))
PY
)

MB_M=$(python3 -c "print('{:.1f}'.format($MASTER_BYTES / 1048576))")
MB_W=$(python3 -c "print('{:.1f}'.format($WEB_BYTES / 1048576))")
WEB_MBPS=$(python3 -c "print('{:.1f}'.format($WEB_BYTES * 8 / 1000000 / float('$DUR')))")

{
  echo "Delivery — $BASE"
  echo "===================="
  echo
  echo "$BASE.mp4          master · $MASTER_DIMS · ${DUR}s · ${MB_M} MB"
  echo "$BASE-web.mp4      web copy · ~${WEB_MBPS} Mbps · ${MB_W} MB"
  echo "$BASE-cover.png    cover frame at ${COVER}s"
  for ext in srt vtt; do
    [[ -f "$DELIV/$BASE.$ext" ]] && echo "$BASE.$ext          captions ($([[ $ext == srt ]] && echo SubRip || echo WebVTT))"
  done
  echo "credits.txt        third-party media credits ($CREDITS)"
  echo "README.txt         this file"
} > "$DELIV/README.txt"

echo "delivery/ · master ${MB_M} MB · web ${MB_W} MB${HALF_NOTE} · cover at ${COVER}s · captions: ${CAPTIONS:-none} · $CREDITS credit(s)"
echo "Next: open $DELIV, play the web copy and look at the cover frame before sending it"
