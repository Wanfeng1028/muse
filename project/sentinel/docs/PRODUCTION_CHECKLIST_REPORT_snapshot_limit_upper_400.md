# sentinel 发版对照报告：快照列表 limit 上限 200 校验（2026-10-28）

1. 构建与靶向测试：通过。理由：新增测试 6 例（limit=201/1000 均 400；limit=200/50 均 200 且 items 2；limit=abc/0 均 400）；靶向测试 6/6 通过，handlers 全包通过，go vet 全洁，gofmt 全洁。
2. 视觉验收：不适用。理由：本轮无 UI 改动。
3. 全量回归测试：未通过。理由：全量 go test ./... 本轮未跑，下一轮补跑。
4. 部署：通过。理由：改动面极小，仅 internal/handlers/snapshot_archive.go 一行条件，不影响整体部署。
5. 安全：通过。理由：limit>200 拦截返回 400“limit 参数非法”；Store 层上限 200 留作防御未动。
6. 可维护性：通过。理由：CHANGELOG 已记 0.33.3 小节、无 schema 变更，代码逻辑改动清晰，易于后续维护。
