
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO="$SCRIPT_DIR/.."
TMP="$REPO/.drill-tmp"

SENTINEL_PID=""
TARGET1_PID=""
TARGET2_PID=""
SINK_PID=""
START_ALL=$(date +%s)

PASS_LIST=()
FAIL_LIST=()
STAGE_TIMES=()

cleanup() {
  local p
  for p in "$SENTINEL_PID" "$TARGET1_PID" "$TARGET2_PID" "$SINK_PID"; do
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      kill "$p" 2>/dev/null || true
      wait "$p" 2>/dev/null || true
    fi
  done
  if [ -d "$TMP" ]; then
    rm -rf "$TMP" 2>/dev/null || true
  fi
}
trap cleanup EXIT

pass() {
  echo "[PASS] $1"
  PASS_LIST+=("$1")
}

fail() {
  echo "[FAIL] $1"
  FAIL_LIST+=("$1")
  exit 1
}

now() { date +%s; }

stage_begin() {
  STAGE_NAME="$1"
  STAGE_START=$(now)
  echo "== 阶段: $STAGE_NAME =="
}

stage_end() {
  local t=$(( $(now) - STAGE_START ))
  STAGE_TIMES+=("$STAGE_NAME: ${t}s")
  echo "-- 阶段 $STAGE_NAME 用时 ${t}s --"
}

# 轮询直到命令成功或超时。用法: poll <超时秒> <间隔秒> <描述> <命令...>
poll() {
  local timeout=$1; shift
  local interval=$1; shift
  local desc=$1; shift
  local deadline=$(( $(now) + timeout ))
  while :; do
    if "$@"; then
      return 0
    fi
    if [ "$(now)" -ge "$deadline" ]; then
      return 1
    fi
    sleep "$interval"
  done
}

json_get() {
  # 用法: json_get <json> <jq表达式>
  local json="$1"
  local expr="$2"
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$json" | jq -r "$expr"
  else
    printf '%s' "$json" | python3 -c '
import sys, json
expr = sys.argv[1]
data = json.load(sys.stdin)
def get(d, path):
    cur = d
    for part in path.split("."):
        if part == "": continue
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur.get(part)
        if cur is None:
            return None
    return cur
# 支持有限的 jq 表达式: .a.b  或  .items | length
expr = expr.strip()
if "|" in expr:
    left, right = expr.split("|", 1)
    left = left.strip()
    right = right.strip()
    if left.startswith("."):
        val = get(data, left[1:])
    else:
        val = data
    if right.startswith("length"):
        print(len(val))
    else:
        print(val)
else:
    if expr.startswith("."):
        v = get(data, expr[1:])
        if v is None:
            print("null")
        elif isinstance(v, bool):
            print("true" if v else "false")
        else:
            print(v)
    else:
        print(data)
' "$expr"
  fi
}

api() {
  # 用法: api <method> <path> [body]
  local method="$1"; shift
  local path="$1"; shift
  local body="${1:-}"
  if [ -n "$body" ]; then
    curl -sS -X "$method" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "http://127.0.0.1:$PORT$path"
  else
    curl -sS -X "$method" \
      -H "Authorization: Bearer $TOKEN" \
      "http://127.0.0.1:$PORT$path"
  fi
}

api_status() {
  local method="$1"; shift
  local path="$1"; shift
  local body="${1:-}"
  if [ -n "$body" ]; then
    curl -sS -o /dev/null -w '%{http_code}' -X "$method" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "http://127.0.0.1:$PORT$path"
  else
    curl -sS -o /dev/null -w '%{http_code}' -X "$method" \
      -H "Authorization: Bearer $TOKEN" \
      "http://127.0.0.1:$PORT$path"
  fi
}

# 阶段 0 准备
stage_begin "阶段0-准备"
mkdir -p "$TMP"

# 假目标 18901
python3 -m http.server 18901 --bind 127.0.0.1 >"$TMP/target1.log" 2>&1 &
TARGET1_PID=$!
# 假目标 18902
python3 -m http.server 18902 --bind 127.0.0.1 >"$TMP/target2.log" 2>&1 &
TARGET2_PID=$!

# 等待两个假目标就绪
poll 30 0.3 "假目标就绪" bash -c "curl -sS -o /dev/null http://127.0.0.1:18901/ && curl -sS -o /dev/null http://127.0.0.1:18902/" \
  || fail "假目标 18901/18902 未就绪"
pass "两个假目标已启动 (18901, 18902)"

# 构建 sentinel
( cd "$REPO" && go build -o "$TMP/sentinel" . ) >"$TMP/build.log" 2>&1 \
  || fail "go build 失败，日志见 $TMP/build.log"
[ -x "$TMP/sentinel" ] || fail "构建产物不存在或不可执行"
pass "sentinel 构建完成"
stage_end

# 阶段 1 启动
stage_begin "阶段1-启动sentinel"
PORT=18200
TOKEN="drill-token"
SINK_PORT=18903
HOOKS_LOG="$TMP/hooks.log"
: > "$HOOKS_LOG"

# 启动 webhook sink：把每次 POST body 追加到 hooks.log
python3 - "$SINK_PORT" "$HOOKS_LOG" >"$TMP/sink.log" 2>&1 <<'PYEOF' &
import sys, http.server, socketserver
port = int(sys.argv[1])
logpath = sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        with open(logpath, "ab") as f:
            f.write(body)
            f.write(b"\n")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *a):
        pass
with socketserver.TCPServer(("127.0.0.1", port), H) as srv:
    srv.serve_forever()
PYEOF
SINK_PID=$!

poll 30 0.3 "webhook sink 就绪" bash -c "curl -sS -o /dev/null -X POST -d x http://127.0.0.1:$SINK_PORT/hook" \
  || fail "webhook sink 未就绪"
pass "webhook sink 已启动 (18903)"

export SENTINEL_DB="$TMP/drill.db"
export SENTINEL_HOST="127.0.0.1"
export SENTINEL_PORT="$PORT"
export SENTINEL_API_TOKEN="$TOKEN"
export SENTINEL_WEBHOOK_URL="http://127.0.0.1:$SINK_PORT/hook"
export SENTINEL_TICK_SEC=2
export SENTINEL_CHECK_RETRY_MAX=2

( cd "$REPO" && "$TMP/sentinel" ) >"$TMP/sentinel.log" 2>&1 &
SENTINEL_PID=$!

poll 60 0.5 "sentinel 健康检查" bash -c "curl -sS -o /dev/null http://127.0.0.1:$PORT/api/healthz" \
  || fail "sentinel 在 60s 内未就绪"
pass "sentinel 已就绪 (端口 $PORT)"
stage_end

# 阶段 2 建监控
stage_begin "阶段2-建监控"
M1_BODY='{"name":"drill-mon-1","kind":"http","target":"http://127.0.0.1:18901/","method":"GET","expected_status":200,"timeout_sec":3,"interval_sec":10,"enabled":1}'
M2_BODY='{"name":"drill-mon-2","kind":"http","target":"http://127.0.0.1:18902/","method":"GET","expected_status":200,"timeout_sec":3,"interval_sec":10,"enabled":1}'

R1_FULL=$(curl -sS -w '\n%{http_code}' -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$M1_BODY" "http://127.0.0.1:$PORT/api/monitors")
S1=$(printf '%s' "$R1_FULL" | tail -n 1)
R1=$(printf '%s' "$R1_FULL" | sed '$d')
([ "$S1" = "200" ] || [ "$S1" = "201" ]) || fail "创建监控1返回 $S1，期望 200/201"
ID1=$(json_get "$R1" ".id")
if [ -z "$ID1" ] || [ "$ID1" = "null" ]; then
  fail "监控1 返回没有 id: $R1"
fi
pass "监控1 已创建 id=$ID1"

R2_FULL=$(curl -sS -w '\n%{http_code}' -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$M2_BODY" "http://127.0.0.1:$PORT/api/monitors")
S2=$(printf '%s' "$R2_FULL" | tail -n 1)
R2=$(printf '%s' "$R2_FULL" | sed '$d')
([ "$S2" = "200" ] || [ "$S2" = "201" ]) || fail "创建监控2返回 $S2，期望 200/201"
ID2=$(json_get "$R2" ".id")
if [ -z "$ID2" ] || [ "$ID2" = "null" ]; then
  fail "监控2 返回没有 id: $R2"
fi
pass "监控2 已创建 id=$ID2"

check_up2() {
  local ov
  ov=$(api GET /api/overview 2>/dev/null || true)
  [ -n "$ov" ] || return 1
  local up
  up=$(json_get "$ov" ".up" 2>/dev/null || echo "")
  [ "$up" = "2" ]
}
poll 90 1 "overview up==2" check_up2 \
  || fail "90s 内 /api/overview 的 up 计数没有到 2"
pass "两个监控均为 up 状态"
stage_end

# 阶段 3 全挂
stage_begin "阶段3-目标全挂"
kill "$TARGET1_PID" 2>/dev/null || true
kill "$TARGET2_PID" 2>/dev/null || true
wait "$TARGET1_PID" 2>/dev/null || true
wait "$TARGET2_PID" 2>/dev/null || true
TARGET1_PID=""
TARGET2_PID=""
pass "两个假目标已停掉"

check_two_open() {
  local inc
  inc=$(api GET /api/incidents 2>/dev/null || true)
  [ -n "$inc" ] || return 1
  local n
  n=$(printf '%s' "$inc" | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    print(0); sys.exit(0)
items = data.get("items") or []
cnt = 0
for it in items:
    if it.get("ended_at") is None:
        cnt += 1
print(cnt)
' 2>/dev/null || echo 0)
  [ "$n" -ge 2 ]
}
poll 120 1 "两条 open 事件" check_two_open \
  || fail "120s 内没有出现 2 条 ended_at 为 null 的事件"
pass "已出现 >=2 条 open 事件"

check_hook_down() {
  [ -f "$HOOKS_LOG" ] || return 1
  grep -q "drill-mon-1" "$HOOKS_LOG" || return 1
  return 0
}
poll 60 1 "webhook 收到告警" check_hook_down \
  || fail "60s 内 webhook sink 没有收到含监控名的告警"
pass "webhook sink 收到告警 (含监控名)"
stage_end

# 阶段 4 恢复闭环
stage_begin "阶段4-恢复闭环"
python3 -m http.server 18901 --bind 127.0.0.1 >"$TMP/target1b.log" 2>&1 &
TARGET1_PID=$!
python3 -m http.server 18902 --bind 127.0.0.1 >"$TMP/target2b.log" 2>&1 &
TARGET2_PID=$!

poll 30 0.3 "假目标重启就绪" bash -c "curl -sS -o /dev/null http://127.0.0.1:18901/ && curl -sS -o /dev/null http://127.0.0.1:18902/" \
  || fail "重启后的假目标未就绪"
pass "两个假目标已重启"

check_all_closed() {
  local inc
  inc=$(api GET /api/incidents 2>/dev/null || true)
  [ -n "$inc" ] || return 1
  printf '%s' "$inc" | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
except Exception:
    print("bad"); sys.exit(0)
items = data.get("items") or []
opened = 0
closed = 0
for it in items:
    if it.get("ended_at") is None:
        opened += 1
    else:
        closed += 1
# 至少要有关闭过的事件，且没有仍然 open 的
if closed >= 2 and opened == 0:
    print("ok")
else:
    print("no")
' | grep -q ok
}
poll 180 1 "所有事件 closed" check_all_closed \
  || fail "180s 内事件没有全部 closed"
pass "两条事件均已 closed"

# 恢复通知判定逻辑：hooks.log 在阶段3已至少有一条。判定为满足其一：
#   (a) 出现包含 "恢复" 字样的新行；或
#   (b) 在阶段3之后 hooks.log 新增了至少一行包含监控名的记录（即恢复事件再次投递）。
# 记录阶段3结束时的行数作为基线。
HOOK_BASELINE=$(wc -l < "$HOOKS_LOG" 2>/dev/null || echo 0)

check_recovery_hook() {
  [ -f "$HOOKS_LOG" ] || return 1
  local total
  total=$(wc -l < "$HOOKS_LOG" 2>/dev/null || echo 0)
  # (a) 任意行含 "恢复"
  if grep -q "恢复" "$HOOKS_LOG"; then
    return 0
  fi
  # (b) 基线之后的新增行里出现监控名
  if [ "$total" -gt "$HOOK_BASELINE" ]; then
    tail -n +$((HOOK_BASELINE + 1)) "$HOOKS_LOG" | grep -q "drill-mon-" && return 0
  fi
  return 1
}
poll 90 1 "恢复类 webhook 通知" check_recovery_hook \
  || fail "90s 内没有检测到恢复类通知（含'恢复'或监控名再次出现）"
pass "检测到恢复类 webhook 通知"
stage_end

# 阶段 5 报告
echo ""
echo "===== 演练报告 ====="
echo "各阶段耗时："
for s in "${STAGE_TIMES[@]}"; do
  echo "  - $s"
done
echo "总耗时: $(( $(now) - START_ALL ))s"
echo "PASS: ${#PASS_LIST[@]} 项"
for p in "${PASS_LIST[@]}"; do
  echo "  [PASS] $p"
done
echo "FAIL: ${#FAIL_LIST[@]} 项"
for f in "${FAIL_LIST[@]}"; do
  echo "  [FAIL] $f"
done
echo "===================="
exit 0
