#!/usr/bin/env bash
set -euo pipefail

# Build an unsigned macOS directory artifact from the current source tree.
# A caller may pin ONE_MEMORY_BUILD_NUMBER; otherwise the current repository
# revision count provides a monotonic local build number.
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
core_binary="$repo_root/apps/core/dist/one-memory-runtime/one-memory"

if [[ ! -x "$core_binary" ]]; then
  echo "missing packaged Core; run pnpm build:core:mac first" >&2
  exit 2
fi
if [[ -n "$(find "$repo_root/apps/core/src" "$repo_root/apps/core/one-memory.spec" \
  -type f -newer "$core_binary" -print -quit)" ]]; then
  echo "packaged Core is stale; run pnpm build:core:mac first" >&2
  exit 2
fi

if [[ -z "${ONE_MEMORY_BUILD_NUMBER:-}" ]]; then
  ONE_MEMORY_BUILD_NUMBER="$(
    git -C "$repo_root" rev-list --count HEAD
  )"
fi
if [[ ! "$ONE_MEMORY_BUILD_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "invalid ONE_MEMORY_BUILD_NUMBER: $ONE_MEMORY_BUILD_NUMBER" >&2
  exit 2
fi

export ONE_MEMORY_BUILD_NUMBER
if [[ -z "${ONE_MEMORY_VERSION:-}" ]]; then
  ONE_MEMORY_VERSION="$(
    node -p "require('$repo_root/package.json').version"
  )"
fi
if ! node -e \
  "require('$repo_root/scripts/release-version.cjs').assertSemver(process.argv[1], 'ONE_MEMORY_VERSION')" \
  "$ONE_MEMORY_VERSION"; then
  echo "invalid ONE_MEMORY_VERSION: $ONE_MEMORY_VERSION" >&2
  exit 2
fi
export ONE_MEMORY_VERSION
ONE_MEMORY_COMMIT="$(git -C "$repo_root" rev-parse HEAD)"
export ONE_MEMORY_COMMIT

cd "$repo_root/apps/desktop"
pnpm exec electron-builder --mac dir --arm64 \
  -c.mac.identity=null \
  -c.extraMetadata.version="$ONE_MEMORY_VERSION" \
  -c.buildVersion="$ONE_MEMORY_BUILD_NUMBER"

plist="$repo_root/apps/desktop/release/mac-arm64/MemHub.app/Contents/Info.plist"
readback="$(
  /usr/libexec/PlistBuddy -c \
    'Print :LSEnvironment:ONE_MEMORY_BUILD_NUMBER' "$plist" 2>/dev/null || true
)"
if [[ "$readback" != "$ONE_MEMORY_BUILD_NUMBER" ]]; then
  echo "packaged build_number readback mismatch: expected=$ONE_MEMORY_BUILD_NUMBER actual=${readback:-<missing>}" >&2
  exit 3
fi
visible_version="$(
  /usr/libexec/PlistBuddy -c \
    'Print :CFBundleShortVersionString' "$plist" 2>/dev/null || true
)"
if [[ "$visible_version" != "$ONE_MEMORY_VERSION" ]]; then
  echo "packaged version readback mismatch: expected=$ONE_MEMORY_VERSION actual=${visible_version:-<missing>}" >&2
  exit 3
fi
