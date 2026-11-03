
#!/usr/bin/env bash
set -euo pipefail

# linkshort 恢复脚本
# 用法: restore.sh <备份文件> [--force] [--dry-run]
# 危险操作: 默认拒绝执行, 需显式 --force

usage() {
  cat <<'EOF'
用法: restore.sh <备份文件> [--force] [--dry-run]

参数:
  备份文件         要恢复的 .db 备份路径
  --force          确认执行恢复(必须先停服)
  --dry-run        只打印将要执行的步骤, 不实际执行
  -h, --help       显示本帮助

环境变量:
  LINKSHORT_DB   目标数据库路径, 默认 ./data/linkshort.db

流程:
  1. 校验备份文件(PRAGMA integrity_check), 失败则拒绝
  2. 若目标 DB 存在, 先做 .broken-<时间戳> 快照留底
  3. 用备份覆盖目标 DB(含清理 -wal/-shm)
  4. 恢复后再次 integrity_check
EOF
}

DB_PATH="${LINKSHORT_DB:-./data/linkshort.db}"
BACKUP_FILE=""
FORCE=0
DRY_RUN=0

if [ $# -eq 0 ]; then
  usage >&2
  exit 2
fi

positional=()
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -*)
      echo "错误: 未知选项 $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      positional+=("$1")
      shift
      ;;
  esac
done

if [ "${#positional[@]}" -ne 1 ]; then
  echo "错误: 必须且只能指定一个备份文件" >&2
  usage >&2
  exit 2
fi

BACKUP_FILE="${positional[0]}"

# 检查 sqlite3
if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "错误: 未找到 sqlite3 CLI, 请先安装 (Debian/Ubuntu: apt install sqlite3; macOS: brew install sqlite)" >&2
  exit 2
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "错误: 备份文件不存在: $BACKUP_FILE" >&2
  exit 2
fi

if [ "$DRY_RUN" -eq 0 ] && [ "$FORCE" -ne 1 ]; then
  echo "错误: 这是危险操作, 会覆盖目标数据库。" >&2
  echo "      请先停服, 然后加 --force 重试:" >&2
  echo "      $0 $BACKUP_FILE --force" >&2
  exit 3
fi

echo "[restore] 备份文件: $BACKUP_FILE"
echo "[restore] 目标 DB: $DB_PATH"

# 1. 校验备份
echo "[restore] 校验备份完整性(PRAGMA integrity_check)..."
CHECK_RESULT="$(sqlite3 "$BACKUP_FILE" 'PRAGMA integrity_check;' 2>&1 || true)"
if [ "$CHECK_RESULT" != "ok" ]; then
  echo "错误: 备份文件完整性校验失败, 拒绝恢复: $CHECK_RESULT" >&2
  exit 4
fi
echo "[restore] 备份校验通过"

TS="$(date +%Y%m%d-%H%M%S)"
BROKEN="${DB_PATH}.broken-$TS"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[restore] (dry-run) 将执行以下步骤:"
  if [ -e "$DB_PATH" ]; then
    echo "  - 备份现有 DB -> $BROKEN"
  else
    echo "  - 目标 DB 不存在, 跳过快照"
  fi
  echo "  - 清理 ${DB_PATH}-wal / ${DB_PATH}-shm (如存在)"
  echo "  - 复制 $BACKUP_FILE -> $DB_PATH"
  echo "  - 再次 PRAGMA integrity_check"
  echo "[restore] dry-run 完成, 未做任何修改"
  exit 0
fi

# 2. 现有 DB 快照
if [ -e "$DB_PATH" ]; then
  echo "[restore] 留底现有 DB: $DB_PATH -> $BROKEN"
  cp -p -- "$DB_PATH" "$BROKEN"
else
  echo "[restore] 目标 DB 不存在, 跳过快照"
fi

# 3. 恢复: 直接操作目标路径, 不用 /tmp
echo "[restore] 清理 WAL/SHM..."
rm -f -- "${DB_PATH}-wal" "${DB_PATH}-shm"

echo "[restore] 写入目标 DB..."
cp -p -- "$BACKUP_FILE" "$DB_PATH"

# 4. 恢复后校验
echo "[restore] 恢复后校验(PRAGMA integrity_check)..."
POST_CHECK="$(sqlite3 "$DB_PATH" 'PRAGMA integrity_check;' 2>&1 || true)"
if [ "$POST_CHECK" != "ok" ]; then
  echo "错误: 恢复后完整性校验失败: $POST_CHECK" >&2
  echo "      现有 DB 快照保留在: $BROKEN" >&2
  exit 4
fi

echo "[restore] 成功"
echo "[restore] 旧 DB 快照: $BROKEN"
exit 0
