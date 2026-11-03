# PRODUCTION CHECKLIST REPORT v1.5

## 0. 结论先行

- [通过] 版本 v1.5「登录限流」里程碑于 2026-10-16 完成验收，`Cargo.toml` 从 1.4.0 升至 1.5.0。
- [通过] `cargo test` 实测 95/95 全过，`cargo clippy --all-targets -- -D warnings` 零警告，`cargo fmt --check` 通过。
- [通过] 真服务冒烟（127.0.0.1:18093）验证 429 契约、`Retry-After` 头与 JSON 体一致、非法配置 exit 2、探针豁免。
- [通过] 无 schema 变更，无新增依赖，沿用 v1.4 的可观测性与部署能力。
- [未通过] 分布式限流未实现：桶为单进程内存，多实例部署不共享，重启清零。
- [未通过] `POST /api/auth/register` 不限流，注册接口滥用不在本次范围。
- [不适用] 分布式限流、注册限流均不属本次 v1.5 范围，故不作通过性判定。

## 1. 版本信息与范围

- [通过] 版本为 v1.5「登录限流」里程碑，日期 2026-10-16，`Cargo.toml` 1.4.0 → 1.5.0。
- [通过] 范围为 `POST /api/auth/login` 加 IP + 账号双维度令牌桶限流；超限返回 429 + `Retry-After` 秒头 + JSON 体 `{"error": "登录尝试过于频繁，请 N 秒后重试", "retry_after": N}`。
- [通过] 环境变量 `MINIOS_LOGIN_RPS`（默认 `1`）、`MINIOS_LOGIN_BURST`（默认 `5`），非法值启动时 stderr 点名变量并 `exit(2)`（fail-fast）。
- [通过] `/api/health`、`/api/readyz`、`/metrics` 不限流。
- [通过] 前端 login.html 收到 429 显示"试得太频繁，N 秒后重试"实时倒计时，倒计时期间提交按钮 disabled。
- [通过] 无新增依赖。

## 2. 可靠性

- [通过] `cargo test` 实测 95/95 全过：lib 29（含新增 ratelimit 单元测试 14）、api_test 16、auth_test 8、failure_injection 11、isolation_test 5、metrics_test 4、ratelimit_test 8（新增）、share_test 6、upload_security_test 8。
- [通过] ratelimit_test 8 例覆盖正常登录放行、超限 429（`Retry-After` 头与 JSON 体一致、retry_after ≥ 1）、并发对冲验证窗口恢复、IP 与账号双维度独立、探针 10 连击全 200 豁免、非法配置子进程 exit 非 0 且 stderr 点名变量、10 并发恰好 burst 个放行其余 429、非法 JSON 体放行不 429。
- [通过] 并发对冲验证窗口恢复采用时序裕量设计：rps=0.1 即 10s/token，恢复等待 12s。
- [通过] IP 与账号双维度独立以 X-Forwarded-For 切换验证。
- [通过] 真服务冒烟（127.0.0.1:18093，`MINIOS_LOGIN_BURST=2 MINIOS_LOGIN_RPS=0.01`）：注册 200 → 前 2 次登录 401 → 第 3 次起 429，响应头 `retry-after: 92` 与 JSON `{"error":"登录尝试过于频繁，请 92 秒后重试","retry_after":92}` 一致。
- [通过] `MINIOS_LOGIN_RPS=abc` 启动 → exit 2，stderr `配置错误：MINIOS_LOGIN_RPS 非法：'abc'，期望大于 0 的数字`。
- [通过] `/api/health` 连续 3 次 200（探针不限流）。
- [通过] 沿用项：JSONL 日志与 request_id、/metrics、健康/就绪、优雅关闭、docker-compose、backup/restore CLI 与脚本。
- [不适用] 分布式限流一致性不属本次范围，故不作通过性判定。

## 3. 可观测性

- [通过] 沿用 JSONL 日志 + request_id。
- [通过] 新增 `auth_ops_total{op="login_ratelimited"}` 计数器，op 维度既有 register/login/logout/migrate_legacy/share_create。
- [通过] `/metrics` 不限流。
- [通过] 沿用项：JSONL 日志与 request_id、/metrics、健康/就绪、优雅关闭、docker-compose、backup/restore CLI 与脚本。

## 4. 数据与状态

- [通过] 无 schema 变更。
- [通过] 限流桶为进程内存（`Mutex<HashMap>`，条目 idle 超 `max(300s, 10*burst/rps)` 且总量超 4096 时惰性清理）。
- [通过] 重启后桶清零。
- [未通过] 桶为单进程内存，多实例部署不共享，重启清零，未做分布式限流。
- [不适用] 分布式限流数据一致性不属本次范围，故不作通过性判定。

## 5. 部署与运维

- [通过] `docs/OPERATIONS.md` 新增 `## 9 登录限流调参`（两个旋钮、双维度、调参建议、反向代理 X-Forwarded-For 透传要求、429 契约、监控排障、探针豁免）与 §2 表格两行。
- [通过] `.env.example` 新增 `MINIOS_LOGIN_RPS=1` / `MINIOS_LOGIN_BURST=5` 注释行。
- [通过] 非法配置 fail-fast（exit 2）。
- [通过] 沿用项：JSONL 日志与 request_id、/metrics、健康/就绪、优雅关闭、docker-compose、backup/restore CLI 与脚本。
- [未通过] IP 取 `X-Forwarded-For` 首项是标准做法，客户端可伪造，反向代理后必须透传真实 XFF 否则多客户端共用 `"unknown"` 桶互相牵连。

## 6. 安全与健壮性

- [通过] 登录暴力破解/撞库防护：IP 桶防单 IP 扫号、账号桶防单账号被集火。
- [通过] 429 不泄露账号是否存在（限流在密码校验之前）。
- [通过] 非法配置 fail-fast（exit 2）。
- [通过] 探针豁免：`/api/health`、`/api/readyz`、`/metrics` 不限流。
- [未通过] `POST /api/auth/register` 不限流，注册接口滥用不在本次范围。
- [未通过] 密码强度策略、2FA 等仍是 v1.3 已知限制延续。
- [不适用] 注册限流、密码强度策略、2FA 均不属本次 v1.5 范围，故不作通过性判定。

## 7. 可维护性

- [通过] `cargo clippy --all-targets -- -D warnings` 零警告。
- [通过] `cargo fmt --check` 通过。
- [通过] `cargo test` 实测 95/95 全过。
- [通过] 无新增依赖。
- [通过] 沿用项：JSONL 日志与 request_id、/metrics、健康/就绪、优雅关闭、docker-compose、backup/restore CLI 与脚本。
- [未通过] 桶为单进程内存，多实例部署不共享，重启清零，未做分布式限流。

## 8. 发版结论

- [通过] v1.5「登录限流」里程碑于 2026-10-16 验收通过。
- [通过] `cargo test` 实测 95/95 全过，`cargo clippy --all-targets -- -D warnings` 零警告，`cargo fmt --check` 通过。
- [通过] 真服务冒烟验证 429 契约、`Retry-After` 头与 JSON 体一致、非法配置 exit 2、探针豁免。
- [未通过] 已知限制①：桶是单进程内存，多实例部署不共享，重启清零，未做分布式限流。
- [未通过] 已知限制②：`POST /api/auth/register` 不限流（注册接口滥用不在本次范围）。
- [未通过] 已知限制③：IP 取 `X-Forwarded-For` 首项是标准做法，客户端可伪造，反向代理后必须透传真实 XFF 否则多客户端共用 `"unknown"` 桶互相牵连。
- [未通过] 已知限制④：密码强度策略、2FA 等仍是 v1.3 已知限制延续。

## 9. 视觉验收（2026-10-16，真服务 + 截图，亲眼检查）

- [通过] `docs/screenshots/v15-login-normal.png`：正常登录页（"登录你的桌面"，无错误条，布局/配色沿用既有体系）。
- [通过] `docs/screenshots/v15-login-ratelimited.png`：限流态（红色 `.err` 条显示"试得太频繁，74 秒后重试"，登录按钮 disabled 置灰，布局无错位）。
- [通过] 检查项：布局撑满视口、无异常空白、无错位重叠。
- [通过] 检查项：文案为大白话、无 AI 味话术。
- [通过] 检查项：复用既有 `.err` 样式与按钮 disabled 态，未引入新配色/渐变/emoji。
