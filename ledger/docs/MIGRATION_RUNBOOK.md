# 数据库迁移运维手册

本手册适用于 ledger（钱迹）后端的 SQLite 数据库迁移运维，覆盖版本对照、升级流程、回滚流程、回滚限制与故障排查。

迁移逻辑由应用启动时自动执行的 `run_migrations` 负责，版本号记录在 SQLite 的 `PRAGMA user_version` 中。

## 1. 版本与 user_version 对照表

| user_version | 版本 | 变更摘要 |
| --- | --- | --- |
| 1 | v1 | 初始化基础表结构（账户、分类、交易等核心业务表）。 |
| 2 | v2 | 引入账单/流水相关的扩展结构。 |
| 3 | v3 | 引入对账或语句导入相关结构（statement 相关表）。 |
| 4 | v4 | 扩展分类与规则相关字段，完善业务约束。 |
| 5 | v5 | 引入匹配规则（match_rules）等规则引擎基础结构。 |
| 6 | v6 | match_rules 增加 pattern_type/is_enabled/hit_count 三列并重建唯一约束；statement_items 增加 suggested_rule_id；新建 report_schemes 表。 |

> 说明：v1..v5 的摘要为版本演进概述，具体以仓库历史迁移代码为准；v6 内容以上表描述为准。

## 2. 升级流程

升级采用「先备份、再迁移、后校验」的顺序，迁移在应用启动时自动执行。

### 2.1 备份

1. 停止应用写入（或确认无写入流量）。
2. 备份 SQLite 数据库文件（含 `-wal`、`-shm` 若存在），保存到安全位置：
   - 复制数据库文件本体；
   - 记录当前 `PRAGMA user_version` 值，便于回退比对。
3. 记录备份文件路径与时间戳。

### 2.2 跑迁移

1. 启动应用，`run_migrations` 会在启动过程中自动执行，将数据库升级到目标版本。
2. 观察启动日志，确认迁移无报错、无异常中断。
3. 若启动过程中断，先不要反复重启，按第 5 节排查。

### 2.3 校验 SQL

迁移完成后，使用 SQL 抽查版本与结构。

校验 `user_version`：

```sql
PRAGMA user_version;
```

预期：返回值等于目标版本号（升级到 v6 时应为 `6`）。

表结构抽查：

```sql
-- 检查 match_rules 新增列
PRAGMA table_info(match_rules);
-- 期望包含：pattern_type、is_enabled、hit_count

-- 检查 statement_items 新增列
PRAGMA table_info(statement_items);
-- 期望包含：suggested_rule_id

-- 检查 report_schemes 表存在
PRAGMA table_info(report_schemes);

-- 检查 match_rules 唯一约束是否重建
PRAGMA index_list(match_rules);
```

抽查通过标准：

- `match_rules` 存在 `pattern_type`、`is_enabled`、`hit_count` 三列。
- `statement_items` 存在 `suggested_rule_id` 列。
- `report_schemes` 表存在且列结构完整。
- `match_rules` 的唯一约束为重建后的约束。

## 3. 回滚流程（v6 → v5）

回滚使用脚本 `scripts/rollback_v6_to_v5.py`，务必先 dry-run 再执行。

### 3.1 dry-run 查看步骤

```bash
.venv/bin/python scripts/rollback_v6_to_v5.py --dry-run
```

dry-run 只打印将执行的步骤，不修改数据库。确认步骤与影响范围符合预期后再继续。

### 3.2 正式执行

```bash
.venv/bin/python scripts/rollback_v6_to_v5.py --yes
```

- 必须显式加 `--yes` 才会真正执行回滚。
- 回滚过程中发现的冲突行会写入 `.rollback_conflicts.json`。
- 执行完成后，确认 `PRAGMA user_version` 回到 `5`。

### 3.3 处理冲突

1. 打开 `.rollback_conflicts.json`，查看冲突行明细。
2. 根据冲突原因人工修复数据或规则配置。
3. 如需重新回滚，先处理冲突文件，避免冲突累积。

## 4. 回滚限制声明

回滚 v6 → v5 会丢弃 v6 引入的数据与结构，属于破坏性操作：

- 丢失 `match_rules` 的 `pattern_type`、`is_enabled`、`hit_count` 列及其数据。
- 丢失 `statement_items` 的 `suggested_rule_id` 列及其数据。
- 丢失 `report_schemes` 表及其全部数据。

回滚完成后必须重新评估规则：

- 重新确认 `match_rules` 的匹配行为（原有 pattern_type / 启用状态信息已丢失）。
- 重新配置或确认报表方案（report_schemes 数据已丢失）。
- 核对 statement_items 的规则建议关联（suggested_rule_id 已丢失）。

在回滚前，务必确认已备份数据库文件，且已导出或记录需要保留的 v6 数据。

## 5. 故障排查

### 5.1 user_version 卡住

现象：迁移后 `PRAGMA user_version` 未达到目标版本。

排查步骤：

1. 查看应用启动日志，定位迁移中断的位置与报错信息。
2. 用 `PRAGMA user_version;` 确认当前版本。
3. 检查数据库文件是否可写、磁盘空间是否充足。
4. 若迁移被中断，优先从备份恢复后重试，不要在半迁移状态下反复启动。

### 5.2 约束重建失败

现象：`match_rules` 唯一约束重建报错。

排查步骤：

1. 用 `PRAGMA index_list(match_rules);` 与 `PRAGMA index_info(<index_name>);` 检查现有索引与约束。
2. 检查是否存在重复数据导致唯一约束无法建立。
3. 清理重复行后重试；或从备份恢复后重试。
4. 重建失败时不要强行改 `user_version`，以免版本与结构不一致。

### 5.3 备份恢复步骤

1. 停止应用，确保无写入。
2. 将备份的数据库文件（含 `-wal`、`-shm` 若存在）覆盖回原路径。
3. 确认 `PRAGMA user_version;` 与备份时记录一致。
4. 启动应用，观察迁移日志。
5. 按第 2.3 节校验 SQL 再次抽查结构与版本。
6. 如仍异常，保留现场数据库文件与日志，再行分析。
