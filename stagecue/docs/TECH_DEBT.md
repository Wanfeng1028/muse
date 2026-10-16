# StageCue 技术债

> 每轮发版前更新；还清一项就删一项，不许留僵尸条目。

## v0.3.0 已偿还
- WS/HTTP 限流：IP 令牌桶（STAGECUE_RATE_LIMIT_RPS/BURST 环境变量，超限 429 + Retry-After）
- 超时/熔断：WS 广播背压——每客户端有界队列 + DROP_OLDEST 丢弃最旧 + stagecue_ws_broadcast_dropped_total 可观测；请求超时由 Ktor CIO 引擎与 WS ping 超时（30s）覆盖
- 新增 GET /readyz 就绪探针；探针（/healthz、/readyz、/metrics）免限流

## v0.2.0 已偿还
- SQLite + Flyway 版本化迁移（原 JSON 文件存储，无迁移机制）
- /metrics 指标缺失
- 备份恢复未实测
- 启动配置无校验
- 排练模式 UI 占位
- 音频仅 WAV

## 剩余债务

| # | 债务 | 现状 / 影响 | 计划 |
|---|------|-------------|------|
| 2 | 依赖更新机制 | 无 Dependabot | 跟仓库统一配（仓库级事项） |
| 3 | 告警规则 | 无 | 基于 /metrics 配 Prometheus rule 示例（cue 触发失败率、WS 断开突增） |
| 4 | 日志轮转 / 资源限制 | Logback 无滚动策略；docker-compose 无 memory limit | v0.3 补 |
| 5 | 滚动更新 / 零停机 | 单机应用，停机更新 | 声明为可接受限制（演出前窗口更新） |
| 6 | 多人同时编辑同一份 show | 未支持（单导演假设） | 二期 |
| 7 | 服务端引擎为 CIO 非 Netty | Ktor Netty 在本 VM 误用 KQueue 启动失败；CI/生产环境可用 Netty | 保留 CIO 为默认，配置项可切 |
| 8 | 桌面 UI 运行时截图未验收 | VM 缺 libXtst.so.6 系统库，Compose Desktop 无法启动；代码已全量编译通过 | 有 GUI 环境后补 |
| 9 | 移动端返听屏 / 灯光台 | 二期 | 协议已留 ClientRole.MONITOR/LIGHTING |
| 10 | 音频格式 | WAV/MP3 已支持 | FLAC/OGG 按用户需求再定 |
