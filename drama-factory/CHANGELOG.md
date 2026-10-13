# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，
版本号使用项目内版本（`v2.x`）。

## [v2.4] - 2026-10-14

### Added
- 指标采集：接入 Micrometer + Prometheus，暴露 `GET /actuator/prometheus`（无鉴权，`JwtAuthFilter` 仅拦 `/api/**`）。
- 业务指标：新增 7 类业务指标——`dramafactory_video_tasks_queued`、`dramafactory_runs_by_status{status}`（8 个 `RunStatus` 小写标签）、`dramafactory_runs_waiting_approval`、`dramafactory_script_llm_calls_total{model,result}`、`dramafactory_script_llm_duration_seconds{model}`、`dramafactory_finalcut_builds_total{result}`、`dramafactory_finalcut_build_duration_seconds`。Gauge 由 `@Scheduled(30s)` 刷新内存快照，抓取时不打 DB。
- 告警：新增 `prometheus/rules/drama-factory.yml`，含 `DramaFactoryHighErrorRate`（critical）、`DramaFactoryVideoQueueBacklog`、`DramaFactoryApprovalStuck`、`DramaFactoryRunFailures`（warning）。
- 抓取配置：新增 `prometheus/prometheus.yml` 示例（job `drama-factory`，15s 间隔，指向 `localhost:8081/actuator/prometheus`）。
- 备份恢复：新增 `scripts/backup.sh`（H2 `BACKUP TO` 在线备份 + `media/`、`settings/` 归档 + manifest + 保留最近 7 个）与 `scripts/restore.sh`（运行检查 → sha256 校验 → 恢复前快照 → H2 `Restore` → media/settings 恢复 → 冒烟），均已真实跑通。
- 运维手册：新增 `docs/OPERATIONS.md`（部署/备份恢复/升级/日志轮转/监控告警/6 条故障排查/已知限制）。
- 测试：新增 `MetricsEndpointTest` 3 例。

### Docs
- 初建 `CHANGELOG.md`，回填 v2 至 v2.3 历史。
- 新增 `docs/dod-v2.4.md` 发版对照报告。

## [v2.3] - 历史版本

### Added
- AI 编剧引擎：接入 DeepSeek-V4-Flash 真实模型调用。

## [v2.2] - 历史版本

### Added
- 结构化日志输出。
- request_id 贯穿请求链路，便于按 ID 检索。
- 接入 Resilience4j 熔断与限流（单实例内存级）。
- 新增 Docker Compose 部署配置。

## [v2.1] - 历史版本

### Added
- 接入 Flyway 数据库迁移。
- 提交幂等支持。
- 优雅关闭。

## [v2] - 历史版本

### Added
- 短剧生产管线：分镜、视频任务状态机、ffmpeg 剪辑。
- 生产看板。
