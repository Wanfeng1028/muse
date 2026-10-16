
#!/usr/bin/env bash
# 备份恢复演练脚本
# 退出码：0=全部通过；1=任一步骤失败；2=环境缺失（go/sqlite3/curl 任一不可用）
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO="$SCRIPT_DIR/.."
TMP="$REPO/.backup-drill-tmp"

# ---- 环境检查 ----
missing=0
for cmd in go sqlite3 curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[FAIL] 缺少命令：$cmd"
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  exit 2
fi

HAS_JQ=1
if ! command -v jq >/dev/null 2>&1; then
  HAS_JQ=0
fi

# ---- 全局状态 ----
SERVER_PID=""
STAGE_NAMES=()
STAGE_RESULTS=()
STAGE_TIMES=()

stage_start() {
  STAGE_CUR_NAME="$1"
  STAGE_CUR_START=$(date +%s)
}

stage_end() {
  local res="$1"
  local now
  now=$(date +%s)
  STAGE_NAMES+=("$STAGE_CUR_NAME")
  STAGE_RESULTS+=("$res")
  STAGE_TIMES+=("$((now - STAGE_CUR_START))")
  if [ "$res" = "PASS" ]; then
    echo "[PASS] $STAGE_CUR_NAME"
  else
    echo "[FAIL] $STAGE_CUR_NAME"
  fi
}

fail() {
  echo "[FAIL] $1"
  exit 1
}

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      kill -TERM "$SERVER_PID" 2>/dev/null || true
      for _ in $(seq 1 30); do
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
          break
        fi
        sleep 1
      done
      if kill -0 "$SERVER_PID" 2>/dev/null; then
        kill -9 "$SERVER_PID" 2>/dev/null || true
      fi
    fi
    SERVER_PID=""
  fi
  if [ -n "${TMP:-}" ] && [ -d "$TMP" ]; then
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

# ---- JSON 取值辅助（jq 缺失时用 python3）----
json_get_id() {
  local body="$1"
  if [ "$HAS_JQ" -eq 1 ]; then
    printf '%s' "$body" | jq -r '.id // empty'
  else
    printf '%s' "$body" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
except Exception:
    print("")
    sys.exit(0)
v=d.get("id","")
print(v if v is not None else "")'
  fi
}

json_get_titles() {
  local body="$1"
  if [ "$HAS_JQ" -eq 1 ]; then
    printf '%s' "$body" | jq -r 'if type=="array" then .[] else (.notes // .items // [])[] end | .title // empty'
  else
    printf '%s' "$body" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit(0)
arr = d if isinstance(d,list) else (d.get("notes") or d.get("items") or [])
for it in arr:
    if isinstance(it,dict):
        t=it.get("title")
        if t is not None:
            print(t)'
  fi
}

# ---- 阶段 0：准备 ----
stage_start "阶段0-准备"
if [ -d "$TMP" ]; then
  rm -rf "$TMP"
fi
mkdir -p "$TMP"
if ! ( cd "$REPO" && go build -o "$TMP/second-brain" ./cmd/server ); then
  fail "构建失败：go build ./cmd/server"
fi
if [ ! -x "$TMP/second-brain" ]; then
  fail "构建产物不存在或不可执行：$TMP/second-brain"
fi
stage_end "PASS"

DB="$TMP/drill.db"
BACKUP="$TMP/backup.db"
ADDR="127.0.0.1:18081"
BASE="http://$ADDR"
BIN="$TMP/second-brain"

start_server() {
  SB_DB="$DB" SB_ADDR="$ADDR" SB_PUSH_ENABLED=false "$BIN" >"$TMP/server.log" 2>&1 &
  SERVER_PID=$!
}

wait_ready() {
  local deadline=$(( $(date +%s) + 60 ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      return 1
    fi
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/notes" || true)
    if [ "$code" = "200" ]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

stop_server() {
  if [ -z "$SERVER_PID" ]; then
    return 0
  fi
  kill -TERM "$SERVER_PID" 2>/dev/null || true
  local deadline=$(( $(date +%s) + 30 ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      SERVER_PID=""
      return 0
    fi
    sleep 1
  done
  kill -9 "$SERVER_PID" 2>/dev/null || true
  SERVER_PID=""
  return 1
}

# ---- 阶段 1：启动 ----
stage_start "阶段1-启动服务"
start_server
if ! wait_ready; then
  echo "---- server.log ----"
  cat "$TMP/server.log" || true
  fail "服务未在 60s 内就绪"
fi
stage_end "PASS"

# ---- 阶段 2：造数据 ----
stage_start "阶段2-造数据"
EPOCH=$(date +%s)
T1="drill-note-1-$EPOCH"
T2="drill-note-2-$EPOCH"
T3="drill-note-3-$EPOCH"
for t in "$T1" "$T2" "$T3"; do
  code=$(curl -s -o "$TMP/create.json" -w '%{http_code}' \
    -X POST "$BASE/api/notes" \
    -H 'Content-Type: application/json' \
    -d "{\"title\":\"$t\"}" || true)
  if [ "$code" != "201" ]; then
    echo "创建失败：title=$t http=$code"
    cat "$TMP/create.json" || true
    fail "POST /api/notes 期望 201，实际 $code"
  fi
  id=$(json_get_id "$(cat "$TMP/create.json")")
  if [ -z "$id" ]; then
    fail "创建返回体缺少 id：$t"
  fi
done

code=$(curl -s -o "$TMP/list.json" -w '%{http_code}' "$BASE/api/notes" || true)
if [ "$code" != "200" ]; then
  fail "GET /api/notes 期望 200，实际 $code"
fi
LIST_TITLES=$(json_get_titles "$(cat "$TMP/list.json")")
for t in "$T1" "$T2" "$T3"; do
  if ! printf '%s\n' "$LIST_TITLES" | grep -Fxq "$t"; then
    echo "列表缺少标题：$t"
    fail "GET /api/notes 未包含刚创建的 3 条"
  fi
done
stage_end "PASS"

# ---- 阶段 3：在线备份 ----
stage_start "阶段3-在线备份"
if ! sqlite3 "$DB" ".backup '$BACKUP'"; then
  fail "在线备份失败"
fi
if [ ! -f "$BACKUP" ]; then
  fail "备份文件不存在：$BACKUP"
fi
if [ ! -s "$BACKUP" ]; then
  fail "备份文件为空：$BACKUP"
fi
IC=$(sqlite3 "$BACKUP" "PRAGMA integrity_check;")
IC_FIRST=$(printf '%s\n' "$IC" | head -n1)
if [ "$IC_FIRST" != "ok" ]; then
  echo "integrity_check 输出：$IC"
  fail "备份库 integrity_check 不是 ok"
fi
stage_end "PASS"

# ---- 阶段 4：删库 ----
stage_start "阶段4-删库"
stop_server || fail "服务未在 30s 内退出"
rm -f "$DB"
if [ -e "$DB" ]; then
  fail "原库文件仍存在：$DB"
fi
stage_end "PASS"

# ---- 阶段 5：恢复 ----
stage_start "阶段5-恢复"
if ! cp "$BACKUP" "$DB"; then
  fail "从备份恢复失败"
fi
if [ ! -s "$DB" ]; then
  fail "恢复后的库文件为空"
fi
start_server
if ! wait_ready; then
  echo "---- server.log ----"
  cat "$TMP/server.log" || true
  fail "恢复后服务未在 60s 内就绪"
fi
stage_end "PASS"

# ---- 阶段 6：一致性校验 ----
stage_start "阶段6-一致性校验"
code=$(curl -s -o "$TMP/list2.json" -w '%{http_code}' "$BASE/api/notes" || true)
if [ "$code" != "200" ]; then
  fail "恢复后 GET /api/notes 期望 200，实际 $code"
fi
LIST2_TITLES=$(json_get_titles "$(cat "$TMP/list2.json")")
for t in "$T1" "$T2" "$T3"; do
  if ! printf '%s\n' "$LIST2_TITLES" | grep -Fxq "$t"; then
    echo "恢复后列表缺少标题：$t"
    fail "恢复后数据不一致，缺少：$t"
  fi
done

echo "---- .tables ----"
TABLES=$(sqlite3 "$DB" ".tables")
printf '%s\n' "$TABLES"
NOTE_TABLE=""
for tb in $TABLES; do
  case "$tb" in
    *note*|*Note*|*NOTE*)
      NOTE_TABLE="$tb"
      break
      ;;
  esac
done
if [ -z "$NOTE_TABLE" ]; then
  fail "未在库中找到含 note 的表，无法校验行数"
fi
COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM \"$NOTE_TABLE\";")
if [ "$COUNT" != "3" ]; then
  fail "表 $NOTE_TABLE 行数期望 3，实际 $COUNT"
fi
stage_end "PASS"

# ---- 阶段 7：报告 ----
echo ""
echo "================ 备份恢复演练汇总 ================"
i=0
total=0
all_pass=1
while [ "$i" -lt "${#STAGE_NAMES[@]}" ]; do
  name="${STAGE_NAMES[$i]}"
  res="${STAGE_RESULTS[$i]}"
  secs="${STAGE_TIMES[$i]}"
  total=$((total + secs))
  printf '%-24s %-4s %ss\n' "$name" "$res" "$secs"
  if [ "$res" != "PASS" ]; then
    all_pass=0
  fi
  i=$((i + 1))
done
echo "总耗时：${total}s"
echo "=================================================="
if [ "$all_pass" -eq 1 ]; then
  echo "[PASS] 全部阶段通过"
  exit 0
else
  echo "[FAIL] 存在失败阶段"
  exit 1
fi
