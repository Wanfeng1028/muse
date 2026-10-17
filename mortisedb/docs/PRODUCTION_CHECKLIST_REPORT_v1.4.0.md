# MortiseDB v1.4.0 生产就绪对照报告

## 一、验收硬指标

| 指标 | 命令 | 结果 |
| --- | --- | --- |
| 构建 | `go build ./...` | ✅ 通过 |
| 静态检查 | `go vet ./...` | ✅ 通过 |
| 格式检查 | `gofmt -l .` | ✅ 干净（本轮涉及文件无输出） |
| 单元与集成测试 | `go test ./...` | ✅ 全过（9 个包 ok，共 135 个测试 PASS（含子测试），0 失败；新增 `import_csv_v14_test.go` 14 例全过） |
| 端到端回归 | `scripts/e2e.sh` | ✅ E2E PASS（10 步，v1.3 全链路无回归） |
| Web UI 回归 | 导入页截图亲验 | ✅ 通过（导入页：数据源下拉真实加载/表单完整/宣纸榫卯风格无 AI 味；总览页真实数据渲染正常；`docs/screenshots/import.png`） |

## 二、v1.4 增补对照

| 增补项 | 落地位置 | 状态 |
| --- | --- | --- |
| 新端点 + 列映射 | `POST /api/import/csv`（`file`/`source` 必填，`table`/`primary_key`/`column_mapping` 可选；列名非空/唯一/正则校验；主键在映射后集合内） | ✅ 通过（真实冒烟：中文列名映射导入 inserted=2；非法映射/缺主键 400） |
| 真流式 | `<dbdir>/.import-tmp/` 临时文件（`os.CreateTemp`，处理完删除）；超 32MB → 413；边写边 sha256；sha256 命中 `_m_imports` → `duplicate=true` | ✅ 通过（5 万行真实感订单导入 Inserted=50000，临时文件无残留；33MB 流 413 不爆内存；二次导入 duplicate=true） |
| 冲突策略集成 | `manual` 挂起写 `_m_conflicts`（`source_a`=现有方来源名、`source_b`=挑战方来源名、`row_json`=挑战方行数据 JSON、`status=pending`）+ 409 冲突数组；`priority` 裁决记 `resolved_auto`；同源更新自动解决 pending | ✅ 通过（真实冒烟：manual 下跨源变更 → HTTP 409 + pending，原行未被覆盖；`GET /api/conflicts` 可查；单测 4 例锁定） |
| Web UI 导入页 | 选数据源/CSV、目标表/主键（可选）、列映射 JSON（可选）、上传；结果展示 inserted/updated/unchanged/error_rows 与错误列表；冲突朱砂提示跳转 | ✅ 通过（截图亲验，见上） |
| 测试文件 | `internal/api/import_csv_v14_test.go`、`scripts/e2e.sh` 回归 | ✅ 14/14 通过（含 5 万行流式/413 内存安全/409/列映射/幂等） |

## 三、遗留项与结论

未通过项：

- Dependabot 未开启：需用户在 GitHub Settings 手动打开，属老问题，非本次引入。

预存局限：

- `EnsureTable` 不支持导入时新增列：后续导入出现新列会返回 500，已排期。
- docker 未实测：本机无 daemon，未做容器内跑通验证。

结论：建议打 tag `mortisedb-v1.4.0`。遗留项如上，Dependabot 待用户手动开启，`EnsureTable` 新列支持与 docker 实测排入后续版本。
