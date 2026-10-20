#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
sibling_audio_qa="$script_dir/../../sound-design/scripts/audio_qa.py"
if [ -n "${AUDIO_QA:-}" ]; then audio_qa="$AUDIO_QA"
elif [ -f "$sibling_audio_qa" ]; then audio_qa="$sibling_audio_qa"
else audio_qa="$HOME/.claude/skills/sound-design/scripts/audio_qa.py"; fi

usage() {
  cat <<'EOF'
render_masters.sh: render upload masters for every composition x props variant, then run qa_video.py and audio_qa.py.

Usage: render_masters.sh [options] <composition> [<composition> ...]
Options:
  --variant NAME[=PROPS_JSON]  repeatable; one master per variant, suffixed -NAME (default: one unsuffixed master)
  --name COMPOSITION=BASE      repeatable; output base name per composition (default: the composition id)
  --entry PATH                 Remotion entry point (default: project config)
  --out-dir DIR                default out/final
  --crf N                      default 16 (platforms re-compress; give them headroom)
  --audio-bitrate RATE         default 320k (AAC)
  --image-format jpeg|png      frame capture format, default jpeg (png for heavy transparency, blur or banding)
  --jpeg-quality N             default 95
  --frames A-B                 render only a frame range (quick tests); output gets a -fA-B suffix
  --qa-args "ARGS"             extra qa_video.py args, e.g. "--ignore 0 --final-hold 1.5 --beats 95:0.2"
  --audio-qa-args "ARGS"       extra audio_qa.py args, e.g. "--target-lufs -14"
  --no-qa                      skip both QA scripts
  --lock-timeout SECONDS       wait for the machine-wide render lock, default 3600
Flags used: h264, yuv420p, --color-space=bt709, AAC. One render at a time per machine: a mkdir lock in $TMPDIR
(override the path with VIDEO_DIRECTOR_LOCK). Run from the Remotion project root. Exit 1 if a render or QA fails.
Example: render_masters.sh Wide Tall --name Wide=film-16x9 --name Tall=film-9x16 \
           --variant sofia='{"voice":"sofia"}' --variant catalina='{"voice":"catalina"}' --qa-args "--ignore 0"
EOF
}

variant_names=(); variant_props=(); name_map=""
entry=""; out_dir="out/final"; crf=16; audio_bitrate=320k; image_format=jpeg; jpeg_quality=95
frames=""; qa_args=""; audio_qa_args=""; run_qa=1; lock_timeout=3600; compositions=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --variant)
      case "$2" in
        *=*) variant_names+=("${2%%=*}"); variant_props+=("${2#*=}") ;;
        *) variant_names+=("$2"); variant_props+=("") ;;
      esac
      shift 2 ;;
    --name) name_map="$name_map"$'\n'"$2"; shift 2 ;;
    --entry) entry="$2"; shift 2 ;;
    --out-dir) out_dir="$2"; shift 2 ;;
    --crf) crf="$2"; shift 2 ;;
    --audio-bitrate) audio_bitrate="$2"; shift 2 ;;
    --image-format) image_format="$2"; shift 2 ;;
    --jpeg-quality) jpeg_quality="$2"; shift 2 ;;
    --frames) frames="$2"; shift 2 ;;
    --qa-args) qa_args="$2"; shift 2 ;;
    --audio-qa-args) audio_qa_args="$2"; shift 2 ;;
    --no-qa) run_qa=0; shift ;;
    --lock-timeout) lock_timeout="$2"; shift 2 ;;
    -*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) compositions+=("$1"); shift ;;
  esac
done
if [ "${#compositions[@]}" -eq 0 ]; then usage >&2; exit 2; fi
case "$image_format" in jpeg|png) ;; *) echo "--image-format must be jpeg or png" >&2; exit 2 ;; esac
if [ "${#variant_names[@]}" -eq 0 ]; then variant_names=(""); variant_props=(""); fi

lock_dir="${VIDEO_DIRECTOR_LOCK:-${TMPDIR:-/tmp}/video-director-render.lock}"
lock_dir="${lock_dir%/}"

release_lock() {
  if [ -f "$lock_dir/pid" ] && [ "$(cat "$lock_dir/pid" 2>/dev/null)" = "$$" ]; then rm -rf "$lock_dir"; fi
}

acquire_lock() {
  local waited=0 owner
  while ! mkdir "$lock_dir" 2>/dev/null; do
    owner=$(cat "$lock_dir/pid" 2>/dev/null || true)
    if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
      echo "removing stale render lock from pid $owner" >&2
      rm -rf "$lock_dir"
      continue
    fi
    if [ "$waited" -ge "$lock_timeout" ]; then
      echo "render lock $lock_dir still held by pid ${owner:-unknown} after ${lock_timeout}s" >&2
      exit 1
    fi
    [ $(( waited % 60 )) -eq 0 ] && echo "waiting for render lock held by pid ${owner:-unknown} ($lock_dir)" >&2
    sleep 5
    waited=$(( waited + 5 ))
  done
  echo "$$" > "$lock_dir/pid"
  trap release_lock EXIT
  trap 'release_lock; exit 130' INT TERM
}

base_name_for() {
  local composition="$1" line
  while IFS= read -r line; do
    if [ "${line%%=*}" = "$composition" ] && [ -n "$line" ]; then echo "${line#*=}"; return; fi
  done <<< "$name_map"
  echo "$composition"
}

render_one() {
  local composition="$1" output="$2" props="$3"
  local command=(npx remotion render)
  [ -n "$entry" ] && command+=("$entry")
  command+=("$composition" "$output" --codec=h264 "--crf=$crf" "--audio-bitrate=$audio_bitrate" --color-space=bt709
    --pixel-format=yuv420p "--image-format=$image_format" --log=error)
  [ "$image_format" = "jpeg" ] && command+=("--jpeg-quality=$jpeg_quality")
  [ -n "$props" ] && command+=("--props=$props")
  [ -n "$frames" ] && command+=("--frames=$frames")
  echo "\$ ${command[*]}"
  "${command[@]}"
}

run_quality_checks() {
  local output="$1" status=0
  # shellcheck disable=SC2086
  "$script_dir/qa_video.py" "$output" --json $qa_args || status=1
  # shellcheck disable=SC2086
  "$audio_qa" "$output" --json $audio_qa_args || status=1
  return "$status"
}

acquire_lock
mkdir -p "$out_dir"
failures=()
written=()
for composition in "${compositions[@]}"; do
  base=$(base_name_for "$composition")
  for index in "${!variant_names[@]}"; do
    variant="${variant_names[$index]}"
    suffix="${variant:+-$variant}${frames:+-f$frames}"
    output="$out_dir/$base$suffix.mp4"
    if ! render_one "$composition" "$output" "${variant_props[$index]}"; then
      failures+=("$output (render)")
      continue
    fi
    echo "rendered $output"
    written+=("$output")
    if [ "$run_qa" = 1 ] && ! run_quality_checks "$output"; then failures+=("$output (QA)"); fi
  done
done

echo "masters: ${written[*]:-none}"
if [ "${#failures[@]}" -gt 0 ]; then
  printf 'FAIL: %s\n' "${failures[@]}"
  exit 1
fi
echo "PASS: ${#written[@]} master(s)"
