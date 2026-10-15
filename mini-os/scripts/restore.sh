#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 二进制选择：release/debug 哪个新用哪个（避免陈旧构建），MINI_OS_BIN 可覆盖
REL_BIN="$SCRIPT_DIR/../target/release/mini-os"
DBG_BIN="$SCRIPT_DIR/../target/debug/mini-os"
BIN=""
for cand in "$REL_BIN" "$DBG_BIN"; do
  if [ -x "$cand" ] && { [ -z "$BIN" ] || [ "$cand" -nt "$BIN" ]; }; then
    BIN="$cand"
  fi
done
if [ -n "${MINI_OS_BIN:-}" ]; then
  BIN="$MINI_OS_BIN"
fi

DB="${MINI_OS_DB:-$SCRIPT_DIR/../data/mini-os.db}"

if [ "$#" -lt 1 ]; then
  echo "用法：restore.sh <备份文件> [--force]" >&2
  exit 2
fi

BACKUP="$1"
shift

FORCE_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--force" ]; then
    FORCE_ARGS+=("--force")
  else
    echo "未知参数：$arg" >&2
    echo "用法：restore.sh <备份文件> [--force]" >&2
    exit 2
  fi
done

if [ ! -f "$BACKUP" ]; then
  echo "备份文件不存在：$BACKUP" >&2
  exit 2
fi

if [ ! -x "$BIN" ]; then
  echo "恢复失败：找不到可执行文件 $BIN" >&2
  exit 2
fi

echo "===================================================" >&2
echo "警告：恢复前请先停止 mini-os 服务" >&2
echo "===================================================" >&2
sleep 2

echo "开始恢复：db=$DB backup=$BACKUP" >&2
set +e
"$BIN" restore --db "$DB" --backup "$BACKUP" "${FORCE_ARGS[@]}"
RC=$?
set -e
exit "$RC"
