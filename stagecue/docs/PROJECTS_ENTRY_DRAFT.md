# PROJECTS.md 的 stagecue 条目更新草稿

> 本文件只是草稿，用于更新仓库根 `PROJECTS.md` 中 stagecue 条目，未改动 PROJECTS.md 本体。

## 草稿文本

- stagecue「舞监台」v0.4.0（2026-10-16）：可观测性收尾——Logback 日志轮转（按天+50MB 切分，保留 14 天）+ Prometheus 告警规则 5 条 + docker-compose 资源限制（512M/1c）+ 发版对照报告；JUnit 52/52（新增 LogConfigTest 4 例、AlertRulesTest 4 例；真实冒烟：服务端启动约 10s，/api/show 5 条默认 cue、/readyz ready、/metrics 9 个 stagecue_ 指标、stagecue.log 正常落盘）。
