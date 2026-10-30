# feedflow Production Checklist Report v1.40.0 (2026-10-30) - 修复 folder_id 校验，拒绝 bool/float

## 验收结果表

| 验证项 | 结果 | 证据 |
| :--- | :--- | :--- |
| 定向 pytest | 41 passed, 1 failed | 运行新测试 (10) + `tests/test_api_deep2.py` + mark_read v139/v138 测试。失败项为 `tests/test_api_deep2.py::test_articles_pagination_edge_cases`，已在干净代码树上重现，为预先存在的 v1.21 旧契约失败，与本次变更无关。 |
| ruff check | clean | `feedflow/api.py` 及新测试文件全部通过 ruff 检查。 |
| 真实服务冒烟测试 | 通过 | 端口 18511，隔离数据库：healthz 返回 200；create 传 True 和 1.5 均返回 400；不带 folder_id 创建返回 201；update 传 True 返回 400；update 传 3 返回 200 且 folder_id 为 3；找不到 feed 传 True 返回 404。测试结束后已确认服务停止、端口关闭，隔离数据库已删除。 |

## 对照表

| 验收域 | 结果 | 理由 |
| :--- | :--- | :--- |
| 可靠性 | 通过 | 拦截非法输入的逻辑明确且已被 10 个新测试覆盖；遗留的 1 个测试失败已确认并记录为与本次无关的历史问题。 |
| 可观测性 | 未通过 | 针对此次新增的非法请求拦截，没有新增专门的 Prometheus 监控指标。 |
| 数据与状态 | 通过 | 未修改数据库结构，输入校验在写入存储前完成，冒烟测试使用隔离数据库并已彻底清理。 |
| 部署与运维 | 通过 | 未引入新的部署配置，现有的 Docker Compose 设置未做任何改动。 |
| 安全与健壮性 | 通过 | 已在这两个端点上修复了 bool/float 被误解析为 int 的漏洞；其他仍使用基础 `int()` 转换的地方已作为已知限制显式列出。 |
| 可维护性 | 通过 | 核心改动仅 4 行，新增 10 个测试，CHANGELOG 已同步更新。 |

## 已知限制清单

- 本轮未运行完整 pytest（full pytest）。
- `update_feed` 的 `interval_min`/`enabled`/`position` 以及 `create_feed` 的 `interval_min` 依然使用基础的 `int()` 进行转换。
- 在 create/update 接口中，负数的 `folder_id` 依然能够通过校验。
- 缺少针对此次校验拒绝逻辑的 Prometheus 监控指标。
- 单用户系统设计保持不变。
- 本次未涉及 UI 变更，因此没有生成新的截图。
- 本次未涉及 Schema 变更，因此无需数据库迁移。

## 结论

尽管存在上述记录在案的边缘情况限制，本次版本包含的修复验证充分，可以作为此小范围修复的正式发布版本。