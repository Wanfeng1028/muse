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
  LINKSHORT_ALERT_WEBHOOK_URL   备份失败时 POST JSON 告警, 留空不通知

说明:
  使用 sqlite3 在线备份(.backup), 不需要停服.
  备份文件名: linkshort-YYYYmmdd-HHMMSS.db
EOF
}

DB_PATH="${LINKSHORT_DB:-./data/linkshort.db}"
BACKUP_DIR="${LINKSHORT_BACKUP_DIR:-./backups}"
KEEP_DAYS=7

# JSON 字符串最小转义: 反斜杠、双引号、换行/回车
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/ }"
  s="${s//$'\r'/ }"
  printf '%s' "$s"
}

# 写入 sidecar 状态文件(原子写入), 失败不致命
write_status() {
  local ok="$1" file="$2" integrity="$3" size="$4" error="$5"
  local finished_at tmp
  finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  tmp="$BACKUP_DIR/.last-backup.json.$$"
  if ! printf '{"ok":%s,"file":"%s","finished_at":"%s","integrity_check":"%s","size_bytes":%s,"error":"%s"}\n' \
      "$ok" "$(json_escape "$file")" "$finished_at" "$(json_escape "$integrity")" "$size" "$(json_escape "$error")" \
      > "$tmp" 2>/dev/null; then
    echo "[backup] 警告: 无法写入状态文件: $tmp" >&2
    rm -f -- "$tmp" 2>/dev/null || true
    return 0
  fi
  if ! mv -- "$tmp" "$BACKUP_DIR/last-backup.json" 2>/dev/null; then
    echo "[backup] 警告: 无法更新状态文件: $BACKUP_DIR/last-backup.json" >&2
    rm -f -- "$tmp" 2>/dev/null || true
  fi
  return 0
}

# 发送失败告警(仅在配置了 webhook 且 curl 可用时)
notify_failure() {
  local msg="$1"
  if [ -z "${LINKSHORT_ALERT_WEBHOOK_URL:-}" ]; then
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    return 0
  fi
  local payload time
  time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  payload="{\"source\":\"linkshort\",\"event\":\"backup_failed\",\"host\":\"$(hostname)\",\"db_path\":\"$(json_escape "$DB_PATH")\",\"backup_dir\":\"$(json_escape "$BACKUP_DIR")\",\"error\":\"$(json_escape "$msg")\",\"time\":\"$time\"}"
  curl -sS --max-time 10 -X POST -H 'Content-Type: application/json' -d "$payload" "$LINKSHORT_ALERT_WEBHOOK_URL" || { echo "[backup] 警告: 告警通知发送失败（已忽略）" >&2; }
}

# 运行时失败统一处理: 报错、写 sidecar、发告警、退出
fail() {
  local code="$1" msg="$2"
  echo "错误: $msg" >&2
  write_status "false" "" "" "0" "$msg"
  notify_failure "$msg"
  exit "$code"
}

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
  fail 2 "未找到 sqlite3 CLI, 请先安装 (Debian/Ubuntu: apt install sqlite3; macOS: brew install sqlite)"
fi

# 检查源 DB
if [ ! -f "$DB_PATH" ]; then
  fail 2 "数据库文件不存在: $DB_PATH"
fi

# 准备备份目录
if ! mkdir -p "$BACKUP_DIR"; then
  fail 2 "无法创建备份目录: $BACKUP_DIR"
fi

TS="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/linkshort-$TS.db"

# 避免同秒覆盖
if [ -e "$DEST" ]; then
  fail 2 "目标备份文件已存在: $DEST"
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
  fail 1 "sqlite3 .backup 失败"
fi

if [ ! -s "$TMP_DEST" ]; then
  fail 1 "备份文件为空: $TMP_DEST"
fi

# 校验备份完整性
echo "[backup] 校验备份完整性(PRAGMA integrity_check)..."
CHECK_RESULT="$(sqlite3 "$TMP_DEST" 'PRAGMA integrity_check;' 2>&1 || true)"
if [ "$CHECK_RESULT" != "ok" ]; then
  fail 1 "备份完整性校验失败: $CHECK_RESULT"
fi

mv -- "$TMP_DEST" "$DEST"
trap - EXIT

size_bytes="$(wc -c < "$DEST" | tr -d ' ')"
write_status "true" "$(basename "$DEST")" "ok" "$size_bytes" ""

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
