# PostgreSQL 只读读取源使用说明

本文说明如何使用 `internal/pgsource` 把 PostgreSQL 以只读方式接入 mortisedb 同步层。设计背景见 `docs/PG_READ_SOURCE_DESIGN.md`。

## 1. 定位

`internal/pgsource` 提供一条从 PostgreSQL 到 mortisedb 同步层的只读读取通道：由 `PGSource` 拉取表结构与行数据，再经 `Adapter` 转换成 `connector.Source`，供同步层消费。

## 2. 快速开始

先在配置里给出连接串和要同步的表，然后 `Open` 打开源，用 `NewAdapter` 包装成 `connector.Source`，最后交给同步流程的 `sources`。

```go
package main

import (
	"context"
	"log"

	"mortisedb/internal/pgsource"
)

func main() {
	ctx := context.Background()

	cfg := pgsource.Config{
		ConnStr: "postgres://muse_reader:change_me@host:5432/target_db",
		Tables:  []string{"orders"},
		// CursorColumn 留空时使用默认列 updated_at。
		CursorColumn: "",
		BatchSize:    1000,
	}

	src, err := pgsource.Open(ctx, cfg)
	if err != nil {
		log.Fatal(err)
	}
	defer src.Close()

	// 第二个参数是数据源在同步层里的名字。
	conn := connector.NewPGAdapter("pgmain", src, "")
	_ = conn

	// 接线位置：把 conn 放进 sync.Sync 的 sources 列表即可，
	// 由同步层调用 conn.Tables() 和 conn.Rows(table, since)。
}
```

`Adapter` 满足 `connector.Source` 接口：

- `Name()`
- `Tables()`
- `Rows(table, since map[string]string)`
- `Close()`

`Config.CursorColumn` 为空时按 `updated_at` 处理；`connector.NewPGAdapter` 的第三个参数是游标列名，传空串时同样走默认值。

### 通过 connector.Open 打开（推荐）

```go
cfg := config.SourceConfig{
    Name:        "pg_orders",
    Type:        "pg",
    Incremental: "column:updated_at",
    Tables: []config.TableMap{
        {Source: "orders", Target: "orders", PrimaryKey: "order_id"},
    },
    Options: map[string]string{
        "conn_str":      "postgres://user:pass@host:5432/db?default_transaction_read_only=on",
        "cursor_column": "updated_at",
        "batch_size":    "1000",
    },
}
src, err := connector.Open(cfg)
```

映射规则：

- `ConnStr = options["conn_str"]`，必填，缺省直接报错。
- `Tables` 取 `tables` 每项的 `source`；`tables` 为空时取单表 `table`。
- `CursorColumn` 优先取 `options["cursor_column"]`；否则解析 `incremental` 的 `column:X`；否则默认 `updated_at`。
- `BatchSize` 解析 `options["batch_size"]` 为正整数，解析失败或缺省时取 `1000`。
- sync 层零改动，仍按既有 `connector.Source` 契约调用。

## 3. 只读保障三层

1. SQL 白名单：`AssertReadOnlySQL` 要求语句以 `SELECT` 或 `WITH` 开头，且不允许出现分号，其他语句直接拒绝。
2. 只读事务：读取走 pgx 的 `ReadOnly` 事务，写操作在事务层被拒绝。
3. 连接串约束：`EnsureReadOnlyConnStr` 为连接串补上 `default_transaction_read_only=on`，让会话默认只读。

## 4. 游标语义

- 增量依据是游标列（默认 `updated_at`）的时间值，同一时间戳内用主键做 tiebreak，保证批次之间不重不漏。
- `Cursor` 由 `UpdatedAt` 和 `LastPK` 组成，通过 `Advance` 向前推进。
- `Adapter` 在 `since` 为空时使用内部记忆的游标断点续传；传入 `since` 时以传入值为准。
- `since` map 的键格式：
  - `since[cursorCol]`：RFC3339 时间字符串。
  - `since[cursorCol+":pk"]`：同一时间戳下的主键断点。

## 5. 测试说明

- 本机没有真实 PostgreSQL 时，用 `NewFakeSource` 构造假源来验证上层接线与游标推进逻辑。
- `source.go` 目前只做了编译验证，依赖 `github.com/jackc/pgx/v5 v5.11.0`。
- 与真实 PostgreSQL 的联调尚未完成，待补。
- 真实 PG 集成测试由环境变量 `MORTISE_TEST_PG_DSN` 门控，未设置时 `t.Skipf` 跳过（本沙箱无 PG 环境，诚实声明）。
- `scripts/e2e.sh` 不包含 pg 步骤（无 PG 环境）。

## 6. 限制

- 表必须有主键，并且有游标列（默认 `updated_at`）。
- 物理删除不会被捕获，同步层看不到被删掉的行。
- 表结构变更后需要重新执行 `PullTables`，否则读到的结构与实际不一致。
