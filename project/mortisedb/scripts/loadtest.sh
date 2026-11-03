#!/usr/bin/env bash
# MortiseDB 负载验证数据生成脚本（三源各 10 万行）。
#
# 用途：生成 CSV/JSON/SQLite 三种数据源各 10 万行，并输出 mortise-load.yaml。
#       脚本只负责数据生成与行数校验，不自动计时同步，请按 docs/LOADTEST.md 手动执行。
#
# 内存量级预期（基于 connector.go 的实现）：
#   - CSV 连接器：逐行流式读取，但会把全部行累积到 []Row 返回 → 每行 map[string]any 约 100-200 字节，
#                 10 万行量级约 20-40 MB 常驻（含 GC 前峰值）。
#   - JSON 连接器：os.ReadFile 一次性读入 + json.Unmarshal 到 []any → 峰值内存约为文件大小的 3-5 倍，
#                 10 万行 JSON 约 15-25 MB 文件 → 峰值 60-120 MB。
#   - SQLite 连接器：逐行 scan，同样累积到 []Row → 与 CSV 类似，约 20-40 MB。
#   建议验证机内存 ≥ 1 GB，Go 版本 ≥ 1.22。
#
# 依赖：python3（生成 JSON）或 sqlite3（生成 archive.db），二者至少其一。

set -euo pipefail

ROWS=100000
WORKDIR="${1:-./loadtest-work}"

echo "==> 工作目录: ${WORKDIR}"
mkdir -p "${WORKDIR}/sources"
mkdir -p "${WORKDIR}/data"

# ---------- 1. 生成 orders.csv ----------
echo "==> 生成 orders.csv (${ROWS} 行)..."
python3 - "$ROWS" "${WORKDIR}/sources/orders.csv" <<'PY'
import sys, csv, datetime
rows = int(sys.argv[1])
out = sys.argv[2]
base = datetime.datetime(2026, 1, 1, 0, 0, 0)
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["order_id", "user_id", "amount", "updated_at"])
    for i in range(1, rows + 1):
        ts = (base + datetime.timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S")
        w.writerow([i, "u%06d" % (i % 10000 + 1), "%.2f" % (i * 0.5), ts])
PY

# ---------- 2. 生成 users.json ----------
echo "==> 生成 users.json (${ROWS} 行)..."
python3 - "$ROWS" "${WORKDIR}/sources/users.json" <<'PY'
import sys, json
rows = int(sys.argv[1])
out = sys.argv[2]
users = []
for i in range(1, rows + 1):
    users.append({
        "user_id": "u%06d" % i,
        "name": "user-%d" % i,
        "age": 18 + (i % 60),
        "active": (i % 2 == 0),
    })
with open(out, "w", encoding="utf-8") as f:
    json.dump({"data": {"users": users}}, f, ensure_ascii=False)
PY

# ---------- 3. 生成 archive.db ----------
echo "==> 生成 archive.db (${ROWS} 行 events)..."
if command -v sqlite3 >/dev/null 2>&1; then
    rm -f "${WORKDIR}/sources/archive.db"
    python3 - "$ROWS" "${WORKDIR}/sources/archive.db" <<'PY'
import sys, sqlite3, datetime
rows = int(sys.argv[1])
path = sys.argv[2]
conn = sqlite3.connect(path)
cur = conn.cursor()
cur.execute("CREATE TABLE events (event_id INTEGER PRIMARY KEY, user_id TEXT, action TEXT, ts TEXT)")
base = datetime.datetime(2026, 1, 1, 0, 0, 0)
data = []
for i in range(1, rows + 1):
    ts = (base + datetime.timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S")
    data.append((i, "u%06d" % (i % 10000 + 1), "click", ts))
cur.executemany("INSERT INTO events (event_id, user_id, action, ts) VALUES (?,?,?,?)", data)
conn.commit()
conn.close()
PY
else
    echo "警告: 未找到 sqlite3 命令，尝试用 python3 的 sqlite3 模块..." >&2
    python3 - "$ROWS" "${WORKDIR}/sources/archive.db" <<'PY'
import sys, sqlite3, datetime
rows = int(sys.argv[1])
path = sys.argv[2]
conn = sqlite3.connect(path)
cur = conn.cursor()
cur.execute("CREATE TABLE events (event_id INTEGER PRIMARY KEY, user_id TEXT, action TEXT, ts TEXT)")
base = datetime.datetime(2026, 1, 1, 0, 0, 0)
data = []
for i in range(1, rows + 1):
    ts = (base + datetime.timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S")
    data.append((i, "u%06d" % (i % 10000 + 1), "click", ts))
cur.executemany("INSERT INTO events (event_id, user_id, action, ts) VALUES (?,?,?,?)", data)
conn.commit()
conn.close()
PY
fi

# ---------- 4. 生成 mortise-load.yaml ----------
echo "==> 生成 mortise-load.yaml..."
cat > "${WORKDIR}/mortise-load.yaml" <<EOF
version: 1
database: "${WORKDIR}/data/mortise.db"
addr: ":8421"

sources:
  - name: load_csv
    type: csv
    path: "${WORKDIR}/sources/orders.csv"
    table: orders
    primary_key: order_id
    incremental: "column:updated_at"

  - name: load_json
    type: json
    path: "${WORKDIR}/sources/users.json"
    table: users
    primary_key: user_id
    incremental: hash
    options:
      root: "data.users"

  - name: load_sqlite
    type: sqlite
    path: "${WORKDIR}/sources/archive.db"
    tables:
      - source: events
        target: events
        primary_key: event_id
    incremental: "column:ts"

views:
  - name: v_load_join
    sql: "SELECT o.order_id, o.amount, u.name FROM orders o LEFT JOIN users u ON o.user_id = u.user_id WHERE o._m_deleted = 0 AND u._m_deleted = 0"
    description: "跨源 JOIN 视图（orders ← users）"

jobs:
  - name: load
    interval: "5m"
    sources: []

sync:
  conflict: priority
  priority:
    - load_csv
    - load_json
    - load_sqlite
  soft_delete: true
EOF

# ---------- 5. 行数校验 ----------
echo "==> 行数校验..."

csv_rows=$(($(wc -l < "${WORKDIR}/sources/orders.csv") - 1))
if [ "${csv_rows}" -ne "${ROWS}" ]; then
    echo "错误: orders.csv 期望 ${ROWS} 行，实际 ${csv_rows} 行" >&2
    exit 1
fi
echo "  orders.csv:    ${csv_rows} 行 ✓"

json_rows=$(python3 -c "import json,sys; d=json.load(open('${WORKDIR}/sources/users.json')); print(len(d['data']['users']))")
if [ "${json_rows}" -ne "${ROWS}" ]; then
    echo "错误: users.json 期望 ${ROWS} 行，实际 ${json_rows} 行" >&2
    exit 1
fi
echo "  users.json:    ${json_rows} 行 ✓"

db_rows=$(python3 -c "import sqlite3; c=sqlite3.connect('${WORKDIR}/sources/archive.db'); print(c.execute('SELECT COUNT(*) FROM events').fetchone()[0])")
if [ "${db_rows}" -ne "${ROWS}" ]; then
    echo "错误: archive.db 期望 ${ROWS} 行，实际 ${db_rows} 行" >&2
    exit 1
fi
echo "  archive.db:    ${db_rows} 行 ✓"

echo
echo "=================================================="
echo "数据生成完成，位于 ${WORKDIR}/sources/"
echo "配置文件: ${WORKDIR}/mortise-load.yaml"
echo
echo "下一步（手动计时）:"
echo "  1. cd ${WORKDIR}"
echo "  2. /usr/bin/time -v mortisedb sync --config mortise-load.yaml"
echo "  3. /usr/bin/time -v mortisedb query --config mortise-load.yaml \"SELECT COUNT(*) FROM v_load_join\""
echo "  4. 记录 wall time / max RSS，填入 docs/LOADTEST.md"
echo "=================================================="
