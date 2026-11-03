# shellcheck shell=bash
# Shared setup for the packaging scripts. Source it: `. "$(dirname "$0")/../env.sh"`.
#
# Exports:
#   ROOT                  workspace root
#   VERSION               [workspace.package] version from Cargo.toml (override: CRAFT_ANYTHING_VERSION)
#   DIST                  output directory for release artifacts (default: $ROOT/dist/release)
#   CRAFT_ANYTHING_BUILD_SHA    git commit baked into the binaries (apps/craft-anything/build.rs)
#   CRAFT_ANYTHING_BUILD_DATE   UTC build date, YYYY-MM-DD
#   CARGO_TARGET_DIR      cargo's target dir (default: $ROOT/target)
# Sets (not exported):
#   BINS                  the binaries to build and ship: craft-anything, plus craft-anything-cli when the
#                         workspace has apps/craft-anything-cli
#   HAS_CLI               1 when craft-anything-cli is part of the build, else 0
#   CARGO_PKGS            `-p <bin>` arguments for cargo build

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT

# The version lives in exactly one place: `[workspace.package] version` in the root Cargo.toml.
# (`cargo xtask version` prints the same thing; awk avoids compiling xtask here.)
workspace_version() {
  awk '
    /^\[/ { in_pkg = ($0 == "[workspace.package]") ; next }
    in_pkg && $1 == "version" { gsub(/[" ]/, "", $3); print $3; exit }
  ' "$ROOT/Cargo.toml"
}

VERSION="${CRAFT_ANYTHING_VERSION:-$(workspace_version)}"
if [ -z "$VERSION" ]; then
  echo "error: could not read [workspace.package] version from $ROOT/Cargo.toml" >&2
  exit 1
fi
export VERSION

DIST="${DIST:-$ROOT/dist/release}"
mkdir -p "$DIST"
export DIST

if [ -z "${CRAFT_ANYTHING_BUILD_SHA:-}" ]; then
  CRAFT_ANYTHING_BUILD_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
fi
export CRAFT_ANYTHING_BUILD_SHA
export CRAFT_ANYTHING_BUILD_DATE="${CRAFT_ANYTHING_BUILD_DATE:-$(date -u +%Y-%m-%d)}"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$ROOT/target}"

# The headless CLI ships next to the app once apps/craft-anything-cli exists.
BINS=(craft-anything)
HAS_CLI=0
if [ -f "$ROOT/apps/craft-anything-cli/Cargo.toml" ]; then
  BINS+=(craft-anything-cli)
  HAS_CLI=1
fi
CARGO_PKGS=()
for _bin in "${BINS[@]}"; do CARGO_PKGS+=(-p "$_bin"); done
unset _bin

# The binary used for a `--version` smoke test: the CLI when shipped, else the app (which answers
# --version before opening a window).
smoke_bin() {
  if [ "$HAS_CLI" = 1 ]; then echo craft-anything-cli; else echo craft-anything; fi
}

# Emit a GitHub Actions warning (plain stderr outside Actions).
# Run a command up to five times, 15 s apart: for steps that ask a remote service (Apple's
# notarization ticket service drops connections now and then).
retry() {
  local attempt
  for attempt in 1 2 3 4 5; do
    "$@" && return 0
    [ "$attempt" = 5 ] || { echo "retrying ($attempt/5): $*" >&2; sleep 15; }
  done
  return 1
}

warn() {
  if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::warning::$*"; else echo "warning: $*" >&2; fi
}

# Copy licence and readme files that exist into a package directory.
copy_docs() {
  local dest="$1" f
  for f in README.md LICENSE LICENSE-MIT LICENSE-APACHE NOTICE COPYRIGHT; do
    if [ -f "$ROOT/$f" ]; then cp "$ROOT/$f" "$dest/"; fi
  done
  copy_font_licences "$dest"
}

# The app embeds the fonts in assets/fonts (OFL-1.1) and, built with CRAFT_FONTS_DIR (releases),
# craft-fonts' too: ship their licences next to the binaries (craft-fonts' as OFL-<font>.txt).
copy_font_licences() {
  local dest="$1" lic
  for lic in "$ROOT"/assets/fonts/OFL-*.txt "${CRAFT_FONTS_DIR:-/nonexistent}"/fonts/*/OFL.txt; do
    [ -f "$lic" ] || continue
    case "$lic" in
      */fonts/*/OFL.txt) cp "$lic" "$dest/OFL-$(basename "$(dirname "$lic")").txt" ;;
      *) cp "$lic" "$dest/" ;;
    esac
  done
}

# Portable SHA-256 of a file (prints just the hash).
sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi
}
