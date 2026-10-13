# MortiseDB 负载验证（10 万行 × 3 源）

本文档描述在真实机器上验证 MortiseDB v1.1 处理 10 万行量级数据的能力。所有数字均为**占位符**，需由编排者在目标机器上实测填写。

## 1. 环境

| 项 | 值 |
| --- | --- |
| CPU | `<待填，如 Intel Xeon E5-2686 v4 @ 2.30GHz (4 vCPU)>` |
| 内存 | `<待填，如 16 GB DDR4>` |
| OS | `<待填，如 Ubuntu 22.04.3 LTS / Linux 5.15>` |
| Go 版本 | `<待填，如 go1.22.5 linux/amd64>` |
| 磁盘 | `<待填，如 SSD>` |
| MortiseDB 版本 | `1.1.0` |

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
/usr/bin/time -v mortisedb sync --config mortise-load.yaml 2>&1 | tee sync.log
```

提取：
- `wall clock`（真实耗时）
- `Maximum resident set size`（峰值内存）

## 4. 视图查询计时

```bash
/usr/bin/time -v mortisedb query --config mortise-load.yaml \
  "SELECT COUNT(*) FROM v_load_join" 2>&1 | tee query.log
```

## 5. 结果

### 5.1 同步

| 源 | 表 | 行数 | 首次全量耗时 | 增量耗时 | 峰值内存 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| load_csv | orders | 100000 | TBD(实测填) | TBD(实测填) | TBD(实测填) | |
| load_json | users | 100000 | TBD(实测填) | TBD(实测填) | TBD(实测填) | hash 全量 |
| load_sqlite | events | 100000 | TBD(实测填) | TBD(实测填) | TBD(实测填) | ts 增量 |

### 5.2 视图查询

| 视图 | 行数 | 耗时 | 峰值内存 |
| --- | --- | --- | --- |
| v_load_join | 100000 | TBD(实测填) | TBD(实测填) |

## 6. 结论

`TBD(实测填)`

## 7. 已知限制

- connector.go 中 CSV/JSON/SQLite 三源均把整表结果累积在内存 `[]Row` 中返回，10 万行量级内存约 20-120 MB（详见 `scripts/loadtest.sh` 顶部注释）。更大数据量（百万行以上）需要后续改为流式处理。
- SQLite 源的水位线过滤在 Go 侧做（`matchSince`），不下推 SQL WHERE，数据量大时增量同步仍会全表扫描。
