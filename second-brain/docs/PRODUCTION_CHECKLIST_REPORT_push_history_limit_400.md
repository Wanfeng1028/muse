# 发版对照报告 push_history limit 400（second-brain，2026-10-28 深耕轮）

范围：`GET /api/push/history` 的 limit 参数校验收紧 + 7 子用例新测。无 UI 改动，视觉验收不适用；无迁移、无新依赖、无新增端点。

- 可靠性：新测 7/7 子用例 + 既有 TestPushHistoryUserFilter 全绿；go vet 全洁；gofmt 全洁（模型稿 import 排序由 gofmt 归位）。
- 可观测性：错误体沿用既有 writeError 格式，含“limit 参数非法”文案，可定位。
- 数据与状态：未动 store 与迁移；钳制沿用 store 既有逻辑。
- 部署运维：无部署形态改动。
- 安全与健壮性：输入校验收紧（本轮主题）；鉴权、限流未动。
- 可维护性：CHANGELOG [Unreleased] 已记；技术债：无新增；文档代码同步。

结论：靶向范围通过；全量 go test ./... 本轮未跑（上一轮基线见 CHANGELOG 0.24.0 全量 823 通过）。
