#!/usr/bin/env bash
# drama-factory 在线备份脚本
# 用法: ./scripts/backup.sh
# 环境变量:
#   H2_JAR         H2 jar 路径 (可选, 未设置则自动搜索)
#   BACKUP_KEEP    保留最近 N 个备份包 (默认 7)
#   APP_HOME       应用根目录 (默认脚本所在目录的上一级)
set -euo pipefail

# ---------- 基础路径 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_HOME="${APP_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$APP_HOME"

DATA_DIR="$APP_HOME/data"
DB_BASE="$DATA_DIR/drama-factory"
DB_FILE="$DB_BASE.mv.db"
MEDIA_DIR="$DATA_DIR/media"
SETTINGS_FILE="$DATA_DIR/settings.json"
BACKUP_DIR="$APP_HOME/backups"
LOG_PREFIX="[backup]"

BACKUP_KEEP="${BACKUP_KEEP:-7}"

log()  { echo "$LOG_PREFIX $(date '+%F %T') $*"; }
fail() { echo "$LOG_PREFIX $(date '+%F %T') [错误] $*" >&2; exit 1; }

log "开始备份, 应用目录: $APP_HOME"

# ---------- 0. 前置检查 ----------
[ -d "$DATA_DIR" ] || fail "数据目录不存在: $DATA_DIR"
[ -f "$DB_FILE" ]  || fail "H2 数据库文件不存在: $DB_FILE (应用是否已初始化?)"
mkdir -p "$BACKUP_DIR"

# ---------- 1. 定位 H2 JAR ----------
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

# ---------- 2. 准备临时工作区 ----------
TS="$(date '+%Y%m%d-%H%M%S')"
PKG_NAME="drama-factory-$TS"
WORK_DIR="$(mktemp -d "$BACKUP_DIR/.staging-backup.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
STAGE="$WORK_DIR/$PKG_NAME"
mkdir -p "$STAGE"

DB_DUMP_ZIP="$STAGE/db.zip"

# ---------- 3. 在线备份 H2 数据库 ----------
log "[1/4] 通过 H2 BACKUP TO 在线导出数据库 ..."
H2_URL="jdbc:h2:file:$DB_BASE"
if ! java -cp "$H2_JAR" org.h2.tools.Shell \
        -url "$H2_URL" -user sa -password "" \
        -sql "BACKUP TO '$DB_DUMP_ZIP'"; then
  fail "步骤 1/4 失败: H2 在线备份命令返回非零 (检查应用是否正在写入、H2 jar 版本是否匹配)"
fi
[ -s "$DB_DUMP_ZIP" ] || fail "步骤 1/4 失败: H2 BACKUP TO 未生成有效 zip: $DB_DUMP_ZIP"
log "     数据库导出完成: $(du -h "$DB_DUMP_ZIP" | cut -f1)"

# ---------- 4. 归档 media 与 settings.json ----------
log "[2/4] 打包媒体目录与 settings.json ..."
MEDIA_TAR="$STAGE/media.tar.gz"
SETTINGS_SRC=""
if [ -d "$MEDIA_DIR" ]; then
  tar -czf "$MEDIA_TAR" -C "$DATA_DIR" media
  log "     media 归档: $(du -h "$MEDIA_TAR" | cut -f1)"
else
  log "     [警告] media 目录不存在, 跳过: $MEDIA_DIR"
fi

if [ -f "$SETTINGS_FILE" ]; then
  SETTINGS_SRC="$STAGE/settings.json"
  cp -p "$SETTINGS_FILE" "$SETTINGS_SRC"
  log "     settings.json 已复制"
else
  log "     [警告] settings.json 不存在, 跳过: $SETTINGS_FILE"
fi

# ---------- 5. 生成 manifest ----------
log "[3/4] 生成 manifest.txt ..."
APP_VERSION="unknown"
for vf in "$APP_HOME/VERSION" "$APP_HOME/build-info.txt"; do
  [ -f "$vf" ] && APP_VERSION="$(head -n1 "$vf")" && break
done
if [ "$APP_VERSION" = "unknown" ] && command -v git >/dev/null 2>&1 && [ -d "$APP_HOME/.git" ]; then
  APP_VERSION="$(git -C "$APP_HOME" rev-parse --short HEAD 2>/dev/null || echo unknown)"
fi

MANIFEST="$STAGE/manifest.txt"
{
  echo "# drama-factory backup manifest"
  echo "timestamp: $TS"
  echo "hostname: $(hostname)"
  echo "app_home: $APP_HOME"
  echo "app_version: $APP_VERSION"
  echo "h2_jar: $H2_JAR"
  echo "db_source: $DB_FILE"
  echo ""
  echo "## files"
} > "$MANIFEST"

( cd "$STAGE" && find . -type f ! -name manifest.txt | sort | while read -r f; do
    printf "%s  %s\n" "$(sha256sum "$f" | awk '{print $1}')" "${f#./}"
  done ) >> "$MANIFEST"

log "     manifest 记录 $(grep -c '^[0-9a-f]\{64\}' "$MANIFEST" || true) 个文件"

# ---------- 6. 打最终备份包 ----------
log "[4/4] 打包备份 ..."
FINAL_PKG="$BACKUP_DIR/$PKG_NAME.tar.gz"
tar -czf "$FINAL_PKG" -C "$WORK_DIR" "$PKG_NAME"
[ -s "$FINAL_PKG" ] || fail "步骤 4/4 失败: 最终备份包为空: $FINAL_PKG"
log "     备份完成: $FINAL_PKG ($(du -h "$FINAL_PKG" | cut -f1))"

# ---------- 7. 保留策略 ----------
log "应用保留策略: 仅保留最近 $BACKUP_KEEP 个备份包"
mapfile -t OLD_PKGS < <(ls -1t "$BACKUP_DIR"/drama-factory-*.tar.gz 2>/dev/null | tail -n +$((BACKUP_KEEP + 1)) || true)
if [ "${#OLD_PKGS[@]}" -eq 0 ]; then
  log "     无需清理"
else
  for old in "${OLD_PKGS[@]}"; do
    log "     删除过期备份: $old"
    rm -f -- "$old"
  done
fi

log "备份成功, 退出"
