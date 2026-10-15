
#!/usr/bin/env bash
set -euo pipefail

# linkshort 在线备份脚本
# 用法: backup.sh [DB_PATH] [--keep-days N]
# 依赖: sqlite3 CLI

usage() {
  cat <<'EOF'
用法: backup.sh [DB_PATH] [--keep-days N]

参数:
  DB_PATH          数据库路径, 默认取 $LINKSHORT_DB 或 ./data/linkshort.db
  --keep-days N    保留最近 N 天的备份, 默认 7; 设为 0 表示不清理
  -h, --help       显示本帮助

环境变量:
  LINKSHORT_DB           数据库路径
  LINKSHORT_BACKUP_DIR   备份目录, 默认 ./backups

说明:
  使用 sqlite3 在线备份(.backup), 不需要停服.
  备份文件名: linkshort-YYYYmmdd-HHMMSS.db
EOF
}

DB_PATH="${LINKSHORT_DB:-./data/linkshort.db}"
BACKUP_DIR="${LINKSHORT_BACKUP_DIR:-./backups}"
KEEP_DAYS=7

# 解析参数
positional=()
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --keep-days)
      if [ $# -lt 2 ]; then
        echo "错误: --keep-days 需要一个参数" >&2
        usage >&2
        exit 2
      fi
      KEEP_DAYS="$2"
      shift 2
      ;;
    --keep-days=*)
      KEEP_DAYS="${1#--keep-days=}"
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

if [ "${#positional[@]}" -gt 1 ]; then
  echo "错误: 位置参数过多" >&2
  usage >&2
  exit 2
fi

if [ "${#positional[@]}" -eq 1 ]; then
  DB_PATH="${positional[0]}"
fi

case "$KEEP_DAYS" in
  ''|*[!0-9]*)
    echo "错误: --keep-days 必须是非负整数, 收到: $KEEP_DAYS" >&2
    exit 2
    ;;
esac

# 检查 sqlite3
if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "错误: 未找到 sqlite3 CLI, 请先安装 (Debian/Ubuntu: apt install sqlite3; macOS: brew install sqlite)" >&2
  exit 2
fi

# 检查源 DB
if [ ! -f "$DB_PATH" ]; then
  echo "错误: 数据库文件不存在: $DB_PATH" >&2
  exit 2
fi

# 准备备份目录
if ! mkdir -p "$BACKUP_DIR"; then
  echo "错误: 无法创建备份目录: $BACKUP_DIR" >&2
  exit 2
fi

TS="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/linkshort-$TS.db"

# 避免同秒覆盖
if [ -e "$DEST" ]; then
  echo "错误: 目标备份文件已存在: $DEST" >&2
  exit 2
fi

echo "[backup] 源: $DB_PATH"
echo "[backup] 目标: $DEST"
echo "[backup] 使用 sqlite3 在线备份(.backup)..."

# 先写临时名再改名, 避免半成品被当成有效备份
TMP_DEST="${DEST}.partial.$$"
cleanup() {
  if [ -e "$TMP_DEST" ]; then
    rm -f -- "$TMP_DEST"
  fi
}
trap cleanup EXIT

if ! sqlite3 "$DB_PATH" ".backup '$TMP_DEST'"; then
  echo "错误: sqlite3 .backup 失败" >&2
  exit 1
fi

if [ ! -s "$TMP_DEST" ]; then
  echo "错误: 备份文件为空: $TMP_DEST" >&2
  exit 1
fi

# 校验备份完整性
echo "[backup] 校验备份完整性(PRAGMA integrity_check)..."
CHECK_RESULT="$(sqlite3 "$TMP_DEST" 'PRAGMA integrity_check;' 2>&1 || true)"
if [ "$CHECK_RESULT" != "ok" ]; then
  echo "错误: 备份完整性校验失败: $CHECK_RESULT" >&2
  exit 1
fi

mv -- "$TMP_DEST" "$DEST"
trap - EXIT

echo "[backup] 完成: $DEST"

# 清理旧备份
if [ "$KEEP_DAYS" -gt 0 ]; then
  echo "[backup] 清理超过 $KEEP_DAYS 天的备份..."
  # 仅匹配本脚本命名格式 linkshort-YYYYmmdd-HHMMSS.db
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'linkshort-????????-??????.db' -mtime +"$KEEP_DAYS" -print0 \
    | while IFS= read -r -d '' old; do
        echo "[backup] 删除旧备份: $old"
        rm -f -- "$old"
      done
fi

echo "[backup] 成功"
exit 0
