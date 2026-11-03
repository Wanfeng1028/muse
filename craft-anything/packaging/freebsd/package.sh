#!/usr/bin/env bash
# Build and package Craft Anything for FreeBSD:
#
#   $DIST/craft-anything-<version>-freebsd-x86_64.tar.gz   a /usr/local-style tree:
#       craft-anything-<version>-freebsd-x86_64/{bin, share/applications, share/icons,
#       share/metainfo, share/doc/craft-anything}
#   bin/ holds craft-anything, plus craft-anything-cli once apps/craft-anything-cli exists.
#
# Install by copying the tree's contents into /usr/local:
#   tar -xzf craft-anything-<version>-freebsd-x86_64.tar.gz --strip-components 1 -C /usr/local
#
# Usage: packaging/freebsd/package.sh [--skip-build] [--dry-run]
#   --dry-run   stage the tree from stub binaries and list it, without building (works on any OS)
#
# Needs: bash, cargo, and the packages installed in .github/workflows/freebsd.yml.
set -euo pipefail
# shellcheck source=../env.sh
. "$(dirname "${BASH_SOURCE[0]}")/../env.sh"
LINUX="$ROOT/packaging/linux"
APP_ID=ai.storyteller.craft-anything

SKIP_BUILD=0
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-build) SKIP_BUILD=1; shift ;;
    --dry-run) DRY_RUN=1; SKIP_BUILD=1; shift ;;
    -h | --help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# FreeBSD's uname says amd64; release file names use x86_64 like the Linux and Windows ones.
# CARGO_BUILD_TARGET is set when the release VM cross-compiles aarch64 from an x86_64 guest.
MACHINE="$(uname -m)"
case "$MACHINE" in
  amd64 | x86_64) HOST_ARCH=x86_64 ;;
  arm64 | aarch64) HOST_ARCH=aarch64 ;;
  *) echo "unsupported architecture $MACHINE" >&2; exit 2 ;;
esac
ARCH="$HOST_ARCH"
if [[ -n "${CARGO_BUILD_TARGET:-}" ]]; then
  # cargo's host-tuple alias means the host triple; resolve it so the binary dir matches cargo's output.
  if [[ "$CARGO_BUILD_TARGET" = host-tuple ]]; then
    CARGO_BUILD_TARGET="$(rustc -vV | sed -n 's/^host: //p')"
    export CARGO_BUILD_TARGET
  fi
  case "$CARGO_BUILD_TARGET" in
    aarch64-unknown-freebsd) ARCH=aarch64 ;;
    x86_64-unknown-freebsd) ARCH=x86_64 ;;
    *)
      echo "error: unsupported CARGO_BUILD_TARGET $CARGO_BUILD_TARGET (use x86_64-unknown-freebsd or aarch64-unknown-freebsd)" >&2
      exit 2
      ;;
  esac
fi
if [ "$DRY_RUN" = 0 ] && [ "$(uname -s)" != FreeBSD ]; then
  echo "error: build on FreeBSD (or pass --dry-run to check the tree layout)" >&2
  exit 2
fi
BASENAME="craft-anything-$VERSION-freebsd-$ARCH"

echo "==> Craft Anything $VERSION for FreeBSD $ARCH"

# The release VM has 12 GB; full parallelism on the biggest crates runs it out of memory.
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-4}"
if [ "$SKIP_BUILD" = 0 ]; then
  (cd "$ROOT" && cargo build --release --locked "${CARGO_PKGS[@]}")
fi
WORK="$CARGO_TARGET_DIR/freebsd-package"
STAGE="$WORK/$BASENAME"
rm -rf "$WORK"
mkdir -p "$WORK"

BIN="$CARGO_TARGET_DIR/release"
if [[ -n "${CARGO_BUILD_TARGET:-}" ]]; then BIN="$CARGO_TARGET_DIR/$CARGO_BUILD_TARGET/release"; fi
OUT_DIR="$DIST"
if [ "$DRY_RUN" = 1 ]; then
  # Stub binaries, and the tarball stays in the work dir so dist/ only ever holds real builds.
  BIN="$WORK/stub-bin"
  OUT_DIR="$WORK"
  mkdir -p "$BIN"
  for b in "${BINS[@]}"; do
    printf '#!/bin/sh\necho "%s %s (dry-run stub)"\n' "$b" "$VERSION" >"$BIN/$b"
    chmod 755 "$BIN/$b"
  done
fi

# ---- stage a /usr/local-style tree --------------------------------------------------------------
# FreeBSD's install(1) has no -D: create the directories first.
mkdir -p "$STAGE/bin" "$STAGE/share/applications" \
  "$STAGE/share/metainfo" "$STAGE/share/icons" "$STAGE/share/doc/craft-anything"
for b in "${BINS[@]}"; do
  install -m 755 "$BIN/$b" "$STAGE/bin/"
  strip "$STAGE/bin/$b" 2>/dev/null || true
done
# The desktop entry, metainfo and icons are the freedesktop files Linux ships.
install -m 644 "$LINUX/$APP_ID.desktop" "$STAGE/share/applications/$APP_ID.desktop"
sed -e "s/@VERSION@/$VERSION/g" -e "s/@DATE@/$CRAFT_ANYTHING_BUILD_DATE/g" \
  "$LINUX/$APP_ID.metainfo.xml.in" >"$STAGE/share/metainfo/$APP_ID.metainfo.xml"
cp -R "$ROOT/assets/app-icon/hicolor" "$STAGE/share/icons/"
copy_docs "$STAGE/share/doc/craft-anything"
if [ -f "$ROOT/ATTRIBUTION.md" ]; then install -m 644 "$ROOT/ATTRIBUTION.md" "$STAGE/share/doc/craft-anything/"; fi

for f in "${BINS[@]/#/bin/}" "share/applications/$APP_ID.desktop" \
  "share/icons/hicolor/256x256/apps/$APP_ID.png" \
  share/doc/craft-anything/LICENSE-MIT share/doc/craft-anything/LICENSE-APACHE; do
  if [ ! -e "$STAGE/$f" ]; then echo "error: $f is missing from the package" >&2; exit 1; fi
done

# ---- .tar.gz ------------------------------------------------------------------------------------
mkdir -p "$OUT_DIR"
tar -C "$WORK" -czf "$OUT_DIR/$BASENAME.tar.gz" "$BASENAME"
echo "wrote $OUT_DIR/$BASENAME.tar.gz"

if [[ -n "${CARGO_BUILD_TARGET:-}" ]]; then
  echo "==> skipping $(smoke_bin) --version: CARGO_BUILD_TARGET is set, so the binary is not run on this host"
else
  "$STAGE/bin/$(smoke_bin)" --version
fi
if [ "$DRY_RUN" = 1 ]; then
  echo "==> dry run: tarball contents"
  tar -tzvf "$OUT_DIR/$BASENAME.tar.gz"
fi
echo "==> done"
