# PostgreSQL 只读源设计

## 1. 目标

把 PostgreSQL 里已有的表以只读方式接进 mortisedb 的拼装层。mortisedb 现有的 internal/store 走的是 SQLite（modernc.org/sqlite 纯 Go），sync 包负责多源合并（UnifyTypes 做类型统一）。本轮要做的是：让一个 PostgreSQL 库也成为一个源，它的表结构和行数据能被 sync 读取、参与合并，但 mortisedb 永远不会往 PostgreSQL 写任何东西。

具体边界：

- 只读：只允许 SELECT 打到 PG。INSERT / UPDATE / DELETE / DDL 一律在应用层拦掉，不到数据库。
- 不写回：mortisedb 对 PG 只有读路径，没有写路径。
- 参与合并：PG 源产出的表、列、行，走和 SQLite 源一样的接口，交给 sync 的合并逻辑。

## 2. 驱动选型

候选三个：pgx v5、lib/pq、纯 database/sql + pgx stdlib。从四个维度打分，1 到 5 分，5 分最好。

### 维度一：维护状态

- pgx v5：活跃维护，作者持续发版，issue 响应快。5 分。
- lib/pq：已进入维护模式，官方 README 建议新项目用 pgx。2 分。
- database/sql + pgx stdlib：底层就是 pgx，维护状态跟着 pgx。5 分。

### 维度二：是否需要 cgo

- pgx v5：纯 Go，不需要 cgo。5 分。
- lib/pq：纯 Go，不需要 cgo。5 分。
- database/sql + pgx stdlib：纯 Go，不需要 cgo。5 分。

### 维度三：类型映射完整度

- pgx v5：原生协议，类型覆盖最全，jsonb、numeric、timestamptz、数组、复合类型都有对应处理。5 分。
- lib/pq：类型覆盖够日常用，但新类型跟进慢，jsonb 等要自己包一层。3 分。
- database/sql + pgx stdlib：走 database/sql 的 driver.Value 抽象，pgx 原生类型信息在标准接口层会丢一部分，jsonb 拿到的常常是 []byte，numeric 拿到的常常是字符串。4 分。

### 维度四：与 modernc.org/sqlite 纯 Go 路线的一致性

- pgx v5：纯 Go，交叉编译不用额外配 C 工具链，和 modernc.org/sqlite 一致。5 分。
- lib/pq：纯 Go，也一致。5 分。
- database/sql + pgx stdlib：纯 Go，也一致。5 分。

### 汇总

| 候选 | 维护状态 | 是否需要 cgo | 类型映射完整度 | 与 modernc.org/sqlite 一致性 | 总分 |
| --- | --- | --- | --- | --- | --- |
| pgx v5 | 5 | 5 | 5 | 5 | 20 |
| lib/pq | 2 | 5 | 3 | 5 | 15 |
| database/sql + pgx stdlib | 5 | 5 | 4 | 5 | 19 |

### 选择

选 pgx v5，走它的原生接口（pgxpool + pgx.Rows），不走 database/sql 那层。

一句话理由：总分最高，且原生协议能把 PG 的 jsonb、numeric、timestamptz 这些类型带得更完整，正好省掉类型映射里一堆手工兜底。

### 版本号

版本号这块我不编。2026-10-17 当天可验证的最新稳定版，需要人类在本机跑命令确认，命令如下：

```
go list -m -versions github.com/jackc/pgx/v5
```

取输出里最后一个 v5 稳定版本号，写进 go.mod。

## 3. 类型映射表

PG 类型到 mortisedb 内部类型的对应关系：

| PG 类型 | mortisedb 内部类型 |
| --- | --- |
| text | TEXT |
| varchar | TEXT |
| int4 | INTEGER |
| int8 | INTEGER |
| numeric | REAL |
| bool | BOOLEAN |
| timestamptz | DATETIME |
| jsonb | TEXT |
| 其余 | TEXT |

映射在 PGSource.PullTables 里做：从 information_schema.columns 或 pg_catalog 读列定义，按上表把 PG 类型名转成 mortisedb 内部类型，产出和 SQLite 源结构一致的表描述。

### 如何复用 UnifyTypes

UnifyTypes 是 sync 包里做类型统一的函数。PG 源不自己实现一套类型合并逻辑，做法是：

1. PGSource.PullTables 把每个列映射成 mortisedb 内部类型（上表），产出这个源自己的列类型视图。
2. 这个视图连同 SQLite 源的列类型视图，一起喂给 sync.UnifyTypes。
3. UnifyTypes 按它现有规则做跨源统一，PG 源不需要改 sync 的代码。

这样 PG 源只负责“把 PG 类型翻译成内部类型”，合并策略仍然集中在 sync，一处维护。

## 4. 只读保障

三层，从应用层到数据库层。

### 第一层：应用层 SQL 白名单

所有要发给 PG 的 SQL，先过一道正则白名单，只放行 SELECT 和 WITH 开头的查询：

```go
var readOnlySQL = regexp.MustCompile(`(?is)^\s*(select|with)\b`)
```

不匹配的直接返回错误，不建立到数据库的往返。这一层挡掉拼错的写语句，成本最低。

### 第二层：PG 只读事务

真正执行查询时，在事务里先设只读：

```sql
BEGIN;
SET TRANSACTION READ ONLY;
-- 查询
COMMIT;
```

用 pgx 的事务选项做更干净：

```go
tx, err := conn.BeginTx(ctx, pgx.TxOptions{
    AccessMode: pgx.ReadOnly,
})
```

数据库层再兜一次，即使应用层白名单被绕过，写操作在只读事务里也会被 PG 拒掉。

### 第三层：只读账号

部署文档里必须写明：给 mortisedb 用的 PG 连接账号，只授予目标表的 SELECT 权限，不授予 INSERT / UPDATE / DELETE / TRUNCATE，不授予 CREATE 等 DDL 权限。

创建账号的语句：

```sql
CREATE ROLE muse_reader LOGIN PASSWORD 'change_me';
GRANT CONNECT ON DATABASE target_db TO muse_reader;
GRANT USAGE ON SCHEMA public TO muse_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO muse_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO muse_reader;
```

### 连接串参数

连接串不依赖 `default_query_exec_mode` 这个参数名，那个是别的驱动的东西，pgx 不走这条路。pgx 用 `default_transaction_read_only` 会话参数更靠谱，在连接串里带上：

```
postgres://muse_reader:change_me@host:5432/target_db?default_transaction_read_only=on
```

这个参数是 PG 服务端会话参数，pgx 会把它作为启动参数发过去，会话级只读，和上面第二层的只读事务形成双重保险。

## 5. 增量同步

两种方案对比。

### 方案 A：updated_at 游标

每个要同步的表要求有一个 updated_at 时间列。第一次全量拉，记下最大 updated_at。之后每次拉 `WHERE updated_at > $1 ORDER BY updated_at`，游标往后推。

优点：实现简单，只读，不需要 PG 开额外配置，对数据库压力可控。缺点：要求表有 updated_at 列；同一时间戳内的多行要靠主键辅助去重；物理删除的行抓不到。

### 方案 B：逻辑复制（wal2json）

在 PG 上开逻辑复制槽，用 wal2json 插件把 WAL 变更解析出来，推给 mortisedb。

优点：能抓到 insert / update / delete，实时性好。缺点：要在 PG 上改 `wal_level = logical`，要装 wal2json 扩展，要管理复制槽生命周期，复制槽不消费会撑爆 WAL，运维复杂度高出一截。

### v1 只做游标方案的理由

v1 的目标是把 PG 以只读方式接进拼装层，先跑通读取和合并这条主链路。游标方案只读、零 PG 侧配置改动、实现量小，能最快验证 PG 源和 sync 的对接是否正确。逻辑复制要动 PG 服务端配置，属于运维面的重决策，不适合放进第一版。等 v1 跑稳、增量抓删除的需求明确之后，再把逻辑复制作为 v2 候选方案单独评估。

## 6. 接口设计

命名跟现有 Store 的习惯对齐：构造函数用 Open，读操作在 Pull 前缀下，收尾用 Close。

```go
type PGSource struct {
    connStr   string
    pool      *pgxpool.Pool
    tables    []string
    cursor    map[string]time.Time
    batchSize int
}

func Open(ctx context.Context, connStr string) (*PGSource, error)

func (s *PGSource) PullTables(ctx context.Context) ([]TableSchema, error)

func (s *PGSource) PullRows(ctx context.Context, table string, since time.Time) ([]Row, error)

func (s *PGSource) Close() error
```

字段说明：

- connStr：PG 连接串，构造时传入，带只读会话参数。
- pool：pgxpool 连接池，Open 时建立，Close 时关掉。
- tables：要同步的表名列表，Open 后由调用方设置或从配置读。
- cursor：每张表上一次同步到的 updated_at 游标。
- batchSize：单次 PullRows 拉多少行，控制内存。

方法说明：

- Open：建连接池，验证连通性和只读账号权限，返回 PGSource。
- PullTables：读表结构，按第 3 节映射成内部类型，产出 TableSchema 列表。
- PullRows：按表名和游标拉增量行，SQL 过只读白名单，走只读事务。
- Close：关连接池，释放资源。

TableSchema 和 Row 用 sync 包里现有的结构体，不新造类型。这里写的名字是接口占位约定，落地时以 sync 包里逐字存在的定义为准。

## 7. 风险与不做事项

### 不做事项（v1 明确不支持）

- 不支持写入：mortisedb 不会向 PG 发任何 INSERT / UPDATE / DELETE。
- 不支持 DDL 同步：PG 侧的表结构变更（加列、改类型、删表）不会自动同步到 mortisedb，需要重新跑 PullTables。
- 不支持大对象：bytea 之外的 large object 不走，PG 的 lo 类型不读。

### 风险

- updated_at 游标依赖表上有 updated_at 列且该列被正确维护。表没有这列，或者应用写数据时不更新这列，增量就会漏。需要在接入前逐表确认。
- 同一 updated_at 时间戳内的多行，游标推进时要靠主键做边界处理，否则可能漏行或重复拉。PullRows 实现里要带上主键排序和大于游标的严格判断。
- 逻辑删除（物理删除行）游标方案抓不到。v1 接受这个缺口，等 v2 评估逻辑复制。
- 只读账号权限配错（误给写权限）会让第二、三层的只读保障退化。部署时要有检查项，确认账号只有 SELECT。