#!/usr/bin/env bash
# drama-factory 恢复脚本
# 用法: ./scripts/restore.sh <备份包路径> [--force]
#   --force  跳过"应用正在运行"检查 (危险, 后果自负)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${APP_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$APP_HOME"

DATA_DIR="$APP_HOME/data"
DB_BASE="$DATA_DIR/drama-factory"
DB_FILE="$DB_BASE.mv.db"
MEDIA_DIR="$DATA_DIR/media"
SETTINGS_FILE="$DATA_DIR/settings.json"
BACKUP_DIR="$APP_HOME/backups"
PORT="${PORT:-8081}"

LOG_PREFIX="[restore]"
log()  { echo "$LOG_PREFIX $(date '+%F %T') $*"; }
fail() { echo "$LOG_PREFIX $(date '+%F %T') [错误] $*" >&2; exit 1; }

FORCE=0
PKG=""
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    -*) fail "未知参数: $a" ;;
    *) [ -z "$PKG" ] && PKG="$a" || fail "只接受一个备份包路径" ;;
  esac
done
[ -n "$PKG" ] || fail "用法: $0 <备份包路径> [--force]"
[ -f "$PKG" ] || fail "备份包不存在: $PKG"

# ---------- 1. 应用运行检查 ----------
log "检查应用是否在运行 ..."
APP_RUNNING=0
if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  APP_RUNNING=1
elif pgrep -f 'drama-factory.*\.jar' >/dev/null 2>&1; then
  APP_RUNNING=1
fi

if [ "$APP_RUNNING" -eq 1 ]; then
  if [ "$FORCE" -eq 1 ]; then
    log "[警告] 应用仍在运行, 因 --force 强制继续 (可能导致数据损坏)"
  else
    fail "应用正在运行 (端口 $PORT 或 java 进程存活)。请先停服再恢复, 或加 --force (后果自负)"
  fi
fi

# ---------- 2. 定位 H2 JAR ----------
find_h2_jar() {
  if [ -n "${H2_JAR:-}" ]; then
    [ -f "$H2_JAR" ] || fail "H2_JAR 指定的文件不存在: $H2_JAR"
    echo "$H2_JAR"; return 0
  fi
  local cand
  for d in "$HOME/.m2/repository" "${M2_REPO:-$HOME/workspace/muse-build/.m2repo}"; do
    [ -d "$d" ] || continue
    cand="$(find "$d" -type f -name 'h2-*.jar' ! -name '*sources*' ! -name '*javadoc*' 2>/dev/null | sort -V | tail -n1)"
    if [ -n "$cand" ]; then echo "$cand"; return 0; fi
  done
  return 1
}
H2_JAR_RESOLVED="$(find_h2_jar || true)"
[ -n "$H2_JAR_RESOLVED" ] || fail "找不到 H2 jar, 请设置 H2_JAR 环境变量指向 h2-*.jar"
export H2_JAR="$H2_JAR_RESOLVED"
log "使用 H2 jar: $H2_JAR"

# ---------- 3. 解包备份 ----------
TS="$(date '+%Y%m%d-%H%M%S')"
mkdir -p "$BACKUP_DIR"
WORK_DIR="$(mktemp -d "$BACKUP_DIR/.staging-restore.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
log "解包备份到临时目录: $WORK_DIR"
tar --no-same-owner -xzf "$PKG" -C "$WORK_DIR"
PKG_ROOT="$(find "$WORK_DIR" -maxdepth 1 -mindepth 1 -type d | head -n1)"
[ -n "$PKG_ROOT" ] || fail "备份包结构异常: 未找到根目录"

DB_DUMP_ZIP="$PKG_ROOT/db.zip"
MEDIA_TAR="$PKG_ROOT/media.tar.gz"
SETTINGS_SRC="$PKG_ROOT/settings.json"
MANIFEST="$PKG_ROOT/manifest.txt"

[ -f "$DB_DUMP_ZIP" ] || fail "备份包中缺少 db.zip"
[ -f "$MANIFEST" ]    || fail "备份包中缺少 manifest.txt"
log "备份包清单:"
sed 's/^/    /' "$MANIFEST"

# 校验 sha256
log "校验备份包内文件 sha256 ..."
( cd "$PKG_ROOT" && grep '^[0-9a-f]\{64\}' manifest.txt | while read -r sum rel; do
    actual="$(sha256sum "$rel" | awk '{print $1}')"
    if [ "$actual" != "$sum" ]; then
      echo "sha256 不匹配: $rel" >&2; exit 1
    fi
  done ) || fail "备份包完整性校验失败"
log "     校验通过"

# ---------- 4. 恢复前快照 ----------
log "[0/4] 生成恢复前快照 ..."
mkdir -p "$BACKUP_DIR"
SNAP_TS="$(date '+%Y%m%d-%H%M%S')"
SNAP_DIR="$WORK_DIR/pre-restore-$SNAP_TS"
mkdir -p "$SNAP_DIR"

if [ -f "$DB_FILE" ]; then
  PRE_DB_ZIP="$SNAP_DIR/db.zip"
  H2_URL="jdbc:h2:file:$DB_BASE"
  log "     在线导出当前数据库 ..."
  java -cp "$H2_JAR" org.h2.tools.Shell \
        -url "$H2_URL" -user sa -password "" \
        -sql "BACKUP TO '$PRE_DB_ZIP'" \
    || fail "恢复前快照失败: 无法导出当前数据库 (应用是否仍在运行?)"
  [ -s "$PRE_DB_ZIP" ] || fail "恢复前快照失败: 导出的 db.zip 为空"
else
  log "     [警告] 当前无 H2 数据库文件, 快照跳过数据库"
fi

if [ -d "$MEDIA_DIR" ]; then
  tar -czf "$SNAP_DIR/media.tar.gz" -C "$DATA_DIR" media
  log "     已归档当前 media"
fi
if [ -f "$SETTINGS_FILE" ]; then
  cp -p "$SETTINGS_FILE" "$SNAP_DIR/settings.json"
  log "     已复制当前 settings.json"
fi

SNAP_PKG="$BACKUP_DIR/pre-restore-$SNAP_TS.tar.gz"
tar -czf "$SNAP_PKG" -C "$WORK_DIR" "pre-restore-$SNAP_TS"
log "     恢复前快照: $SNAP_PKG"

# ---------- 5. 恢复数据库 ----------
log "[1/4] 恢复 H2 数据库 ..."
mkdir -p "$DATA_DIR"
# 先把现有 mv.db 挪走 (不删, 保留为 .pre-restore-<ts>.bak), 避免 H2 Restore 与旧文件冲突
if [ -f "$DB_FILE" ]; then
  mv "$DB_FILE" "$DB_FILE.pre-restore-$SNAP_TS.bak"
  log "     旧数据库文件已改名为: $DB_FILE.pre-restore-$SNAP_TS.bak"
fi
if [ -f "${DB_FILE}.trace.db" ]; then
  mv "${DB_FILE}.trace.db" "${DB_FILE}.trace.db.pre-restore-$SNAP_TS.bak" || true
fi

if ! java -cp "$H2_JAR" org.h2.tools.Restore \
        -file "$DB_DUMP_ZIP" \
        -dir "$DATA_DIR" \
        -db drama-factory; then
  fail "步骤 1/4 失败: H2 Restore 返回非零。旧文件保留在 $DB_FILE.pre-restore-$SNAP_TS.bak, 可手动回滚"
fi
[ -s "$DB_FILE" ] || fail "步骤 1/4 失败: 恢复后数据库文件不存在或为空: $DB_FILE"
log "     数据库恢复完成: $(du -h "$DB_FILE" | cut -f1)"

# ---------- 6. 恢复 media ----------
log "[2/4] 恢复 media 目录 ..."
if [ -f "$MEDIA_TAR" ]; then
  if [ -d "$MEDIA_DIR" ]; then
    BAK_MEDIA="$MEDIA_DIR.bak.$SNAP_TS"
    mv "$MEDIA_DIR" "$BAK_MEDIA"
    log "     现有 media 已改名为: $BAK_MEDIA"
  fi
  tar --no-same-owner -xzf "$MEDIA_TAR" -C "$DATA_DIR"
  [ -d "$MEDIA_DIR" ] || fail "步骤 2/4 失败: 解包后 media 目录不存在"
  log "     media 恢复完成"
else
  log "     [警告] 备份包中无 media.tar.gz, 跳过"
fi

# ---------- 7. 恢复 settings.json ----------
log "[3/4] 恢复 settings.json ..."
if [ -f "$SETTINGS_SRC" ]; then
  if [ -f "$SETTINGS_FILE" ]; then
    cp -p "$SETTINGS_FILE" "$SETTINGS_FILE.bak.$SNAP_TS"
    log "     现有 settings.json 已备份为: $SETTINGS_FILE.bak.$SNAP_TS"
  fi
  cp -p "$SETTINGS_SRC" "$SETTINGS_FILE"
  log "     settings.json 恢复完成"
else
  log "     [警告] 备份包中无 settings.json, 跳过"
fi

# ---------- 8. 冒烟检查 ----------
log "[4/4] 一致性冒烟检查 ..."
[ -f "$DB_FILE" ] || fail "冒烟失败: H2 文件不存在"
[ -s "$DB_FILE" ] || fail "冒烟失败: H2 文件为空"
[ -d "$MEDIA_DIR" ] || fail "冒烟失败: media 目录不存在"
log "     H2 文件: $DB_FILE ($(stat -c%s "$DB_FILE") 字节)"
log "     media 目录: $MEDIA_DIR"

cat <<EOF

============================================================
恢复完成。请按以下步骤手动验证:

  1. 启动应用:
       java -jar <你的 drama-factory.jar>
     或
       docker compose up -d

  2. 等待启动完成 (查看日志, 确认 Flyway 迁移无误):
       tail -f logs/*.log

  3. 健康检查:
       curl -fsS http://127.0.0.1:${PORT}/api/health

  4. 抽查媒体文件与最近任务记录是否与备份时一致。

回滚方法 (如果恢复后应用起不来):
  - 数据库: mv "$DB_FILE.pre-restore-$SNAP_TS.bak" "$DB_FILE"
  - media:  mv "$MEDIA_DIR.bak.$SNAP_TS" "$MEDIA_DIR"
  - 配置:   mv "$SETTINGS_FILE.bak.$SNAP_TS" "$SETTINGS_FILE"
  或直接使用本次恢复前快照: $SNAP_PKG

============================================================
EOF

log "恢复流程结束"
