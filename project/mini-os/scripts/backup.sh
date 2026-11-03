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

OUT_DIR="${MINI_OS_BACKUP_DIR:-$SCRIPT_DIR/../backups}"
DB="${MINI_OS_DB:-$SCRIPT_DIR/../data/mini-os.db}"

if [ ! -f "$DB" ]; then
  echo "数据库文件不存在：$DB" >&2
  exit 2
fi

if [ ! -x "$BIN" ]; then
  echo "备份失败：找不到可执行文件 $BIN" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUT_DIR/mini-os-$STAMP.db"

echo "开始备份：db=$DB out=$OUT" >&2
if ! "$BIN" backup --db "$DB" --out "$OUT"; then
  echo "备份失败：$BIN backup --db $DB --out $OUT" >&2
  exit 1
fi

if [ ! -f "$OUT" ]; then
  echo "备份失败：命令成功但未生成 $OUT" >&2
  exit 1
fi

# 仅保留最新 7 个备份（按文件名排序）
KEEP=7
mapfile -t ALL < <(ls -1 "$OUT_DIR"/mini-os-*.db 2>/dev/null | sort)
TOTAL="${#ALL[@]}"
if [ "$TOTAL" -gt "$KEEP" ]; then
  DELETE_COUNT=$((TOTAL - KEEP))
  for ((i = 0; i < DELETE_COUNT; i++)); do
    if ! rm -f "${ALL[$i]}"; then
      echo "清理旧备份失败：${ALL[$i]}" >&2
      exit 1
    fi
  done
fi

echo "备份完成：$OUT" >&2
echo "当前保留的备份（最多 $KEEP 个）：" >&2
mapfile -t KEPT < <(ls -1 "$OUT_DIR"/mini-os-*.db 2>/dev/null | sort)
for f in "${KEPT[@]}"; do
  echo "  $f" >&2
done
