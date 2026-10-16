#!/usr/bin/env bash
# MortiseDB「榫卯」v1.2 端到端编排脚本
# 依赖：bash + curl + grep + awk（不使用 jq/python）
set -euo pipefail

# ---------- 基础路径 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN="${BIN:-$SCRIPT_DIR/../bin/mortisedb}"
WORK="${1:-./e2e-work}"
WORK="$(cd "$(dirname "$WORK")" && pwd)/$(basename "$WORK")"

# ---------- 二进制定位 ----------
if [ ! -x "$BIN" ]; then
  if ! command -v go >/dev/null 2>&1; then
    echo "FAIL: 未找到可执行文件 $BIN，且 go 不在 PATH 中，无法构建" >&2
    exit 1
  fi
  echo "==> 构建 mortisedb 二进制到 $BIN"
  ( cd "$REPO_ROOT" && go build -o "$BIN" ./cmd/mortisedb )
fi
if [ ! -x "$BIN" ]; then
  echo "FAIL: 二进制 $BIN 不可执行" >&2
  exit 1
fi

# ---------- 断言 helper ----------
# assert_contains <needle> <haystack>
assert_contains() {
  local needle="$1" haystack="$2"
  if ! printf '%s' "$haystack" | grep -qF -- "$needle"; then
    echo "FAIL: 期望输出包含 '$needle'，实际为：" >&2
    printf '%s\n' "$haystack" >&2
    exit 1
  fi
}
# assert_not_contains <needle> <haystack>
assert_not_contains() {
  local needle="$1" haystack="$2"
  if printf '%s' "$haystack" | grep -qF -- "$needle"; then
    echo "FAIL: 期望输出不包含 '$needle'，实际为：" >&2
    printf '%s\n' "$haystack" >&2
    exit 1
  fi
}
# assert_eq <expected> <actual> <label>
assert_eq() {
  local expected="$1" actual="$2" label="$3"
  if [ "$expected" != "$actual" ]; then
    echo "FAIL: $label 期望 '$expected'，实际 '$actual'" >&2
    exit 1
  fi
}

# ---------- 清理 & 工作目录 ----------
rm -rf "$WORK"
mkdir -p "$WORK/sources"
cd "$WORK"

SERVE_PID=""
cleanup() {
  if [ -n "$SERVE_PID" ] && kill -0 "$SERVE_PID" 2>/dev/null; then
    kill "$SERVE_PID" 2>/dev/null || true
    wait "$SERVE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# ---------- 步骤 1：数据源 ----------
echo "==> [1/10] 生成数据源 (orders.csv / users.json)"


cat > sources/orders.csv <<'CSV'
order_id,user_id,customer,item,amount,updated_at
9001,u01,陈建国,西湖龙井 250g,128.00,2026-10-11 09:15:22
9002,u02,林晓梅,紫砂壶·西施,268.00,2026-10-11 10:02:47
9003,u03,赵铁柱,安吉白茶 100g,89.50,2026-10-12 14:23:10
9004,u01,陈建国,茶盘·竹,156.00,2026-10-12 16:48:05
9005,u04,吴淑芬,普洱生茶 357g,320.00,2026-10-13 08:31:59
9006,u05,郑志远,玻璃杯·双层,58.00,2026-10-13 11:07:33
9007,u06,黄丽华,铁观音 250g,118.00,2026-10-14 13:55:18
9008,u02,林晓梅,茶巾,25.00,2026-10-14 15:12:41
9009,u03,赵铁柱,大红袍 100g,168.00,2026-10-15 09:44:07
9010,u04,吴淑芬,功夫茶具套装,499.00,2026-10-15 18:20:55
CSV

cat > sources/users.json <<'JSON'
[
  {"user_id":"u01","name":"陈建国","phone":"13857120001","city":"杭州","level":"金卡"},
  {"user_id":"u02","name":"林晓梅","phone":"13857120002","city":"湖州","level":"银卡"},
  {"user_id":"u03","name":"赵铁柱","phone":"13857120003","city":"嘉兴","level":"普卡"},
  {"user_id":"u04","name":"吴淑芬","phone":"13857120004","city":"绍兴","level":"金卡"},
  {"user_id":"u05","name":"郑志远","phone":"13857120005","city":"杭州","level":"银卡"},
  {"user_id":"u06","name":"黄丽华","phone":"13857120006","city":"湖州","level":"普卡"},
  {"user_id":"u07","name":"周文斌","phone":"13857120007","city":"嘉兴","level":"银卡"},
  {"user_id":"u08","name":"孙雅琴","phone":"13857120008","city":"绍兴","level":"金卡"}
]
JSON

# ---------- 步骤 2：初始 YAML ----------
echo "==> [2/10] 写入 mortise.yaml（初始版）"

cat > mortise.yaml <<'YAML'
database: ./data/mortise.db
addr: "127.0.0.1:18421"
sync: {conflict: priority, priority: [shop, members], soft_delete: true}
sources:
  - {name: shop, type: csv, path: ./sources/orders.csv, table: orders, primary_key: order_id, incremental: "column:updated_at"}
  - {name: members, type: json, path: ./sources/users.json, table: users, primary_key: user_id, incremental: hash}
views:
  - name: v_order_detail
    description: 订单关联会员
    sql: SELECT o.order_id, o.customer, o.item, o.amount, u.city AS city, u.level AS level FROM "orders" o LEFT JOIN "users" u ON o.user_id = u.user_id WHERE o._m_deleted = 0
  - name: v_city_revenue
    description: 按城市汇总销售额
    sql: SELECT u.city AS city, COUNT(*) AS orders, SUM(o.amount) AS revenue FROM "orders" o LEFT JOIN "users" u ON o.user_id = u.user_id WHERE o._m_deleted = 0 GROUP BY u.city
YAML

# ---------- 步骤 3：sync ----------
echo "==> [3/10] sync 并断言视图自动注册"

SYNC_OUT="$("$BIN" sync --config mortise.yaml 2>&1)"
echo "$SYNC_OUT"
assert_contains "视图自动注册: 新增 2，更新 0，清理 0" "$SYNC_OUT"

# ---------- 步骤 4：views list ----------
echo "==> [4/10] views list 断言视图名"

LIST_OUT="$("$BIN" views list --config mortise.yaml 2>&1)"
echo "$LIST_OUT"
assert_contains "v_order_detail" "$LIST_OUT"
assert_contains "v_city_revenue" "$LIST_OUT"

# ---------- 步骤 5：query 内联子查询计数 ----------
echo "==> [5/10] query 内联视图 SQL 计数"

V_ORDER_SQL='SELECT o.order_id, o.customer, o.item, o.amount, u.city AS city, u.level AS level FROM "orders" o LEFT JOIN "users" u ON o.user_id = u.user_id WHERE o._m_deleted = 0'
Q_OUT="$("$BIN" query --config mortise.yaml "SELECT * FROM ($V_ORDER_SQL)" 2>&1)"
echo "$Q_OUT"
assert_contains "(10 行)" "$Q_OUT"

# ---------- 步骤 6：变更演练（新增 v_top_items，改 v_city_revenue） ----------
echo "==> [6/10] YAML 变更：新增 v_top_items / 修改 v_city_revenue 描述"

cat > mortise.yaml <<'YAML'
database: ./data/mortise.db
addr: "127.0.0.1:18421"
sync: {conflict: priority, priority: [shop, members], soft_delete: true}
sources:
  - {name: shop, type: csv, path: ./sources/orders.csv, table: orders, primary_key: order_id, incremental: "column:updated_at"}
  - {name: members, type: json, path: ./sources/users.json, table: users, primary_key: user_id, incremental: hash}
views:
  - name: v_order_detail
    description: 订单关联会员
    sql: SELECT o.order_id, o.customer, o.item, o.amount, u.city AS city, u.level AS level FROM "orders" o LEFT JOIN "users" u ON o.user_id = u.user_id WHERE o._m_deleted = 0
  - name: v_city_revenue
    description: 按城市汇总销售额（v2）
    sql: SELECT u.city AS city, COUNT(*) AS orders, SUM(o.amount) AS revenue FROM "orders" o LEFT JOIN "users" u ON o.user_id = u.user_id WHERE o._m_deleted = 0 GROUP BY u.city
  - name: v_top_items
    description: 按商品汇总销售额
    sql: SELECT item, COUNT(*) AS n, SUM(amount) AS revenue FROM "orders" WHERE _m_deleted = 0 GROUP BY item ORDER BY revenue DESC
YAML

SYNC2_OUT="$("$BIN" views sync --config mortise.yaml 2>&1)"
echo "$SYNC2_OUT"
assert_contains "视图自动注册: 新增 1，更新 1，清理 0" "$SYNC2_OUT"

# ---------- 步骤 7：删除 v_top_items ----------
echo "==> [7/10] YAML 变更：删除 v_top_items"

cat > mortise.yaml <<'YAML'
database: ./data/mortise.db
addr: "127.0.0.1:18421"
sync: {conflict: priority, priority: [shop, members], soft_delete: true}
sources:
  - {name: shop, type: csv, path: ./sources/orders.csv, table: orders, primary_key: order_id, incremental: "column:updated_at"}
  - {name: members, type: json, path: ./sources/users.json, table: users, primary_key: user_id, incremental: hash}
views:
  - name: v_order_detail
    description: 订单关联会员
    sql: SELECT o.order_id, o.customer, o.item, o.amount, u.city AS city, u.level AS level FROM "orders" o LEFT JOIN "users" u ON o.user_id = u.user_id WHERE o._m_deleted = 0
  - name: v_city_revenue
    description: 按城市汇总销售额（v2）
    sql: SELECT u.city AS city, COUNT(*) AS orders, SUM(o.amount) AS revenue FROM "orders" o LEFT JOIN "users" u ON o.user_id = u.user_id WHERE o._m_deleted = 0 GROUP BY u.city
YAML

SYNC3_OUT="$("$BIN" views sync --config mortise.yaml 2>&1)"
echo "$SYNC3_OUT"
assert_contains "视图自动注册: 新增 0，更新 0，清理 1" "$SYNC3_OUT"

LIST3_OUT="$("$BIN" views list --config mortise.yaml 2>&1)"
echo "$LIST3_OUT"
assert_not_contains "v_top_items" "$LIST3_OUT"

# ---------- 步骤 8：serve + CSV 导出 ----------
echo "==> [8/10] 启动 serve 并导出 CSV"

MORTISE_ADDR="127.0.0.1:18421" "$BIN" serve --config mortise.yaml > serve.log 2>&1 &
SERVE_PID=$!

HEALTH_OK=0
for i in $(seq 1 30); do
  H="$(curl -s http://127.0.0.1:18421/api/health || true)"
  if printf '%s' "$H" | grep -q '"status":"ok"'; then
    HEALTH_OK=1
    break
  fi
  sleep 1
done
if [ "$HEALTH_OK" != "1" ]; then
  echo "FAIL: /api/health 30 秒内未就绪，serve.log 尾部：" >&2
  tail -n 40 serve.log >&2 || true
  exit 1
fi

VIEWS_JSON="$(curl -s http://127.0.0.1:18421/api/views)"
assert_contains "v_order_detail" "$VIEWS_JSON"
REFRESH_JSON="$(curl -s -X POST http://127.0.0.1:18421/api/views/v_city_revenue/refresh)"
assert_contains '"rows"' "$REFRESH_JSON"


curl -s "http://127.0.0.1:18421/api/views/v_order_detail/rows?format=csv" -o export.csv

HEADER="$(head -n 1 export.csv)"
assert_contains "order_id" "$HEADER"

DATA_ROWS="$(tail -n +2 export.csv | grep -c . || true)"
assert_eq "10" "$DATA_ROWS" "CSV 数据行数"

EXPORT_BODY="$(cat export.csv)"
assert_contains "龙井" "$EXPORT_BODY"

cleanup
SERVE_PID=""

# ---------- 步骤 9：物化视图演练 ----------
echo "==> [9/10] 物化视图：on_sync 自动刷新 + manual 手动刷新"
cat > mortise.yaml <<'YAML'
database: ./data/mortise.db
addr: "127.0.0.1:18421"
sync: {conflict: priority, priority: [shop, members], soft_delete: true}
sources:
  - {name: shop, type: csv, path: ./sources/orders.csv, table: orders, primary_key: order_id, incremental: "column:updated_at"}
  - {name: members, type: json, path: ./sources/users.json, table: users, primary_key: user_id, incremental: hash}
views:
  - name: v_order_detail
    description: 订单关联会员
    sql: SELECT o.order_id, o.customer, o.item, o.amount, u.city AS city, u.level AS level FROM "orders" o LEFT JOIN "users" u ON o.user_id = u.user_id WHERE o._m_deleted = 0
    materialize:
      enabled: true
      refresh: on_sync
  - name: v_city_revenue
    description: 按城市汇总销售额
    sql: SELECT u.city AS city, COUNT(*) AS orders, SUM(o.amount) AS revenue FROM "orders" o LEFT JOIN "users" u ON o.user_id = u.user_id WHERE o._m_deleted = 0 GROUP BY u.city
    materialize:
      enabled: true
      refresh: manual
YAML

SYNC3_OUT="$("$BIN" sync --config mortise.yaml 2>&1)"
echo "$SYNC3_OUT"
assert_contains "物化视图刷新: 刷新 1，跳过 1" "$SYNC3_OUT"

MV_COUNT_OUT="$("$BIN" query --config mortise.yaml 'SELECT COUNT(*) AS c FROM "_mv_v_order_detail"' 2>&1)"
echo "$MV_COUNT_OUT"
assert_contains "(1 行)" "$MV_COUNT_OUT"
assert_contains "10" "$MV_COUNT_OUT"

echo "==> [9/10] 手动刷新 manual 策略视图"
REF_OUT="$("$BIN" views refresh --config mortise.yaml v_city_revenue 2>&1)"
echo "$REF_OUT"
assert_contains "已刷新视图 v_city_revenue，写入" "$REF_OUT"

MV2_OUT="$("$BIN" query --config mortise.yaml 'SELECT COUNT(*) AS c FROM "_mv_v_city_revenue"' 2>&1)"
echo "$MV2_OUT"
assert_contains "(1 行)" "$MV2_OUT"

# ---------- 步骤 10：摘要 ----------
echo "==> [10/10] 汇总"
echo "    orders.csv 行数     : $(tail -n +2 sources/orders.csv | grep -c .)"
echo "    users.json 对象数   : $(grep -c '"user_id"' sources/users.json)"
echo "    sync 首轮统计       : 新增 2，更新 0，清理 0"
echo "    变更演练统计        : 新增 1，更新 1，清理 0"
echo "    删除演练统计        : 新增 0，更新 0，清理 1"
echo "    CSV 导出数据行数    : $DATA_ROWS"
echo "    物化视图刷新        : on_sync 自动刷新 1，manual 跳过 1，手动刷新 1"
echo "E2E PASS"
