
#!/usr/bin/env bash
# fault-drill.sh - second-brain v0.13 故障演练脚本
#
# 退出码：
#   0 = 全部通过
#   1 = 任一步骤失败
#   2 = 环境缺失（go / sqlite3 / curl 任一不可用）
#
# 用法：bash scripts/fault-drill.sh
#
# 本脚本会自己起服务、杀服务、改文件权限，全部产物放在 $REPO/.fault-drill-tmp/，
# 退出时清理干净。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO="$SCRIPT_DIR/.."
TMP="$REPO/.fault-drill-tmp"
ADDR="127.0.0.1:18082"
BASE="http://$ADDR"

# ---------- 环境检查 ----------
for tool in go sqlite3 curl python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "[FAIL] 缺少命令：$tool"
        exit 2
    fi
done

# 记录后台进程 PID，退出时清理
PIDS=()
cleanup() {
    local p
    for p in "${PIDS[@]:-}"; do
        if [ -n "${p:-}" ] && kill -0 "$p" 2>/dev/null; then
            kill -9 "$p" 2>/dev/null || true
        fi
    done
    if [ -d "$TMP" ]; then
        chmod -R u+w "$TMP" 2>/dev/null || true
        rm -rf "$TMP" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ---------- 工具函数 ----------
# 解析 JSON 里的某个字段，优先 jq，没有就用 python3
json_field() {
    # $1 = json 文本, $2 = 字段名
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$1" | jq -r ".$2 // empty"
    else
        printf '%s' "$1" | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
    v = data.get(sys.argv[1], "")
    print("" if v is None else v)
except Exception:
    print("")
' "$2"
    fi
}

# 轮询 GET /api/notes 直到返回 200，超时则返回非 0
wait_ready() {
    local timeout=$1
    local deadline=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        local code
        code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/notes" 2>/dev/null || true)
        if [ "$code" = "200" ]; then
            return 0
        fi
        sleep 0.3
    done
    return 1
}

# 启动服务并记录 PID。$1=SB_DB 路径
start_server() {
    local db="$1"
    SB_DB="$db" SB_ADDR="$ADDR" SB_PUSH_ENABLED=false \
        "$TMP/second-brain" >"$TMP/server.log" 2>&1 &
    local pid=$!
    PIDS+=("$pid")
    printf '%s' "$pid"
}

# 停服务：$1=PID。先 SIGTERM，给 10 秒；还活着则 SIGKILL。
stop_server() {
    local pid="$1"
    if [ -z "$pid" ]; then
        return 0
    fi
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        local deadline=$(( $(date +%s) + 10 ))
        while kill -0 "$pid" 2>/dev/null && [ "$(date +%s)" -lt "$deadline" ]; do
            sleep 0.2
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    fi
}


# 打印并累计结果
declare -a RESULTS=()
declare -a TIMES=()
PASS_COUNT=0
FAIL_COUNT=0

record() {
    # $1=阶段名 $2=结果(PASS/FAIL) $3=耗时秒
    RESULTS+=("$2|$1|$3")
    if [ "$2" = "PASS" ]; then
        PASS_COUNT=$((PASS_COUNT + 1))
        echo "[PASS] $1 (${3}s)"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "[FAIL] $1 (${3}s)"
    fi
}

# ============================================================
# 阶段 0：准备
# ============================================================
echo "== 阶段 0：准备 =="
mkdir -p "$TMP"
DB="$TMP/drill.db"

if ! ( cd "$REPO" && go build -o "$TMP/second-brain" ./cmd/server ) 2>"$TMP/build.log"; then
    echo "[FAIL] 构建失败，日志："
    cat "$TMP/build.log" || true
    exit 1
fi
echo "构建完成"

PID0=$(start_server "$DB")
if ! wait_ready 60; then
    echo "[FAIL] 服务 60 秒内没有就绪"
    echo "--- server.log ---"
    cat "$TMP/server.log" || true
    exit 1
fi
echo "服务就绪，PID=$PID0"

# ============================================================
# 阶段 1：kill -9 恢复
# ============================================================
echo ""
echo "== 阶段 1：kill -9 恢复 =="
T1_START=$(date +%s)
P1_OK=1

K9_TITLE="fault-drill-kill9-$(date +%s)"
POST_BODY=$(printf '{"title":"%s"}' "$K9_TITLE")
POST_CODE=$(curl -s -o "$TMP/post1.json" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' \
    -d "$POST_BODY" "$BASE/api/notes" 2>/dev/null || true)

if [ "$POST_CODE" != "201" ]; then
    echo "[FAIL] 阶段1：创建 kill9 笔记返回 $POST_CODE，期望 201"
    P1_OK=0
fi

# kill -9 服务进程
if [ "$P1_OK" = "1" ]; then
    kill -9 "$PID0" 2>/dev/null || true
    DEADLINE=$(( $(date +%s) + 10 ))
    while kill -0 "$PID0" 2>/dev/null; do
        if [ "$(date +%s)" -ge "$DEADLINE" ]; then
            echo "[FAIL] 阶段1：kill -9 后进程 10 秒没消失"
            P1_OK=0
            break
        fi
        sleep 0.2
    done
fi

# 重新启动服务
if [ "$P1_OK" = "1" ]; then
    PID1=$(start_server "$DB")
    if ! wait_ready 60; then
        echo "[FAIL] 阶段1：重启后服务没就绪"
        P1_OK=0
    fi
fi

# 断言 kill9 笔记仍在
if [ "$P1_OK" = "1" ]; then
    LIST=$(curl -s "$BASE/api/notes" 2>/dev/null || true)
    if ! printf '%s' "$LIST" | grep -q "$K9_TITLE"; then
        echo "[FAIL] 阶段1：kill -9 后 kill9 笔记丢失"
        P1_OK=0
    fi
fi

# sqlite 完整性检查
if [ "$P1_OK" = "1" ]; then
    INTEG=$(sqlite3 "$DB" "PRAGMA integrity_check;" 2>/dev/null || echo "ERROR")
    if [ "$INTEG" != "ok" ]; then
        echo "[FAIL] 阶段1：sqlite integrity_check 结果=$INTEG"
        P1_OK=0
    fi
fi

T1_END=$(date +%s)
if [ "$P1_OK" = "1" ]; then
    record "阶段1 kill -9 恢复" PASS $((T1_END - T1_START))
else
    record "阶段1 kill -9 恢复" FAIL $((T1_END - T1_START))
fi

# 阶段 1 的服务不能留到下一阶段，否则 $ADDR 端口冲突导致后续服务 bind 失败
stop_server "$PID1"


# ============================================================
# 阶段 2a：只读目录启动失败
# ============================================================
echo ""
echo "== 阶段 2a：只读目录启动失败 =="
T2A_START=$(date +%s)
P2A_OK=1

RO_DIR="$TMP/ro"
mkdir -p "$RO_DIR"
chmod 555 "$RO_DIR"

# 后台启动，期望进程自己退出且退出码非 0
SB_DB="$RO_DIR/drill.db" SB_ADDR="$ADDR" SB_PUSH_ENABLED=false \
    "$TMP/second-brain" >"$TMP/ro-server.log" 2>&1 &
RO_PID=$!
PIDS+=("$RO_PID")

RO_EXITED=0
RO_EXIT_CODE=""
DEADLINE=$(( $(date +%s) + 15 ))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    if ! kill -0 "$RO_PID" 2>/dev/null; then
        RO_EXITED=1
        break
    fi
    sleep 0.2
done

if [ "$RO_EXITED" = "1" ]; then
    # 拿退出码：wait 会阻塞？进程已退出，wait 立即返回
    if wait "$RO_PID"; then
        RO_EXIT_CODE=0
    else
        RO_EXIT_CODE=$?
    fi
    if [ "$RO_EXIT_CODE" = "0" ]; then
        echo "[FAIL] 阶段2a：只读目录下服务退出码为 0，期望非 0"
        P2A_OK=0
    fi
else
    echo "[FAIL] 阶段2a：只读目录下服务 15 秒还活着"
    kill -9 "$RO_PID" 2>/dev/null || true
    P2A_OK=0
fi

chmod 755 "$RO_DIR" 2>/dev/null || true
T2A_END=$(date +%s)
if [ "$P2A_OK" = "1" ]; then
    record "阶段2a 只读目录启动失败" PASS $((T2A_END - T2A_START))
else
    record "阶段2a 只读目录启动失败" FAIL $((T2A_END - T2A_START))
fi

# ============================================================
# 阶段 2b：DB 文件只读时服务启动 fail-fast
# （Linux 上已打开的 DB 不受 chmod 影响，运行时写失败造不出来；
#  这里测启动时 fail-fast：不带病运行、不占端口）
# ============================================================
echo ""
echo "== 阶段 2b：DB 文件只读启动失败 =="
T2B_START=$(date +%s)
P2B_OK=1

ROF_DIR="$TMP/rofile"
ROF_DB="$ROF_DIR/drill.db"
mkdir -p "$ROF_DIR"
# 先建一个正常库
PID_TMP=$(start_server "$ROF_DB")
if ! wait_ready 60; then
    echo "[FAIL] 阶段2b：建库时服务没就绪"
    P2B_OK=0
else
    curl -s -o /dev/null -X POST -H 'Content-Type: application/json' \
        -d '{"title":"rofile-seed"}' "$BASE/api/notes" 2>/dev/null || true
fi
stop_server "$PID_TMP"
sleep 1

if [ "$P2B_OK" = "1" ]; then
    chmod 444 "$ROF_DB"
    # 后台启动，期望进程自己退出（不许半死不活占端口）
    SB_DB="$ROF_DB" SB_ADDR="$ADDR" SB_PUSH_ENABLED=false \
        "$TMP/second-brain" >"$TMP/rofile-server.log" 2>&1 &
    ROF_PID=$!
    PIDS+=("$ROF_PID")

    ROF_EXITED=0
    DEADLINE=$(( $(date +%s) + 15 ))
    while [ "$(date +%s)" -lt "$DEADLINE" ]; do
        if ! kill -0 "$ROF_PID" 2>/dev/null; then
            ROF_EXITED=1
            break
        fi
        sleep 0.2
    done

    if [ "$ROF_EXITED" = "1" ]; then
        if wait "$ROF_PID"; then
            echo "[FAIL] 阶段2b：DB 文件只读时服务退出码为 0，期望非 0"
            P2B_OK=0
        fi
    else
        echo "[FAIL] 阶段2b：DB 文件只读时服务 15 秒还活着（占端口）"
        kill -9 "$ROF_PID" 2>/dev/null || true
        P2B_OK=0
    fi
    chmod 644 "$ROF_DB" 2>/dev/null || true
fi

T2B_END=$(date +%s)
if [ "$P2B_OK" = "1" ]; then
    record "阶段2b DB 文件只读启动失败" PASS $((T2B_END - T2B_START))
else
    record "阶段2b DB 文件只读启动失败" FAIL $((T2B_END - T2B_START))
fi


# ============================================================
# 阶段 3：报告
# ============================================================
echo ""
echo "== 阶段 3：汇总报告 =="
TOTAL=0
for line in "${RESULTS[@]}"; do
    IFS='|' read -r res name secs <<<"$line"
    echo "  [$res] $name  用时 ${secs}s"
    TOTAL=$((TOTAL + secs))
done
echo ""
echo "通过：$PASS_COUNT  失败：$FAIL_COUNT  总耗时：${TOTAL}s"

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "全部通过"
    exit 0
else
    exit 1
fi
