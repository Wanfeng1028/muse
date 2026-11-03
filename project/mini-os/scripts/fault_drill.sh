#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 二进制选择：release/debug 哪个新用哪个（避免陈旧构建），MINI_OS_BIN 可覆盖
REL_BIN="$SCRIPT_DIR/../target/release/mini-os"
DBG_BIN="$SCRIPT_DIR/../target/debug/mini-os"
BIN=""
for cand in "$REL_BIN" "$DBG_BIN"; do
  if [ -x "$cand" ] && { [ -z "$BIN" ] || [ "$cand" -nt "$BIN" ]; }; then
    BIN="$cand"
  fi
done
if [ -n "${MINI_OS_BIN:-}" ]; then
  BIN="$MINI_OS_BIN"
fi

if [ ! -x "$BIN" ]; then
  echo "演练失败：找不到可执行文件 $BIN" >&2
  exit 1
fi

DRILL="$SCRIPT_DIR/../target/drill"
PORT=18091
DB="$DRILL/mini-os.db"
STATIC="$SCRIPT_DIR/../static"
BASE="http://127.0.0.1:$PORT"

rm -rf "$DRILL"
mkdir -p "$DRILL"

PID=""

dump_log() {
  echo "----- server.log 最后 30 行 -----" >&2
  if [ -f "$DRILL/server.log" ]; then
    tail -n 30 "$DRILL/server.log" >&2 || true
  else
    echo "(server.log 不存在)" >&2
  fi
  echo "---------------------------------" >&2
}

fail() {
  echo "演练失败：$1" >&2
  dump_log
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
  fi
  exit 1
}

start_server() {
  local logfile="$1"
  PORT="$PORT" DATABASE_PATH="$DB" STATIC_DIR="$STATIC" SHUTDOWN_TIMEOUT_SECS="${SHUTDOWN_TIMEOUT_SECS:-5}" \
    "$BIN" serve >"$logfile" 2>&1 &
  PID=$!
}

wait_ready() {
  local deadline=$((SECONDS + 15))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -sf --max-time 5 "$BASE/api/readyz" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

wait_gone() {
  local deadline=$((SECONDS + 10))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if ! kill -0 "$PID" 2>/dev/null; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

# 1. 起服务
start_server "$DRILL/server.log"
if ! wait_ready; then
  fail "服务未在 15 秒内就绪（readyz 未返回 200）"
fi

# 2. 写 3 个文件
for i in 1 2 3; do
  code=$(curl -s --max-time 5 -o "$DRILL/post-$i.json" -w '%{http_code}' \
    -X POST "$BASE/api/fs" \
    -H 'Content-Type: application/json' \
    -d "{\"parentId\":null,\"name\":\"drill-$i\",\"kind\":\"file\",\"content\":\"$i\"}")
  if [ "$code" != "201" ]; then
    fail "创建第 $i 个文件失败：HTTP $code"
  fi
done

present=$(curl -s --max-time 5 "$BASE/api/fs" | python3 -c 'import json,sys; names={n["name"] for n in json.load(sys.stdin)}; print("ok" if {"drill-1","drill-2","drill-3"} <= names else "missing")')
if [ "$present" != "ok" ]; then
  fail "GET /api/fs 未找到 drill-1/2/3（种子节点 Desktop/Documents 会使总数>3，只断言三者存在）"
fi

# 3. kill -9 后数据不丢
kill -9 "$PID"
if ! wait_gone; then
  fail "kill -9 后进程仍在运行"
fi

start_server "$DRILL/server.log"
if ! wait_ready; then
  fail "kill -9 后重起服务未就绪"
fi
present=$(curl -s --max-time 5 "$BASE/api/fs" | python3 -c 'import json,sys; names={n["name"] for n in json.load(sys.stdin)}; print("ok" if {"drill-1","drill-2","drill-3"} <= names else "missing")')
if [ "$present" != "ok" ]; then
  fail "kill -9 后数据丢失：drill-1/2/3 未全部找回"
fi
kill -TERM "$PID"
wait "$PID" 2>/dev/null || true
PID=""

# 4. 备份 / 恢复演练
if ! "$BIN" backup --db "$DB" --out "$DRILL/bak.db"; then
  fail "backup 命令失败"
fi
if [ ! -f "$DRILL/bak.db" ]; then
  fail "backup 未生成 $DRILL/bak.db"
fi
rm -f "$DB"
if ! "$BIN" restore --db "$DB" --backup "$DRILL/bak.db" --force; then
  fail "restore --force 失败"
fi

start_server "$DRILL/server.log"
if ! wait_ready; then
  fail "恢复后重起服务未就绪"
fi
present=$(curl -s --max-time 5 "$BASE/api/fs" | python3 -c 'import json,sys; names={n["name"] for n in json.load(sys.stdin)}; print("ok" if {"drill-1","drill-2","drill-3"} <= names else "missing")')
if [ "$present" != "ok" ]; then
  fail "恢复后数据不一致：drill-1/2/3 未全部找回"
fi
kill -TERM "$PID"
wait "$PID" 2>/dev/null || true
PID=""

# 损坏文件校验：restore 应因完整性校验失败 exit 3
head -c 512 /dev/urandom > "$DRILL/corrupt.db" 2>/dev/null || \
  python3 -c 'import os,sys; open(sys.argv[1],"wb").write(os.urandom(512))' "$DRILL/corrupt.db"
set +e
"$BIN" restore --db "$DRILL/other.db" --backup "$DRILL/corrupt.db" >"$DRILL/corrupt.out" 2>&1
CORRUPT_RC=$?
set -e
if [ "$CORRUPT_RC" != "3" ]; then
  echo "----- corrupt restore 输出 -----" >&2
  cat "$DRILL/corrupt.out" >&2 || true
  fail "损坏备份未按预期 exit 3，实际 exit $CORRUPT_RC"
fi

# 5. 优雅关闭
start_server "$DRILL/server.log"
if ! wait_ready; then
  fail "优雅关闭前服务未就绪"
fi
kill -TERM "$PID"
set +e
wait "$PID"
TERM_RC=$?
set -e
PID=""
if [ "$TERM_RC" != "0" ]; then
  fail "优雅关闭 exit code 期望 0，实际 $TERM_RC"
fi
if ! grep -Fq 'service_stopped' "$DRILL/server.log"; then
  fail "server.log 未找到 service_stopped 事件"
fi

# 5b. 超时不掐正常服务（回归：SHUTDOWN_TIMEOUT_SECS 只约束排空阶段）
SHUTDOWN_TIMEOUT_SECS=3 start_server "$DRILL/server2.log"
if ! wait_ready; then
  fail "回归检查前服务未就绪"
fi
sleep 5
if ! kill -0 "$PID" 2>/dev/null; then
  fail "服务在超时时间（3s）后自行退出：SHUTDOWN_TIMEOUT_SECS 误杀了正常服务"
fi
if ! curl -sf --max-time 5 "$BASE/api/readyz" >/dev/null; then
  fail "超时后 readyz 不再返回 200"
fi
echo "回归通过：健康服务未被 SHUTDOWN_TIMEOUT_SECS 掐断"
kill -TERM "$PID"
wait "$PID" 2>/dev/null || true
PID=""

# 6. 收尾
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null || true
fi

echo "FAULT DRILL PASS"
