#!/usr/bin/env bash
# setup.sh [--voices] [--vision] [--enhance] [kit] — one-time setup for shenghua. Safe to re-run.
# --voices also fetches script mode's voice model (~350 MB) and the configured whisper
# word-alignment model (base by default, ~145 MB), once.
# --vision sets up the optional face detector: opencv-python-headless (pip) plus the YuNet model
# (~300 KB), recorded in config.json; without it every step works exactly as before.
# --enhance pip-installs deepfilternet (user-level) for enhance_voice.py's voice cleanup; never
# installed by default.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPTS_DIR")"
ASSETS_DIR="$SKILL_DIR/assets"
GSAP_VERSION="3.12.5"
KOKORO_DIR="${VV_KOKORO_DIR:-$HOME/.cache/shenghua/kokoro}"
KOKORO_URL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
YUNET_DIR="${VV_YUNET_DIR:-$HOME/.cache/shenghua/yunet}"
YUNET_MODEL="face_detection_yunet_2023mar.onnx"
YUNET_URL="https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/$YUNET_MODEL"
CONFIG_FILE="${VV_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/shenghua/config.json}"
VOICES=0
VISION=0
ENHANCE=0
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --voices) VOICES=1 ;;
    --vision) VISION=1 ;;
    --enhance) ENHANCE=1 ;;
    *) echo "unknown option $1 (usage: setup.sh [--voices] [--vision] [--enhance] [kit])" >&2; exit 1 ;;
  esac
  shift
done
missing=()

command -v ffmpeg >/dev/null || missing+=("ffmpeg (apt install ffmpeg · brew install ffmpeg)")
command -v node >/dev/null || missing+=("node >= 18")
command -v npm >/dev/null || missing+=("npm (needed to install playwright-core)")
command -v python3 >/dev/null || missing+=("python3 >= 3.10")
python3 -c "import faster_whisper" 2>/dev/null || missing+=("faster-whisper (pip install faster-whisper 'av<19')")
# PyAV 19 dropped the metadata_errors argument faster-whisper 1.2.1 passes; lift once faster-whisper supports it
python3 -c "import av, sys; sys.exit(int(av.__version__.split('.')[0]) >= 19)" 2>/dev/null \
  || ! python3 -c "import av" 2>/dev/null \
  || missing+=("PyAV < 19, faster-whisper cannot decode audio with 19+ (pip install 'av<19')")
python3 -c "import numpy" 2>/dev/null || missing+=("numpy (pip install numpy)")
if (( VOICES )); then
  python3 -c "import kokoro_onnx" 2>/dev/null || missing+=("kokoro-onnx, for script-mode voices (pip install kokoro-onnx)")
fi
if (( VISION )); then
  python3 -c "import cv2" 2>/dev/null || missing+=("opencv-python-headless, for face detection (pip install opencv-python-headless)")
fi

node_major=$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/') || node_major=0
(( node_major >= 18 )) || missing+=("node >= 18 (got $(node -v 2>/dev/null || echo none))")

python_minor=$(python3 --version 2>/dev/null | sed 's/.* 3\.\([0-9]*\).*/\1/') || python_minor=0
(( python_minor >= 10 )) || missing+=("python3 >= 3.10 (got $(python3 --version 2>/dev/null || echo none))")

# speak.py aligns word times with the configured whisper model; fetch it now so script mode never downloads mid-run
if (( VOICES )) && python3 -c "import faster_whisper" 2>/dev/null; then
  # config.json supplies the defaults transcribe.py and speak.py resolve the same way; flags there override it
  WHISPER_CFG=$(python3 - "$CONFIG_FILE" <<'PY'
import json, sys
try:
    cfg = json.load(open(sys.argv[1], encoding="utf-8")).get("whisper", {})
except FileNotFoundError:
    cfg = {}
except (json.JSONDecodeError, OSError) as e:
    print(f"cannot read {sys.argv[1]}: {e}", file=sys.stderr)
    print('Next: fix the JSON, e.g. {"whisper": {"model": "large-v3", "device": "cuda"}}', file=sys.stderr)
    sys.exit(1)
print(cfg.get("model") or "base", cfg.get("device") or "auto", cfg.get("compute_type") or "auto")
PY
  ) || exit 1
  read -r WHISPER_MODEL WHISPER_DEVICE WHISPER_COMPUTE <<< "$WHISPER_CFG"
  WHISPER_MODEL_PATH="${WHISPER_MODEL/#\~/$HOME}"
  echo "whisper settings · model=$WHISPER_MODEL device=$WHISPER_DEVICE compute=$WHISPER_COMPUTE (${CONFIG_FILE})"
  if [[ -d "$WHISPER_MODEL_PATH" ]]; then
    echo "whisper model ready · local folder $WHISPER_MODEL (used as-is, no download)"
  elif python3 -c 'from faster_whisper import download_model; import sys; download_model(sys.argv[1], local_files_only=True)' "$WHISPER_MODEL" 2>/dev/null; then
    echo "whisper model already cached · $WHISPER_MODEL (no download)"
  else
    echo "downloading the whisper model ($WHISPER_MODEL — large models are several GB)"
    if ! fetch_error=$(python3 -c 'from faster_whisper import download_model; import sys; download_model(sys.argv[1])' "$WHISPER_MODEL" 2>&1 >/dev/null); then
      echo "could not fetch the faster-whisper $WHISPER_MODEL model (speak.py word alignment): ${fetch_error##*$'\n'}"
      echo "Next: check the connection and the model name, then re-run setup.sh --voices"
      exit 1
    fi
    echo "whisper model ready · $WHISPER_MODEL"
  fi
fi

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "setup incomplete — missing ${#missing[@]}:"
  printf '  %s\n' "${missing[@]}"
  echo "Next: install the above, then re-run setup.sh"
  exit 1
fi

KIT_ARG="${1:-}"

# The catalogue's own typefaces (Fraunces, Oswald, Anton…) are shared by every kit; kit fonts install below
FONTS_URL=$(python3 - "$SKILL_DIR/templates/templates.json" <<'PY'
import json, sys
try:
    themes = json.load(open(sys.argv[1], encoding="utf-8")).get("templates", [])
except (json.JSONDecodeError, OSError) as e:
    print(f"cannot read theme catalogue {sys.argv[1]}: {e}", file=sys.stderr)
    print("Next: restore templates/templates.json from git", file=sys.stderr)
    sys.exit(1)
families = sorted({t["fonts"] for t in themes if t.get("fonts")})
print("https://fonts.googleapis.com/css2?" + "&".join("family=" + f for f in families) + "&display=swap")
PY
)

if [[ ! -d "$SCRIPTS_DIR/node_modules/playwright-core" ]]; then
  (cd "$SCRIPTS_DIR" && npm install --silent)
fi

# Each playwright-core release pins its own browser build; install is a no-op when the matching one is cached
(cd "$SCRIPTS_DIR" && node node_modules/playwright-core/cli.js install chromium-headless-shell >/dev/null)

mkdir -p "$ASSETS_DIR"
if [[ ! -f "$ASSETS_DIR/gsap.min.js" ]]; then
  curl -sfL -o "$ASSETS_DIR/gsap.min.js" "https://cdnjs.cloudflare.com/ajax/libs/gsap/$GSAP_VERSION/gsap.min.js"
fi

# Re-fetch whenever the catalogue's families change
if [[ ! -f "$ASSETS_DIR/fonts.css" || "$(cat "$ASSETS_DIR/fonts.url" 2>/dev/null)" != "$FONTS_URL" ]]; then
  rm -f "$ASSETS_DIR"/*.woff2
  # A desktop UA makes Google Fonts serve woff2
  curl -sf -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36" "$FONTS_URL" > "$ASSETS_DIR/fonts.css"
  grep -o 'https://fonts.gstatic.com[^)]*' "$ASSETS_DIR/fonts.css" | sort -u | while read -r url; do
    file="$(echo "$url" | sed 's#https://fonts.gstatic.com/s/##; s#/#-#g')"
    curl -sf -o "$ASSETS_DIR/$file" "$url"
    sed -i.bak "s#$url#$file#g" "$ASSETS_DIR/fonts.css" && rm -f "$ASSETS_DIR/fonts.css.bak"
  done
  echo "$FONTS_URL" > "$ASSETS_DIR/fonts.url"
fi

# Each kit installs into its own assets/kits/<id>/, so two clients' fonts never overwrite each other
if ! KIT_LINE=$(python3 "$SCRIPTS_DIR/brand_kit.py" install ${KIT_ARG:+"$KIT_ARG"} 2>&1); then
  echo "$KIT_LINE"
  exit 1
fi
KIT_NAME="${KIT_LINE%% installed*}"

if (( VOICES )); then
  mkdir -p "$KOKORO_DIR"
  for file in kokoro-v1.0.onnx voices-v1.0.bin; do
    # Download to a temp name so an interrupted fetch never leaves a truncated model behind
    if [[ ! -s "$KOKORO_DIR/$file" ]]; then
      echo "downloading $file → $KOKORO_DIR"
      if ! curl -sfL -o "$KOKORO_DIR/$file.part" "$KOKORO_URL/$file"; then
        echo "could not download $KOKORO_URL/$file"
        echo "Next: check the connection, or download it by hand into $KOKORO_DIR"
        exit 1
      fi
      mv "$KOKORO_DIR/$file.part" "$KOKORO_DIR/$file"
    fi
  done
  echo "voices ready · $KOKORO_DIR"
fi

if (( VISION )); then
  mkdir -p "$YUNET_DIR"
  # Download to a temp name so an interrupted fetch never leaves a truncated model behind
  if [[ ! -s "$YUNET_DIR/$YUNET_MODEL" ]]; then
    echo "downloading $YUNET_MODEL → $YUNET_DIR"
    if ! curl -sfL -o "$YUNET_DIR/$YUNET_MODEL.part" "$YUNET_URL"; then
      echo "could not download $YUNET_URL"
      echo "Next: check the connection, or download it by hand into $YUNET_DIR"
      exit 1
    fi
    mv "$YUNET_DIR/$YUNET_MODEL.part" "$YUNET_DIR/$YUNET_MODEL"
  fi
  # Smoke-test the detector, then record it in config.json for key_greenscreen.py and find_media.py
  if ! vision_error=$(python3 - "$CONFIG_FILE" "$YUNET_DIR/$YUNET_MODEL" <<'PY'
import json, os, sys
import cv2
cv2.FaceDetectorYN.create(sys.argv[2], "", (320, 320))
try:
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
except FileNotFoundError:
    cfg = {}
except (json.JSONDecodeError, OSError) as e:
    print(f"cannot read {sys.argv[1]}: {e}", file=sys.stderr)
    print('Next: fix the JSON, e.g. {"whisper": {"model": "base"}}', file=sys.stderr)
    sys.exit(1)
cfg["vision"] = {"available": True, "model": sys.argv[2]}
directory = os.path.dirname(sys.argv[1])
if directory:
    os.makedirs(directory, exist_ok=True)
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(cfg, handle, indent=2)
    handle.write("\n")
PY
  ); then
    echo "the YuNet face model failed to load: ${vision_error##*$'\n'}"
    echo "Next: delete $YUNET_DIR/$YUNET_MODEL and re-run setup.sh --vision"
    exit 1
  fi
  echo "vision ready · $YUNET_DIR/$YUNET_MODEL (recorded in $CONFIG_FILE)"
fi

if (( ENHANCE )); then
  if command -v deepFilter >/dev/null; then
    echo "enhance ready · $(command -v deepFilter)"
  else
    echo "installing deepfilternet (pip --user) for voice cleanup"
    if ! python3 -m pip install --user deepfilternet; then
      echo "could not install deepfilternet"
      echo "Next: pip install deepfilternet by hand, then re-run setup.sh --enhance"
      exit 1
    fi
    command -v deepFilter >/dev/null \
      || echo "note: deepFilter installed but not on PATH — add $(python3 -m site --user-base)/bin to it"
    echo "enhance ready · deepfilternet (user-level pip)"
  fi
fi

# YouTube clips are optional; everything else works without them
if ! command -v yt-dlp >/dev/null; then
  echo "optional: yt-dlp not found — YouTube clips disabled (pipx install yt-dlp)"
fi
# Face detection is optional too; without it framing and crops behave as they always have
if ! python3 -c "import cv2" 2>/dev/null; then
  echo "optional: opencv not found — face detection disabled (pip install opencv-python-headless, then setup.sh --vision)"
fi
# Voice cleanup is optional as well; enhance_voice.py reports it missing until then
if ! command -v deepFilter >/dev/null; then
  echo "optional: deepFilter not found — voice cleanup disabled (setup.sh --enhance)"
fi

echo "ready · kit $KIT_NAME"
if (( VOICES )); then
  echo "Next: write the script, then run speak.py (script mode) — or transcribe.py on a recording"
else
  echo "Next: run transcribe.py on your audio file"
fi
