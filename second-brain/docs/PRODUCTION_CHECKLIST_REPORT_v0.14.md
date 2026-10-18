
# second-brain v0.14 发版对照报告（2026-10-18）

## 变更清单

### 1. DB 迁移版本化

- 文件：internal/store/migrate.go（新增），internal/store/store.go（OpenStore 改走 Migrate()，不再直调两个分散迁移）。
- 行为：新增 Migration{Version,Name,Up} 结构体和 Migrations 有序注册表，CurrentSchemaVersion=2。新增 schema_version 表，提供 GetSchemaVersion/SetSchemaVersion/Migrate 统一入口。v1 迁移为 reviews_user_id，v2 迁移为 push_log_user_id。
- 测试文件：internal/store/migrate_test.go，4 个用例：新库写入版本、幂等重跑、老 reviews 表升级、老 push_log 表升级。

### 2. reviews_due 按用户拆分

- 文件：metrics 暴露路径（GET /metrics）。
- 行为：新增 reviews_due_by_user{user}（gauge）。按 user label 值排序输出，label 值转义反斜杠、双引号、换行。原 reviews_due（默认用户）保留，语义不变。
- 测试文件：无单独新增测试文件。

### 3. GET /api/search?format=legacy

- 文件：搜索 API 处理路径（GET /api/search）。
- 行为：format=legacy 时返回 v0.8.0 之前的纯 note 数组形状。不传 format 或 format=object 时返回现有 {query,terms,notes,meta} 对象形状。其它值返回 400，响应体 { error: '无效的 format 参数' }。
- 测试文件：无单独新增测试文件。

## 生产 checklist 关键项自评

- DB 迁移版本化：通过。schema_version 表记录当前版本，Migrations 有序注册表按版本号顺序执行，Migrate 是唯一入口。
- 可观测性：通过。新增按用户指标 reviews_due_by_user{user}，原 reviews_due 保留不动。
- 兼容性：通过。搜索 API 默认行为不变，legacy 格式只在显式传 format=legacy 时返回旧数组形状。

## 已知限制

- reviews_due_by_user 只统计有到期或默认用户，不是全量用户列表。
- 迁移版本号写在 schema_version 表，不写在代码常量之外的地方。

## 结论

待 `go test ./...` 全绿 + `go vet`/`gofmt` 全洁后可发版。
