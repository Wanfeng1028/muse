# Production Checklist Report — v2.17.19 (2026-10-26)

## 变更摘要

- 仅 workbench 批次条目 `status` 入参校验（非法值返回 400，错误信息明确）。
- 版本号四处同步：`__init__`、`pyproject`、`CHANGELOG`、版本一致性测试 EXPECTED_VERSION。
- tests/test_workbench_api.py 末尾追加 6 个用例。
- `CHANGELOG` 新增一节。
- 无数据库迁移、无新依赖、无 UI 改动、无配置项新增。

## 逐条对照表

| 检查项 | 结果 | 说明 | 实测/证据 |
|---|---|---|---|
| 单元 / 集成测试 | 通过 | test_workbench_api.py 追加 6 用例覆盖 workbench `status` 校验路径 | 新测试 6/6 通过 |
| 全量 pytest | 通过 | 全量测试执行 | 1457 通过、1 跳过、0 失败（较 v2.17.18 的 1451 通过恰增 6） |
| Ruff 静态检查 | 通过 | 静态检查 | 本轮改动行零新增 ruff 错误（workbench 13 错与测试文件 1 错均为 HEAD 既存）；本轮改动行格式洁净，其余格式差异均为既存 |
| 输入校验 | 通过 | 非法 `status` 返回 400，错误信息明确 | 已验证 |
| 错误可定位 | 通过 | 错误 detail 包含合法取值 | 已验证 |
| 版本一致性 | 通过 | `__init__` / `pyproject` / `CHANGELOG` / 版本测试四处一致 | 版本比对 |
| 文档同步 | 通过 | `CHANGELOG` 与本报告同步 | 已核对 |
| 真实服务冒烟 | 通过 | 真实服务冒烟测试 | 8129 端口隔离库（demo.db 复制库）：bogus/空串 400 且 detail 正确、all/pending 200 且 total 10、claimed 200 且 total 0、不存在的批次加 bogus 404，6/6 通过；冒烟后服务已停 |
| 数据库迁移 | 不适用 | 无表结构变化 | N/A |
| Docker / 部署 | 不适用 | 无运行形态变化 | N/A |
| 备份恢复 | 不适用 | 无数据格式变化 | N/A |
| 视觉验收 | 不适用 | 无 UI 改动 | N/A |
| 故障演练 | 不适用 | 本轮无韧性机制变化 | N/A |

## 已知限制

- 其余列表端点（账单条目、交易列表等）的 `status` / `limit` 类参数仍沿用 FastAPI `Query` 的 422 口径，本轮仅收紧工作台批次条目这一处。
- `status` 校验仅在 HTTP 层生效，服务层直接调用仍可传入任意值。