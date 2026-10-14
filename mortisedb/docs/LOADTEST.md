# MortiseDB 负载验证（10 万行 × 3 源）

本文档记录 2026-10-13 在真实机器上的实测结果（v1.1，`sync.batch_size=5000`）。

## 1. 环境

| 项 | 值 |
| --- | --- |
| CPU | Intel Xeon Platinum 8321HC @ 1.40GHz（2 vCPU，本次测试机） |
| 内存 | 8 GB（测试时可用约 1.1 GB） |
| OS | Ubuntu 24.04.5 LTS / Linux 7.0.0-39-generic |
| Go 版本 | go1.23.4 linux/amd64 |
| 磁盘 | btrfs |
| MortiseDB 版本 | `1.1.0`（commit 61ea155，批量事务优化后） |

## 2. 数据生成

```bash
# 生成三源各 10 万行数据 + mortise-load.yaml
bash scripts/loadtest.sh ./loadtest-work
cd ./loadtest-work
```

生成内容：
- `sources/orders.csv`：10 万行，含 `order_id,user_id,amount,updated_at`，`updated_at` 递增。
- `sources/users.json`：10 万行，`{"data":{"users":[...]}}`。
- `sources/archive.db`：SQLite 表 `events(event_id PK, user_id, action, ts)` 10 万行。
- `mortise-load.yaml`：三源配置 + 跨源 JOIN 视图 `v_load_join`。

## 3. 同步计时

```bash
# /usr/bin/time 在本机缺失，改用 timewrap.sh（date +%s%N 计 wall 时间，轮询 /proc/<pid>/status 的 VmHWM 计峰值 RSS）
./timewrap.sh sync_new ./mortisedb sync --config mortise-load.yaml
# 输出：prefix=sync_new exit=0 wall_s=265.89 peak_rss_kb=166160
```

## 4. 视图查询计时

```bash
mortisedb query --config mortise-load.yaml \
  "SELECT COUNT(*) FROM (SELECT o.order_id, o.amount, u.name FROM orders o LEFT JOIN users u ON o.user_id = u.user_id WHERE o._m_deleted = 0 AND u._m_deleted = 0)"
# 实测：100000 行，wall 452ms（v_load_join；v1.2 起 YAML 声明视图已自动注册进 _m_views，本次为等价 SQL 直查计时口径不变）
```

## 5. 结果（2026-10-13 实测）

### 5.1 同步

| 源 | 表 | 行数 | 首次全量耗时 | 峰值内存（VmHWM） | 备注 |
| --- | --- | --- | --- | --- | --- |
| load_csv | orders | 100000 | 与 users/events 合计 265.89s（见下） | 166160 KB（进程级） | updated_at 增量 |
| load_json | users | 100000 | 同上 | 同上 | hash 全量，最慢的一源 |
| load_sqlite | events | 100000 | 同上 | 同上 | ts 增量 |

- 三源合计：300000 行，wall 265.89s（约 1128 行/秒），exit=0；目标库 43933696 字节（约 42MB）。
- 行数校验：`SELECT COUNT(*)` 三表均为 100000，与源（csv 100001 含表头 / json 100000 / sqlite 100000 distinct）一致。
- 对比基线：批量事务优化前（逐行自动提交）实测约 38 行/秒，10 万行需约 44 分钟；优化后约 1128 行/秒，**约 30 倍**。
- 测试时另有一个旧代码同步进程在同机运行，存在轻度 CPU 争用，数字为保守值。

### 5.2 视图查询

| 视图 | 行数 | 耗时（wall） |
| --- | --- | --- |
| v_load_join（等价 SQL直查） | 100000 | 452ms |

## 6. 结论

v1.1 在 2 vCPU / 8GB 的弱 VM 上：30 万行三源同步 265.89s（峰值 RSS 162MB），跨源 JOIN 10 万行 452ms。批量事务（`sync.batch_size`，默认 5000）是关键优化，相对逐行提交约 30 倍提升。10 万行量级可用；百万行以上需流式 connector（见 §7）。

## 7. 已知限制

- connector.go 中 CSV/JSON/SQLite 三源均把整表结果累积在内存 `[]Row` 中返回，10 万行量级内存约 20-120 MB（详见 `scripts/loadtest.sh` 顶部注释）。更大数据量（百万行以上）需要后续改为流式处理。
- SQLite 源的水位线过滤在 Go 侧做（`matchSince`），不下推 SQL WHERE，数据量大时增量同步仍会全表扫描。
- ~~`views list` 不会自动注册 yaml 里声明的视图~~ —— v1.2 已落地自动注册（`views.SyncFromConfig`，见 README「视图自动注册」节），本轮计时口径仍为等价 SQL 直查。
