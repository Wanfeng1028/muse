#!/usr/bin/env bash
set -euo pipefail

# auth-service 备份脚本
# 用法: ./scripts/backup-auth.sh
# 环境变量:
#   BACKUP_KEEP        保留最近备份个数 (默认 7)
#   APP_HOME           应用根目录 (默认脚本上一级)
#   H2_JAR             H2 jar 路径 (可选, 自动搜索)
#   AUTH_PORT          auth-service 端口 (默认 8082)
#   AUTH_ADMIN_EMAIL / AUTH_ADMIN_PASSWORD  在线模式的管理员凭证

BACKUP_KEEP="${BACKUP_KEEP:-7}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${APP_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
AUTH_PORT="${AUTH_PORT:-8082}"

LOG_PREFIX="[backup-auth]"
log()  { echo "$LOG_PREFIX $*"; }
fail() { echo "$LOG_PREFIX 错误: $*" >&2; exit 1; }

TS="$(date +%Y%m%d-%H%M%S)"

DATA_DIR="$APP_HOME/data"
DB_BASE="$DATA_DIR/auth"
DB_FILE="$DB_BASE.mv.db"
BACKUP_DIR="$APP_HOME/backups/auth"

mkdir -p "$BACKUP_DIR" || fail "无法创建备份目录: $BACKUP_DIR"
# 临时目录建在备份目录下，不使用 /tmp（仓库安全规范）
STAGE="$(mktemp -d "$BACKUP_DIR/.staging-backup-auth.XXXXXX")"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

# ---------- 前置检查 ----------
[ -d "$DATA_DIR" ] || fail "数据目录不存在: $DATA_DIR"

# ---------- 在线检查 ----------
# 应用运行时走 HTTP 在线备份（应用内执行 BACKUP TO，无文件锁冲突）；
# 应用未运行时走 H2 Shell 离线备份（需库文件存在）。
# H2 嵌入式文件库持有独占文件锁，独立 JVM 进程无法在应用运行时打开同一库文件，
# 故在线备份必须经由应用内端点 /api/auth/admin/backup。
ONLINE=0
if curl -fsS --max-time 2 "http://127.0.0.1:$AUTH_PORT/actuator/health" >/dev/null 2>&1; then
  ONLINE=1
  log "检测到 auth-service 运行中，使用在线备份模式"
fi
if [ "$ONLINE" -eq 0 ]; then
  [ -f "$DB_FILE" ] || fail "数据库文件不存在: $DB_FILE (应用未运行且库文件缺失)"
fi

# ---------- 定位 H2 jar（离线模式需要） ----------
find_h2_jar() {
  if [ -n "${H2_JAR:-}" ]; then
    [ -f "$H2_JAR" ] || fail "指定的 H2_JAR 不存在: $H2_JAR"
    echo "$H2_JAR"
    return 0
  fi
  local search_dirs=(
    "$HOME/.m2/repository"
    "$HOME/workspace/muse-build/.m2repo"
  )
  local d found
  for d in "${search_dirs[@]}"; do
    [ -d "$d" ] || continue
    found="$(find "$d" -type f -name 'h2-*.jar' ! -name '*sources*' ! -name '*javadoc*' 2>/dev/null | sort -V | tail -n 1 || true)"
    if [ -n "$found" ]; then
      echo "$found"
      return 0
    fi
  done
  return 1
}

# ---------- 获取 db.zip（在线经 HTTP，离线经 H2 Shell） ----------
if [ "$ONLINE" -eq 1 ]; then
  [ -n "${AUTH_ADMIN_EMAIL:-}" ] || fail "在线备份需要 AUTH_ADMIN_EMAIL / AUTH_ADMIN_PASSWORD（管理员凭证）"
  [ -n "${AUTH_ADMIN_PASSWORD:-}" ] || fail "在线备份需要 AUTH_ADMIN_EMAIL / AUTH_ADMIN_PASSWORD（管理员凭证）"
  log "登录获取管理员 token ..."
  TOKEN_JSON="$(curl -fsS --max-time 10 -X POST "http://127.0.0.1:$AUTH_PORT/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$AUTH_ADMIN_EMAIL\",\"password\":\"$AUTH_ADMIN_PASSWORD\"}")" \
    || fail "管理员登录失败（检查 AUTH_ADMIN_EMAIL/PASSWORD）"
  ACCESS_TOKEN="$(echo "$TOKEN_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')" \
    || fail "解析 accessToken 失败"
  log "调用在线备份端点 ..."
  curl -fsS --max-time 60 -X POST "http://127.0.0.1:$AUTH_PORT/api/auth/admin/backup" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -o "$STAGE/db.zip" \
    || fail "在线备份端点调用失败"
else
  H2_JAR_RESOLVED="$(find_h2_jar || true)"
  [ -n "$H2_JAR_RESOLVED" ] || fail "未找到 H2 jar, 请设置 H2_JAR 环境变量"
  log "使用 H2 jar: $H2_JAR_RESOLVED"
  log "开始离线备份数据库: $DB_BASE"
  java -cp "$H2_JAR_RESOLVED" org.h2.tools.Shell \
    -url "jdbc:h2:file:$DB_BASE" \
    -user sa \
    -password "" \
    -sql "BACKUP TO '$STAGE/db.zip'" \
    || fail "H2 离线备份失败"
fi

[ -f "$STAGE/db.zip" ] || fail "备份产物 db.zip 未生成"
log "数据库备份完成"

# ---------- 生成 manifest ----------
APP_VERSION="$(cd "$APP_HOME" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
MANIFEST="$STAGE/manifest.txt"
{
  echo "# auth-service backup manifest"
  echo "timestamp: $TS"
  echo "hostname: $(hostname 2>/dev/null || echo unknown)"
  echo "app_home: $APP_HOME"
  echo "app_version: $APP_VERSION"
  echo "mode: $([ "$ONLINE" -eq 1 ] && echo online || echo offline)"
  echo "db_source: $DB_FILE"
  echo ""
  echo "## files"
  ( cd "$STAGE" && sha256sum db.zip )
} > "$MANIFEST"
log "manifest 生成完成"

# ---------- 打包（带根目录，与 restore-auth.sh 的解包期望一致） ----------
PKG_NAME="auth-service-$TS"
PKG_ROOT="$STAGE/$PKG_NAME"
mkdir -p "$PKG_ROOT"
mv "$STAGE/db.zip" "$STAGE/manifest.txt" "$PKG_ROOT/"
PACKAGE="$BACKUP_DIR/$PKG_NAME.tar.gz"
tar -czf "$PACKAGE" -C "$STAGE" "$PKG_NAME" \
  || fail "打包失败: $PACKAGE"
[ -s "$PACKAGE" ] || fail "备份包为空: $PACKAGE"
log "备份包生成: $PACKAGE ($(du -h "$PACKAGE" | cut -f1))"

# ---------- 保留策略 ----------
if [ "$BACKUP_KEEP" -gt 0 ] 2>/dev/null; then
  mapfile -t OLD_PKGS < <(ls -1t "$BACKUP_DIR"/auth-service-*.tar.gz 2>/dev/null | tail -n +$((BACKUP_KEEP + 1)) || true)
  for p in "${OLD_PKGS[@]:-}"; do
    [ -n "$p" ] || continue
    rm -f "$p"
    log "清理旧备份: $p"
  done
fi

log "备份完成"
