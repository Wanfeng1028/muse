# FeedFlow v1.11.0 发版对照报告

版本：v1.11.0 | 日期：2026-10-25 | 改动：登录失败锁定（feedflow/login_lockout.py 新模块 + auth/config/__init__ 接线 + tests/test_auth_lockout.py 9 例 + CHANGELOG/OPERATIONS/.env.example 文档）。

## 验收结果表

| 验收项 | 结果 | 详情 |
| :--- | :--- | :--- |
| 全量 pytest | 通过 | 971/971 通过（359.8 秒，0 失败） |
| ruff check | 通过 | 全洁 |
| 真实服务冒烟 | 通过 | 18399 端口：healthz 200、GET /login 200、错密码 2 次 200 + “密码不正确”、第 3 次 429 + Retry-After 900 + “尝试次数过多，请稍后再试”、锁定中正确密码仍 429、锁定中 GET / 为 302 |

## 对照表

| 生产清单领域 | 状态 | 理由 |
| :--- | :--- | :--- |
| 可靠性 | 通过 | 登录失败锁定逻辑生效且环境变量非法值启动 fail-fast 保障确定性。 |
| 可观测性 | 未通过 | 锁定事件没有 Prometheus 指标（未新增计数器），下一轮评估加指标。 |
| 数据与状态 | 通过 | 密码只存 werkzeug 哈希、锁定计数不落盘、配置与密钥分离且启动校验、备份恢复机制既有；数据库迁移子项因本版无 schema 变更而不适用。 |
| 部署与运维 | 通过 | Docker Compose 与运维手册既有，.env.example 已补充新增环境变量 FEEDFLOW_AUTH_MAX_ATTEMPTS / FEEDFLOW_AUTH_LOCK_MINUTES / FEEDFLOW_AUTH_WINDOW_MINUTES 配置说明。 |
| 安全与健壮性 | 未通过 | 仍为单用户单密码，无多用户、无登录失败以外的多因素（单用户设计，文档已声明）。 |
| 可维护性 | 通过 | 代码规范全洁，新增独立模块与 9 例测试，登录页模板复用既有错误文案无需新截图。 |

## 已知限制清单

1. 锁定事件没有 Prometheus 指标（未新增计数器）。
2. 锁定计数只存内存，进程重启清零，单进程有效，反代后同 IP 共享计数。
3. 仍为单用户单密码，无多用户、无登录失败以外的多因素。
4. pyproject.toml 的 version 字段仍为 0.1.0，与 CHANGELOG 版本号不一致，这是自早期起的既有遗留，本版未动。

## 结论

本版可发版，缺口均已文档化。
