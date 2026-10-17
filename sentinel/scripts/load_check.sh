
#!/usr/bin/env bash
set -euo pipefail

# v0.6 里程碑 B3：真实负载验证脚本
# 用法：bash scripts/load_check.sh
# 退出码：0 全过 / 1 任一断言失败 / 2 环境缺失

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$REPO/.load-tmp"

# 可配置项
TOKEN="load-token"
API_PORT="18201"
SINK_PORT="19100"
TARGET_BASE_PORT="19101"
N_TARGETS=8

# 环境变量（sentinel）
export SENTINEL_TICK_SEC=2
export SENTINEL_CHECK_RETRY_MAX=1
export SENTINEL_WEBHOOK_QUEUE_TICK_SEC=5
export SENTINEL_WEBHOOK_QUEUE_BASE_BACKOFF_SEC=5
export SENTINEL_WEBHOOK_QUEUE_MAX_ATTEMPTS=5

SENTINEL_HOST="127.0.0.1"
SENTINEL_PORT="$API_PORT"
export SENTINEL_HOST SENTINEL_PORT SENTINEL_API_TOKEN="$TOKEN"

SENTINEL_DB="$TMP/load.db"
SENTINEL_WEBHOOK_URL="http://127.0.0.1:$SINK_PORT/hook"
export SENTINEL_DB SENTINEL_WEBHOOK_URL

API="http://127.0.0.1:$API_PORT"
HOOKS_LOG="$TMP/hooks.log"

TARGET_PIDS=()
SINK_PID=""
SENTINEL_PID=""
START_TS=0

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }

cleanup() {
  set +e
  if [[ -n "${SENTINEL_PID:-}" ]] && kill -0 "$SENTINEL_PID" 2>/dev/null; then
    kill "$SENTINEL_PID" 2>/dev/null || true
    wait "$SENTINEL_PID" 2>/dev/null || true
  fi
  if [[ -n "${SINK_PID:-}" ]] && kill -0 "$SINK_PID" 2>/dev/null; then
    kill "$SINK_PID" 2>/dev/null || true
  fi
  local i
  for i in "${!TARGET_PIDS[@]}"; do
    local pid="${TARGET_PIDS[$i]:-}"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  rm -rf "$TMP"
}
trap cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "缺少依赖: $1" >&2; exit 2; }
}

api() {
  # api <method> <path> [body]
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sS -X "$method" "$API$path" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "$body"
  else
    curl -sS -X "$method" "$API$path" \
      -H "Authorization: Bearer $TOKEN"
  fi
}

json_get() {
  # json_get <json> <python-expr on d>
  python3 -c '
import sys, json
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except Exception:
    print("")
    sys.exit(0)
expr = sys.argv[1]
try:
    v = eval(expr, {"__builtins__": {"sum": sum, "any": any, "len": len, "str": str, "int": int}}, {"d": d})
except Exception:
    v = ""
print(v)
' "$2" <<<"$1"
}

poll_until() {
  # poll_until <描述> <超时秒> <命令...>
  local desc="$1" timeout="$2"; shift 2
  local deadline=$(( $(date +%s) + timeout ))
  while true; do
    if "$@" >/dev/null 2>&1; then
      return 0
    fi
    if (( $(date +%s) >= deadline )); then
      echo "超时：$desc" >&2
      return 1
    fi
    sleep 1
  done
}

sqlite_ro() {
  python3 - "$SENTINEL_DB" "$1" <<'PY'
import sys, sqlite3
db, query = sys.argv[1], sys.argv[2]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
try:
    cur = con.execute(query)
    for row in cur.fetchall():
        print("\t".join("" if c is None else str(c) for c in row))
finally:
    con.close()
PY
}

now() { date +%s; }

if [ -d "$HOME/workspace/toolchains/go/bin" ]; then
  PATH="$HOME/workspace/toolchains/go/bin:$PATH"
  export PATH
fi

require_cmd go
require_cmd python3
require_cmd curl

mkdir -p "$TMP"
rm -rf "$TMP"/*
mkdir -p "$REPO/docs"
: >"$HOOKS_LOG"

START_TS=$(now)

echo "== 阶段0：准备假目标与 webhook sink =="

# webhook sink
python3 - "$SINK_PORT" "$HOOKS_LOG" <<'PY' &
import sys, http.server, socketserver
port = int(sys.argv[1]); logf = sys.argv[2]

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        with open(logf, "ab") as f:
            f.write(body + b"\n")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *a):
        pass

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", port), H) as httpd:
    httpd.serve_forever()
PY
SINK_PID=$!

# 8 个假目标
for i in $(seq 1 "$N_TARGETS"); do
  port=$(( TARGET_BASE_PORT + i - 1 ))
  python3 -m http.server "$port" --bind 127.0.0.1 >/dev/null 2>&1 &
  TARGET_PIDS[$((i-1))]=$!
done

poll_until "等待 webhook sink 就绪" 30 bash -c "curl -sS -o /dev/null http://127.0.0.1:$SINK_PORT/ || true; ss -ltn 2>/dev/null | grep -q ':$SINK_PORT ' || nc -z 127.0.0.1 $SINK_PORT 2>/dev/null" || fail "webhook sink 未就绪"

for i in $(seq 1 "$N_TARGETS"); do
  port=$(( TARGET_BASE_PORT + i - 1 ))
  poll_until "等待假目标端口 $port 就绪" 30 bash -c "nc -z 127.0.0.1 $port 2>/dev/null || curl -sS -o /dev/null http://127.0.0.1:$port/ 2>/dev/null" || fail "假目标 $port 未就绪"
done
pass "8 个假目标与 sink 就绪"

echo "== 构建 sentinel =="
( cd "$REPO" && go build -o "$TMP/sentinel" . ) || fail "go build 失败"
pass "构建完成"

echo "== 阶段1：启动 sentinel =="
"$TMP/sentinel" >"$TMP/sentinel.log" 2>&1 &
SENTINEL_PID=$!

poll_until "等待 sentinel /api/healthz 就绪" 60 curl -sS -o /dev/null "$API/api/healthz" || fail "sentinel 未就绪"
pass "sentinel 就绪 (pid=$SENTINEL_PID)"

echo "== 阶段2：创建 8 个监控 =="
for i in $(seq 1 "$N_TARGETS"); do
  port=$(( TARGET_BASE_PORT + i - 1 ))
  body=$(printf '{"name":"load-mon-%d","kind":"http","target":"http://127.0.0.1:%d/","method":"GET","expected_status":200,"timeout_sec":3,"interval_sec":10,"enabled":1}' "$i" "$port")
  resp="$(api POST /api/monitors "$body")" || fail "创建监控 load-mon-$i 请求失败"
  mid="$(json_get "$resp" 'd.get("id","")')"
  [[ -n "$mid" ]] || fail "创建监控 load-mon-$i 未返回 id: $resp"
done
pass "8 个监控已创建"

overview_up() {
  local resp
  resp="$(api GET /api/overview 2>/dev/null || true)"
  [[ -n "$resp" ]] || return 1
  local up
  up="$(json_get "$resp" 'd.get("up",0)')"
  [[ "$up" == "8" ]]
}
poll_until "等待 /api/overview up==8（120s）" 120 overview_up || fail "overview up 未达到 8"
pass "overview up==8"

echo "== 阶段3：基线采集（等待 35 秒多轮检查）=="
sleep 45

TOTAL_CHECKS="$(sqlite_ro "SELECT COUNT(*) FROM checks;" | tr -d '[:space:]')"
[[ -n "$TOTAL_CHECKS" ]] || fail "读取 checks 总行数失败"
if (( TOTAL_CHECKS < 24 )); then
  fail "checks 总行数 $TOTAL_CHECKS < 24（平均每目标至少 3 轮）"
fi
pass "checks 总行数 $TOTAL_CHECKS >= 24"

read -r P50 P99 OK_RATIO <<EOF
$(python3 - "$SENTINEL_DB" <<'PY'
import sys, sqlite3, statistics
db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
try:
    rows = [r[0] for r in con.execute("SELECT latency_ms FROM checks WHERE latency_ms IS NOT NULL;").fetchall()]
    total = con.execute("SELECT COUNT(*) FROM checks;").fetchone()[0]
    ok = con.execute("SELECT COUNT(*) FROM checks WHERE ok=1;").fetchone()[0]
finally:
    con.close()

def pct(vals, p):
    if not vals:
        return 0.0
    vals = sorted(vals)
    if len(vals) == 1:
        return float(vals[0])
    # 线性插值分位
    k = (len(vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    frac = k - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac

p50 = pct(rows, 0.50)
p99 = pct(rows, 0.99)
ratio = (ok / total) if total else 0.0
print(f"{p50:.1f}\t{p99:.1f}\t{ratio:.4f}")
PY
)
EOF

[[ -n "${P50:-}" ]] || fail "计算延迟分位失败"
if [[ "$OK_RATIO" != "1.0000" ]]; then
  fail "基线 ok=1 占比 $OK_RATIO != 100%"
fi
pass "基线：p50=${P50}ms p99=${P99}ms ok=100%"

echo "== 阶段4：故障正确性（kill 19105~19108）=="
DOWN_NAMES=("load-mon-5" "load-mon-6" "load-mon-7" "load-mon-8")
for i in 5 6 7 8; do
  pid="${TARGET_PIDS[$((i-1))]:-}"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
  TARGET_PIDS[$((i-1))]=""
done

open_incidents_count() {
  local resp
  resp="$(api GET /api/incidents 2>/dev/null || true)"
  [[ -n "$resp" ]] || return 1
  local n
  n="$(json_get "$resp" 'sum(1 for it in d.get("items",[]) if it.get("ended_at") is None)')"
  [[ "$n" =~ ^[0-9]+$ ]] || return 1
  (( n >= 4 ))
}
poll_until "等待 /api/incidents open 事件 >= 4（120s）" 120 open_incidents_count || fail "open 事件未达到 4"

# webhook 走异步投递队列（worker 每 QUEUE_TICK_SEC 扫一次），轮询等送达
hooks_all_arrived() {
  [ -f "$HOOKS_LOG" ] || return 1
  local name
  for name in "${DOWN_NAMES[@]}"; do
    grep -q "$name" "$HOOKS_LOG" || return 1
  done
  return 0
}
poll_until "等待 webhook 送达 4 个监控（90s，异步队列）" 90 hooks_all_arrived || fail "webhook 90s 内未送达全部 4 个监控"
pass "webhook 送达 4/4（19105~19108）"

# 存活的 4 个监控不应有 open 事件
INC_JSON="$(api GET /api/incidents)"
for i in 1 2 3 4; do
  name="load-mon-$i"
  hit="$(json_get "$INC_JSON" "any(it.get('monitor_name')=='$name' and it.get('ended_at') is None for it in d.get('items',[]))")"
  if [[ "$hit" == "True" ]]; then
    fail "存活监控 $name 出现误报 open 事件"
  fi
done
pass "存活 4 个监控无误报"

echo "== 阶段5：队列积压行为 =="
# 停掉 sink
if [[ -n "${SINK_PID:-}" ]] && kill -0 "$SINK_PID" 2>/dev/null; then
  kill "$SINK_PID" 2>/dev/null || true
  wait "$SINK_PID" 2>/dev/null || true
fi
SINK_PID=""

# 再 kill 19103、19104 制造新 down 事件
for i in 3 4; do
  pid="${TARGET_PIDS[$((i-1))]:-}"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
  TARGET_PIDS[$((i-1))]=""
done

BACKLOG_SUM() {
  local raw
  # /api/metrics 需要 API Token 鉴权（未带 token 返回 401）
  raw="$(curl -sS -H "Authorization: Bearer $TOKEN" "$API/api/metrics" 2>/dev/null || true)"
  [[ -n "$raw" ]] || { echo "0"; return; }
  python3 -c '
import sys, re
total = 0
for line in sys.stdin:
    m = re.match(r"sentinel_webhook_queue_backlog\{status=\"[^\"]+\"\}\s+([0-9.]+)", line.strip())
    if m:
        try:
            total += float(m.group(1))
        except Exception:
            pass
print(int(total))
' <<<"$raw"
}

PEAK_BACKLOG=0
DEADLINE=$(( $(now) + 120 ))
while true; do
  cur="$(BACKLOG_SUM)"
  [[ -n "$cur" ]] || cur=0
  if (( cur > PEAK_BACKLOG )); then
    PEAK_BACKLOG="$cur"
  fi
  if (( cur > 0 )); then
    break
  fi
  if (( $(now) >= DEADLINE )); then
    fail "等待 /api/metrics 积压 sum > 0 超时（120s）"
  fi
  sleep 1
done
pass "检测到积压，峰值暂记 $PEAK_BACKLOG"

# 重启 sink
python3 - "$SINK_PORT" "$HOOKS_LOG" <<'PY' &
import sys, http.server, socketserver
port = int(sys.argv[1]); logf = sys.argv[2]

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        with open(logf, "ab") as f:
            f.write(body + b"\n")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *a):
        pass

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", port), H) as httpd:
    httpd.serve_forever()
PY
SINK_PID=$!

poll_until "等待 sink 重启就绪" 30 bash -c "nc -z 127.0.0.1 $SINK_PORT 2>/dev/null || curl -sS -o /dev/null http://127.0.0.1:$SINK_PORT/ 2>/dev/null" || fail "sink 重启失败"

DEADLINE=$(( $(now) + 180 ))
while true; do
  cur="$(BACKLOG_SUM)"
  [[ -n "$cur" ]] || cur=0
  if (( cur > PEAK_BACKLOG )); then
    PEAK_BACKLOG="$cur"
  fi
  if (( cur == 0 )); then
    break
  fi
  if (( $(now) >= DEADLINE )); then
    fail "等待积压排空超时（180s），当前积压 $cur"
  fi
  sleep 1
done
pass "积压排空成功，峰值 $PEAK_BACKLOG"

TOTAL_SECONDS=$(( $(now) - START_TS ))
REPORT_DATE="$(date +%Y%m%d)"
REPORT="$REPO/docs/load-test-$REPORT_DATE.md"

echo "== 阶段6：生成报告 =="
cat >"$REPORT" <<EOF
# Sentinel v0.6 负载验证报告

- 日期: $REPORT_DATE
- 目标数: $N_TARGETS
- 检查总轮数: $TOTAL_CHECKS
- 延迟 p50: ${P50} ms
- 延迟 p99: ${P99} ms
- 事件正确性: 4 down 事件全对、无误报
- webhook 送达: 4/4
- 积压峰值: $PEAK_BACKLOG
- 排空成功: 是
- 总耗时: ${TOTAL_SECONDS}s
EOF

cat <<EOF
===== 负载验证摘要 =====
目标数:        $N_TARGETS
检查总轮数:    $TOTAL_CHECKS
延迟 p50:      ${P50} ms
延迟 p99:      ${P99} ms
事件正确性:    4 down 事件全对、无误报
webhook 送达:  4/4
积压峰值:      $PEAK_BACKLOG
排空成功:      是
总耗时:        ${TOTAL_SECONDS}s
报告:          $REPORT
========================
EOF

pass "全部通过"
exit 0
