# 生产就绪检查报告 v1.8

## 0. 结论先行

这版能上生产。范围就一件事：分享读限流 v1.8 重设计。Cargo 版本 1.7.0 → 1.8.0，没夹带别的功能。

数字汇总：

- `cargo test` 151/151 全过。
- `cargo clippy --all-targets -- -D warnings` 零警告。
- `cargo fmt --check` 通过。
- 依赖零新增。
- 真服务冒烟 14/14 通过（127.0.0.1:18101，MINIOS_SHARE_RPS=1 / MINIOS_SHARE_BURST=3）。
- 截图 2 张亲眼验收。

未通过条目：

- ① Dependabot 依赖更新——未通过。等仓库根迁入 `.github/` 时统一配，需要 gh token 补 workflow 权限，是用户侧待办。
- ② v1.5 遗留：分布式限流、注册限流、密码策略、2FA——这版没动，继续挂。

已知限制：

- 限流桶是单进程内存桶：多实例不共享配额，重启清零。
- NAT/出口 IP 下多用户共享同一 IP 桶会被误伤，调大 BURST 或透传 X-Forwarded-For 缓解。
- 旧变量 `MINIOS_SHARE_READ_RPM` / `MINIOS_SHARE_READ_BURST` 一旦被设置就拒绝启动，这是有意的 fail-fast，不是静默忽略，运维升级时要删掉。

## 1. 版本信息与范围

- 版本：Cargo.toml `1.7.0` → `1.8.0`。
- 无 DB 迁移。
- 依赖零新增。
- 4 个破坏性变更点：
  1. 环境变量改名并废弃旧变量：新增 `MINIOS_SHARE_RPS`（默认 5）、`MINIOS_SHARE_BURST`（默认 30）、`MINIOS_SHARE_RATE_LIMIT_ENABLED`（默认 true）；旧变量 `MINIOS_SHARE_READ_RPM` / `MINIOS_SHARE_READ_BURST` 只要被设置就启动失败。
  2. 限流维度从 token+IP 双维度改成 IP 单维度。
  3. 指标迁移：`auth_ops_total{op="share_ratelimited"}` 移除，改用 `minios_share_rate_limited_total`。
  4. 429 契约不变（与 v1.7 逐字一致），前端 UX 沿用 v1.5 登录限流体系。
- 前端改动点：share.html 两处 fetch（初始 `/api/s/:token`、目录浏览 `/api/share/list`）加 429 分支。

## 2. 可靠性

[通过] 测试总数与明细：151/151 全过——lib 52、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、metrics_test 4、metrics_v16_test 5、ratelimit_test 8、rbac_test 8、share_dir_test 12、share_ratelimit_test 8（v1.8 重写）、share_test 6、upload_security_test 8。

[通过] fail-fast 行为：非法 env（解析失败、rps ≤ 0/NaN/无穷大、burst 非整数或 0、非法布尔）启动时 stderr 点名变量并 `exit(2)`；旧变量被设置同样 `exit(2)` 并提示改用新变量。纯函数有单测覆盖。

[通过] 总开关 `MINIOS_SHARE_RATE_LIMIT_ENABLED=false` 有集成测试覆盖：分享读请求直接放行，不计数不记桶。

[通过] 健康检查沿用 v1.7 行为，探针不受限流影响。

## 3. 可观测性

[通过] 新 counter `minios_share_rate_limited_total`，HELP 文案 "Total number of share read requests rejected by rate limiting."，TYPE counter，样本行格式标准 Prometheus 文本格式。

[通过] 429 契约与 v1.7 逐字一致：状态码 429、响应头 `Retry-After: <整数秒>`、JSON 体 `{"error": "分享访问过于频繁，请 <N> 秒后重试", "retry_after": <N>}`。

[通过] request_id 日志沿用，排障时可按 request_id 串联。

## 4. 数据与状态

[不适用] 无 DB 迁移，无 schema 改动。

[通过] token 生成沿用 v1.7：32 字节 hex。

[通过] 多用户隔离沿用，isolation_test 5 项全过。

## 5. 部署与运维

[通过] OPERATIONS.md 新增 §10 分享读限流调参，含三个旋钮、IP 单维度语义、调参建议表、429 契约与前端、监控、已知限制。

[通过] 升级注意已写进文档：旧变量必须删掉，否则服务起不来，这是有意的 fail-fast。

[通过] 滚动更新限制沿用（单进程 SQLite），本版没改这部分。

## 6. 安全与健壮性

[通过] 三条公开读路由覆盖：`GET /api/s/:token`、`/api/s/:token/download`、`GET /api/share/list`。

[通过] 探针豁免验证：冒烟测试里限流期间 `/api/health`、`/api/readyz`、`/metrics` 均为 200；集成测试同样覆盖。

[通过] XFF 透传要求已写进 OPERATIONS §10.2：反代后必须透传 `X-Forwarded-For`。

[未通过] Dependabot 依赖更新——未通过。等仓库根迁入 `.github/` 时统一配，需要 gh token 补 workflow 权限，用户侧待办。

## 7. 可维护性

[通过] `ShareReadKey` / `ShareReadLimiter` 独立模块边界，与登录限流类型隔离、状态隔离。

[通过] API 契约稳定：429 响应结构与 v1.7 逐字一致。

[通过] CHANGELOG 新增 [1.8.0] 条目。

[通过] 文档代码同步：OPERATIONS §10、CHANGELOG [1.8.0]、Cargo 版本 1.8.0、两张截图齐全。

## 8. 发版结论

通过汇总：

- 测试 151/151。
- clippy 零警告。
- fmt 通过。
- 依赖零新增。
- 冒烟 14/14。
- 截图 2 张亲眼验收。
- 文档同步完成。

未通过清单（带排期）：

- ① Dependabot 依赖更新——等仓库根迁入 `.github/` 时统一配，需要 gh token 补 workflow 权限（用户侧待办，无明确排期）。
- ② v1.5 遗留（分布式限流、注册限流、密码策略、2FA）——这版没动，继续挂。

已知限制：

- 单进程内存桶，多实例不共享、重启清零。
- NAT/出口 IP 下多用户共享 IP 桶会被误伤，调大 BURST 或透传 X-Forwarded-For 缓解。
- 旧变量废弃是 fail-fast 不是静默，运维升级时必须删掉旧变量。

结论：可以发。

## 9. 视觉验收

[通过] `docs/screenshots/v18-share-normal.png`：文件分享正常态，文件名、大小、下载按钮齐全，深色主题。

[通过] `docs/screenshots/v18-share-ratelimited.png`：429 态，显示「看的人有点多」+ 实时倒计时 + 置灰 disabled 重试按钮。

[通过] 布局：两张截图布局正确，无错位。

[通过] 数据真实：文件名、大小、倒计时数字都是真实运行态数据，不是占位符。

[通过] 文案无 AI 味：大白话，无四字 polished 短语。

[通过] 深色一致：两张截图深色主题 token 一致，无风格断裂。

[通过] 倒计时 + disabled 状态正确：429 截图里倒计时在走，重试按钮是 disabled 状态。
