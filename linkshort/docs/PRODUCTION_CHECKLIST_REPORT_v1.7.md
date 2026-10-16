
# linkshort v1.7.0 发版对照报告

- 版本：v1.7.0「burn 逐条彻底删除 + 备份恢复自动化演练」
- 日期：2026-10-16
- 结论：可发版

## 1. 可靠性
- [通过] 测试金字塔：`go test ./... -race` 共 104 例全绿（v1.6.0 的 95 例 + 新增 9 例：store 4——v4→v5 真实迁移/CreateLinkEx purge 标记/UpdateLinkEx purge 标记/PurgeLink 删行+visits 级联；handler 5——purge 非 burn 报 400/逐条 purge 302→404/默认软保留 302→410/PATCH 设 purge/全局开关仍有效）。
- [通过] 失败注入：v1.2 关库场景用例仍通过。
- [通过] 迁移版本化：v4→v5 用 `PRAGMA user_version` 标记，`links.purge_after_burn INTEGER NOT NULL DEFAULT 0`，老库自动 ALTER，老行默认 0，真实老库实测升级通过。
- [通过] 健康检查/就绪探针：优雅关闭/readyz 未动。

## 2. 可观测性
- [通过] 审计日志：`handler: 彻底删除已销毁链接 link=<id> slug=<slug> cause=per-link|env`，可按 cause 区分逐条与全局开关触发。
- [通过] 指标：复用 `linkshort_burn_links_purged_total`。
- [通过] 演练脚本日志：`[drill]` 前缀逐步输出，FAIL 时定位到具体步骤。

## 3. 数据
- [通过] purge 删除含 visits 级联。
- [通过] 敏感数据：无新增；purge 删的是访问日志，符合"彻底删除"语义。
- [通过] 配置环境变量化：无新增环境变量，逐条 purge 走 API 字段。

## 4. 部署运维
- [通过] 一键演练：`make drill`，脚本 `scripts/backup-drill.sh`，用法 `backup-drill.sh [--addr 127.0.0.1:PORT] [--keep] [--timeout N]`；退出码 0 通过 / 2 参数或依赖缺失 / 其他非零为某步 FAIL；全程 mktemp 隔离工作区不碰生产 data/ 与 backups/。
- [通过] 运维文档：OPERATIONS.md 新增 3.9 节。
- [通过] 真实演练通过（2026-10-16）：
  ```
  [drill] 演练前快照: links=2 visits=5 clicks=5
  [drill] 备份文件: .../backups/linkshort-20261016-104120.db
  [drill] 一致性校验...
  [drill] PASS
  ```

## 5. 安全
- [通过] 输入校验：`purge=true` 仅 burn 有效，非 burn 链传 `purge=true` 返回 400（防误传）；PATCH 校验同样生效。
- [通过] 鉴权沿用 API Key（`X-API-Key` 头或 `?key=` 参数）。

## 6. 可维护性
- [通过] 文档同步：CHANGELOG、README、OPERATIONS 本轮全部更新。
- [通过] 技术债登记：v1.5 之前销毁的 burn 链没有 `burned_at`，定时清理仍跳过它们（v1.5 起已知）；PATCH 把 burn 设为 false 时若该链 `purge=true` 会 400，需先把 purge 设 false（严格校验，有意为之），两条均已记入 CHANGELOG 已知缺口。

## 7. 验收
- [通过] 真实服务冒烟（2026-10-16）：burn+purge 链 201（purge_after_burn=true）→ 302 → 再访 404；库里该行消失、其 visits 为 0；默认 burn 链 302 → 再访 410（软保留不变）；非 burn 链传 purge=true → 400。
- [通过] 演练 PASS。
- [通过] 测试命令：`go test ./... -race` 104 例全绿；`go vet`、`gofmt` 全洁。
- [通过] 发版结论：未通过项 0。
