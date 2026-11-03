#!/usr/bin/env bash
set -euo pipefail

# auth-service 恢复脚本
# 用法: ./scripts/restore-auth.sh <备份包> [--force]
# 环境变量:
#   APP_HOME   应用根目录 (默认脚本上一级)
#   H2_JAR     H2 jar 路径 (可选, 自动搜索)
#   AUTH_PORT  auth-service 端口 (默认 8082)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${APP_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
AUTH_PORT="${AUTH_PORT:-8082}"

LOG_PREFIX="[restore-auth]"
log()  { echo "$LOG_PREFIX $*"; }
warn() { echo "$LOG_PREFIX 警告: $*" >&2; }
fail() { echo "$LOG_PREFIX 错误: $*" >&2; exit 1; }

# ---------- 参数解析 ----------
BACKUP_PKG="${1:-}"
FORCE="false"
if [ "${2:-}" = "--force" ]; then
  FORCE="true"
fi

[ -n "$BACKUP_PKG" ] || fail "用法: $0 <备份包> [--force]"
[ -f "$BACKUP_PKG" ] || fail "备份包不存在: $BACKUP_PKG"

DATA_DIR="$APP_HOME/data"
DB_BASE="$DATA_DIR/auth"
DB_FILE="$DB_BASE.mv.db"
BACKUP_DIR="$APP_HOME/backups/auth"
HEALTH_URL="http://127.0.0.1:$AUTH_PORT/actuator/health"

mkdir -p "$BACKUP_DIR" || fail "无法创建备份目录: $BACKUP_DIR"
# 临时目录建在备份目录下，不使用 /tmp（仓库安全规范）
STAGE="$(mktemp -d "$BACKUP_DIR/.staging-restore-auth.XXXXXX")"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

TS="$(date +%Y%m%d-%H%M%S)"

# ---------- 定位 H2 jar ----------
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

H2_JAR_RESOLVED="$(find_h2_jar || true)"
[ -n "$H2_JAR_RESOLVED" ] || fail "未找到 H2 jar, 请设置 H2_JAR 环境变量"
log "使用 H2 jar: $H2_JAR_RESOLVED"

# ---------- 运行状态检查 ----------
# H2 嵌入式库文件被应用独占锁定，恢复前必须停服（除非 --force 自担风险）。
is_running() {
  if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    return 0
  fi
  if pgrep -f 'auth-servic[e].*\.jar' >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

if is_running; then
  if [ "$FORCE" = "true" ]; then
    warn "检测到 auth-service 正在运行, 但已指定 --force, 继续恢复"
    warn "注意: H2 文件被独占锁定, 恢复很可能失败或损坏数据, 后果自负"
  else
    fail "auth-service 正在运行, 请先停止服务, 或使用 --force 强制恢复"
  fi
fi

# ---------- 解包并校验 manifest ----------
log "解包备份: $BACKUP_PKG"
tar --no-same-owner -xzf "$BACKUP_PKG" -C "$STAGE" || fail "解包失败: $BACKUP_PKG"
PKG_ROOT="$(find "$STAGE" -maxdepth 1 -mindepth 1 -type d | head -n1)"
[ -n "$PKG_ROOT" ] || fail "备份包结构异常: 未找到根目录"

MANIFEST="$PKG_ROOT/manifest.txt"
[ -f "$MANIFEST" ] || fail "备份包缺少 manifest.txt"
DB_ZIP="$PKG_ROOT/db.zip"
[ -f "$DB_ZIP" ] || fail "备份包缺少 db.zip"

log "校验 manifest sha256"
while read -r hash name; do
  [ -n "$hash" ] || continue
  case "$hash" in \#*) continue ;; esac
  [ -f "$PKG_ROOT/$name" ] || fail "manifest 中的文件缺失: $name"
  actual="$(sha256sum "$PKG_ROOT/$name" | awk '{print $1}')"
  if [ "$hash" != "$actual" ]; then
    fail "sha256 校验失败: $name"
  fi
done < <(sed -n '/^## files/,$p' "$MANIFEST" | tail -n +2)
log "manifest 校验通过"

# ---------- 恢复前快照 ----------
if [ -f "$DB_FILE" ]; then
  log "对当前库做恢复前快照"
  SNAP_ZIP="$STAGE/pre-restore-db.zip"
  java -cp "$H2_JAR_RESOLVED" org.h2.tools.Shell \
    -url "jdbc:h2:file:$DB_BASE" \
    -user sa \
    -password "" \
    -sql "BACKUP TO '$SNAP_ZIP'" \
    || fail "恢复前快照失败"
  SNAP_PKG="$BACKUP_DIR/pre-restore-auth-$TS.tar.gz"
  tar -czf "$SNAP_PKG" -C "$STAGE" pre-restore-db.zip \
    || fail "打包快照失败"
  log "恢复前快照: $SNAP_PKG"
else
  log "当前库不存在, 跳过恢复前快照"
fi

# ---------- 执行恢复（H2 恢复用 org.h2.tools.Restore 工具解压 db.zip，无 SQL RESTORE 命令） ----------
log "执行恢复（org.h2.tools.Restore 解压 db.zip）"
java -cp "$H2_JAR_RESOLVED" org.h2.tools.Restore \
  -file "$DB_ZIP" \
  -dir "$DATA_DIR" \
  -db "auth" \
  || fail "恢复执行失败"
log "数据库恢复完成"

# ---------- 恢复后完整性校验 ----------
log "恢复后完整性校验"
COUNT_OUT="$(java -cp "$H2_JAR_RESOLVED" org.h2.tools.Shell \
  -url "jdbc:h2:file:$DB_BASE" \
  -user sa \
  -password "" \
  -sql "SELECT COUNT(*) FROM users;" 2>&1 || true)"
if ! echo "$COUNT_OUT" | grep -Eq '[0-9]+'; then
  fail "完整性校验失败, 无法从 users 表取数"
fi
log "完整性校验通过 (users 表可查)"

log "恢复完成"
