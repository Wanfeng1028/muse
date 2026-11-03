#!/usr/bin/env bash
# scripts/publish_npmjs.sh — 发布无 scope 包 openclaw-hy-memory 到 registry.npmjs.org
#
# 源码与发布包都在 plugins/openclaw/。
#
# Usage:
#   bash scripts/publish_npmjs.sh 1.1.8
#
# 鉴权（任选其一）:
#   ~/.npmrc 中 //registry.npmjs.org/:_authToken=...
#   export NPM_TOKEN=npm_...

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OPENCLAW="${ROOT}/plugins/openclaw"
VERSION="${1:-}"

if [[ -z "${VERSION}" ]]; then
  echo "Usage: bash scripts/publish_npmjs.sh <version>"
  echo "Example: bash scripts/publish_npmjs.sh 1.1.8"
  exit 1
fi

echo "→ build plugins/openclaw/"
(cd "${OPENCLAW}" && npm run build)

echo "→ set package version ${VERSION}"
node -e "
const fs = require('fs');
const path = '${OPENCLAW}/package.json';
const pkg = JSON.parse(fs.readFileSync(path, 'utf8'));
pkg.version = '${VERSION}';
fs.writeFileSync(path, JSON.stringify(pkg, null, 2) + '\n');
"

echo "→ publish openclaw-hy-memory@${VERSION} to registry.npmjs.org"
NPM_TOKEN_NPMJS="${NPM_TOKEN:-$(grep '//registry.npmjs.org/:_authToken=' "${HOME}/.npmrc" 2>/dev/null | cut -d= -f2- || true)}"
if [[ -z "${NPM_TOKEN_NPMJS}" ]]; then
  echo "ERROR: 需要 NPM_TOKEN 或 ~/.npmrc 中的 //registry.npmjs.org/:_authToken"
  exit 1
fi

(cd "${OPENCLAW}" && npm publish \
  --registry https://registry.npmjs.org/ \
  --//registry.npmjs.org/:_authToken="${NPM_TOKEN_NPMJS}")

echo "✓ Published: openclaw-hy-memory@${VERSION} → https://www.npmjs.com/package/openclaw-hy-memory"
