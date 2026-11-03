
#!/usr/bin/env bash
set -euo pipefail

# linkshort 备份恢复自动化演练脚本 (v1.7)
#
# 一键跑完: 备份 -> 停服 -> 删库 -> 恢复 -> 重启 -> 一致性校验
#
# 用法: backup-drill.sh [--addr 127.0.0.1:PORT] [--keep] [--timeout N] [-h|--help]
#
# 参数:
#   --addr 127.0.0.1:PORT  演练服务监听地址, 默认 127.0.0.1:18080; 端口被占则报错
#   --keep                 保留隔离工作区(不清理), 打印路径供排查
#   --timeout N            readyz 就绪轮询最长等待秒数, 默认 30
#   -h, --help             显示本帮助
#
# 退出码:
#   0   演练通过
#   2   参数或依赖错误(缺 sqlite3/go/curl, 端口占用, 参数非法)
#   非零 其他值 = 演练某步骤失败
#
# 环境变量:
#   本脚本自身不需要环境变量; 内部为子进程 backup.sh / restore.sh 设置:
#   LINKSHORT_DB / LINKSHORT_BACKUP_DIR / LINKSHORT_ADMIN_KEY / LINKSHORT_ADDR
#
# 说明:
#   演练全程在 mktemp -d 隔离工作区进行, 不碰仓库的 data/ 与 backups/.
#   --keep 时保留工作区并在结束时打印路径.

usage() {
  cat <<'EOF'
用法: backup-drill.sh [--addr 127.0.0.1:PORT] [--keep] [--timeout N] [-h|--help]

参数:
  --addr 127.0.0.1:PORT  演练服务监听地址, 默认 127.0.0.1:18080; 端口被占则报错
  --keep                 保留隔离工作区(不清理), 打印路径供排查
  --timeout N            readyz 就绪轮询最长等待秒数, 默认 30
  -h, --help             显示本帮助

退出码:
  0   演练通过
  2   参数或依赖错误(缺 sqlite3/go/curl, 端口占用, 参数非法)
  非零 其他值 = 演练某步骤失败

说明:
  演练全程在 mktemp -d 隔离工作区进行, 不碰仓库的 data/ 与 backups/.
  --keep 时保留工作区并在结束时打印路径.
EOF
}

log()  { echo "[drill] $*"; }
fail() {
  # fail <步骤名> <原因>
  local step="$1"; shift
  local reason="$*"
  echo "[drill] FAIL ${step}: ${reason}" >&2
  exit 1
}
die_usage() {
  echo "错误: $*" >&2
  usage >&2
  exit 2
}

ADDR="127.0.0.1:18080"
KEEP=0
TIMEOUT=30

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --addr)
      [ $# -ge 2 ] || die_usage "--addr 需要一个参数"
      ADDR="$2"; shift 2
      ;;
    --addr=*)
      ADDR="${1#--addr=}"; shift
      ;;
    --keep)
      KEEP=1; shift
      ;;
    --timeout)
      [ $# -ge 2 ] || die_usage "--timeout 需要一个参数"
      TIMEOUT="$2"; shift 2
      ;;
    --timeout=*)
      TIMEOUT="${1#--timeout=}"; shift
      ;;
    -*)
      die_usage "未知选项 $1"
      ;;
    *)
      die_usage "位置参数过多: $1"
      ;;
  esac
done

case "$TIMEOUT" in
  ''|*[!0-9]*) die_usage "--timeout 必须是非负整数, 收到: $TIMEOUT" ;;
esac
[ "$TIMEOUT" -gt 0 ] || die_usage "--timeout 必须大于 0"

# 依赖检查
for dep in sqlite3 go curl; do
  if ! command -v "$dep" >/dev/null 2>&1; then
    echo "错误: 未找到 $dep, 请先安装" >&2
    exit 2
  fi
done

# 从 addr 拆出端口用于占用探测
ADDR_HOST="${ADDR%:*}"
ADDR_PORT="${ADDR##*:}"
case "$ADDR_PORT" in
  ''|*[!0-9]*) die_usage "--addr 格式非法: $ADDR" ;;
esac

# 端口占用探测
if (echo > "/dev/tcp/${ADDR_HOST}/${ADDR_PORT}") >/dev/null 2>&1; then
  echo "错误: 端口 ${ADDR_HOST}:${ADDR_PORT} 已被占用, 请用 --addr 指定其他地址" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WORK="$(mktemp -d)"
DRILL_DB="$WORK/drill.db"
DRILL_BACKUP_DIR="$WORK/backups"
BIN="$WORK/drill-linkshort"
LOG_FILE="$WORK/server.log"
SERVER_PID=""

cleanup() {
  local rc=$?
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [ "$KEEP" -eq 1 ]; then
    echo "[drill] 保留工作区: $WORK"
  else
    rm -rf -- "$WORK" 2>/dev/null || true
  fi
  return $rc
}
trap cleanup EXIT

log "工作区: $WORK"
log "仓库根: $ROOT"
log "监听地址: $ADDR"

# 随机 admin key
if command -v openssl >/dev/null 2>&1; then
  ADMIN_KEY="$(openssl rand -hex 16)"
else
  ADMIN_KEY="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
fi

# ---- 步骤 2: 构建 ----
log "构建二进制..."
if ! (cd "$ROOT" && go build -o "$BIN" ./cmd/linkshort) 2>"$WORK/build.log"; then
  fail "build" "go build 失败, 见 $WORK/build.log"
fi

# ---- 启动服务 ----
start_server() {
  LINKSHORT_ADDR="$ADDR" \
  LINKSHORT_DB="$DRILL_DB" \
  LINKSHORT_ADMIN_KEY="$ADMIN_KEY" \
  LINKSHORT_BACKUP_DIR="$DRILL_BACKUP_DIR" \
  "$BIN" >>"$LOG_FILE" 2>&1 &
  SERVER_PID=$!
}

wait_ready() {
  local step="$1"
  local elapsed=0
  local url="http://${ADDR_HOST}:${ADDR_PORT}/api/readyz"
  while [ "$elapsed" -lt "$TIMEOUT" ]; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      fail "$step" "服务进程已退出, 见 $LOG_FILE"
    fi
    if curl -fsS -o /dev/null -H "X-API-Key: ${ADMIN_KEY}" "$url" 2>/dev/null; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  fail "$step" "等待 readyz 超时(${TIMEOUT}s), 见 $LOG_FILE"
}

stop_server() {
  local step="$1"
  if [ -z "$SERVER_PID" ]; then
    return 0
  fi
  kill "$SERVER_PID" 2>/dev/null || true
  local elapsed=0
  while kill -0 "$SERVER_PID" 2>/dev/null; do
    if [ "$elapsed" -ge 10 ]; then
      kill -9 "$SERVER_PID" 2>/dev/null || true
      fail "$step" "进程未在 10s 内退出, 已 kill -9"
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  wait "$SERVER_PID" 2>/dev/null || true
  SERVER_PID=""
}

# ---- 步骤 4: 首次启动 ----
log "启动演练服务..."
start_server
wait_ready "start"

BASE="http://${ADDR_HOST}:${ADDR_PORT}"
API=(-H "X-API-Key: ${ADMIN_KEY}" -H "Content-Type: application/json")

create_link() {
  # create_link <slug> <json-body>
  local slug="$1"
  local body="$2"
  local resp
  resp="$(curl -fsS "${API[@]}" -X POST -d "$body" "$BASE/api/links")" \
    || fail "create-link-${slug}" "POST /api/links 失败"
  case "$resp" in
    *"\"slug\":\"${slug}\""*) : ;;
    *) fail "create-link-${slug}" "响应中未见 slug=${slug}: $resp" ;;
  esac
}

# ---- 步骤 5: 建三条链 ----
log "创建演练短链..."
create_link "drill-plain" "{\"url\":\"https://example.com/plain\",\"slug\":\"drill-plain\"}"
create_link "drill-burn"  "{\"url\":\"https://example.com/burn\",\"slug\":\"drill-burn\",\"burn\":true,\"purge\":true}"
create_link "drill-max"   "{\"url\":\"https://example.com/max\",\"slug\":\"drill-max\",\"max_visits\":2}"

# ---- 步骤 6: 访问制造数据 ----
log "访问短链制造数据..."
for _ in 1 2 3; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/drill-plain")"
  [ "$code" = "302" ] || fail "visit-plain" "drill-plain 期望 302, 实际 $code"
done
for _ in 1 2; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/drill-max")"
  [ "$code" = "302" ] || fail "visit-max" "drill-max 期望 302, 实际 $code"
done
code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/drill-burn")"
[ "$code" = "302" ] || fail "visit-burn" "drill-burn 首次期望 302, 实际 $code"
code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/drill-burn")"
[ "$code" = "404" ] || fail "visit-burn" "drill-burn purge 后再访期望 404, 实际 $code"

snapshot() {
  local links visits clicks
  links="$(sqlite3 "$DRILL_DB" 'SELECT COUNT(*) FROM links;')"
  visits="$(sqlite3 "$DRILL_DB" 'SELECT COUNT(*) FROM visits;')"
  clicks="$(sqlite3 "$DRILL_DB" 'SELECT COALESCE(SUM(clicks),0) FROM links;')"
  printf '%s %s %s' "$links" "$visits" "$clicks"
}

read -r SNAP_LINKS SNAP_VISITS SNAP_CLICKS <<<"$(snapshot)"
log "演练前快照: links=$SNAP_LINKS visits=$SNAP_VISITS clicks=$SNAP_CLICKS"

# ---- 步骤 7: 备份 ----
log "执行备份..."
LINKSHORT_DB="$DRILL_DB" \
LINKSHORT_BACKUP_DIR="$DRILL_BACKUP_DIR" \
  "$ROOT/scripts/backup.sh" >"$WORK/backup.log" 2>&1 \
  || fail "backup" "backup.sh 失败, 见 $WORK/backup.log"

LATEST_BACKUP="$(ls -1t "$DRILL_BACKUP_DIR"/linkshort-*.db 2>/dev/null | head -n1 || true)"
[ -n "$LATEST_BACKUP" ] || fail "backup" "未找到备份文件"
[ -f "$LATEST_BACKUP" ] || fail "backup" "备份文件不存在: $LATEST_BACKUP"

CHECK="$(sqlite3 "$LATEST_BACKUP" 'PRAGMA integrity_check;' 2>&1 || true)"
[ "$CHECK" = "ok" ] || fail "backup-integrity" "备份完整性校验失败: $CHECK"
log "备份文件: $LATEST_BACKUP"

# ---- 步骤 8: 停服 ----
log "停止服务..."
stop_server "stop"

# ---- 步骤 9: 删库 ----
log "删除数据库(模拟灾难)..."
rm -f -- "$DRILL_DB" "$DRILL_DB-wal" "$DRILL_DB-shm"
[ ! -e "$DRILL_DB" ] || fail "delete-db" "数据库未能删除: $DRILL_DB"

# ---- 步骤 10: 恢复 ----
log "执行恢复..."
LINKSHORT_DB="$DRILL_DB" \
  "$ROOT/scripts/restore.sh" "$LATEST_BACKUP" --force >"$WORK/restore.log" 2>&1 \
  || fail "restore" "restore.sh 失败, 见 $WORK/restore.log"
[ -f "$DRILL_DB" ] || fail "restore" "恢复后数据库不存在: $DRILL_DB"

# ---- 步骤 11: 重启 ----
log "重启服务..."
start_server
wait_ready "restart"

# ---- 步骤 12: 一致性校验 ----
log "一致性校验..."
read -r POST_LINKS POST_VISITS POST_CLICKS <<<"$(snapshot)"
[ "$POST_LINKS" = "$SNAP_LINKS" ] || fail "consistency-links" "links 行数不一致: 前=$SNAP_LINKS 后=$POST_LINKS"
[ "$POST_VISITS" = "$SNAP_VISITS" ] || fail "consistency-visits" "visits 行数不一致: 前=$SNAP_VISITS 后=$POST_VISITS"
[ "$POST_CLICKS" = "$SNAP_CLICKS" ] || fail "consistency-clicks" "clicks 总和一致: 前=$SNAP_CLICKS 后=$POST_CLICKS"

code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/drill-plain")"
[ "$code" = "302" ] || fail "verify-plain" "drill-plain 期望 302, 实际 $code"

# drill-max: 恢复后 max_visits=2, 已用 2, 第 3 次应 410
code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/drill-max")"
[ "$code" = "410" ] || fail "verify-max" "drill-max 第 3 次期望 410, 实际 $code"

# drill-burn: purge=true, 恢复后应已不存在 -> 404
code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/drill-burn")"
[ "$code" = "404" ] || fail "verify-burn" "drill-burn 期望 404, 实际 $code"

HEALTH="$(curl -fsS "${API[@]}" "$BASE/api/backup/health" 2>/dev/null || true)"
[ -n "$HEALTH" ] || fail "verify-health" "GET /api/backup/health 无响应"
case "$HEALTH" in
  *'"status":"ok"'*) : ;;
  *) fail "verify-health" "备份健康状态非 ok: $HEALTH" ;;
esac

# ---- 步骤 13: 停服 + 收尾 ----
log "停止服务..."
stop_server "stop-final"

log "PASS"
exit 0
