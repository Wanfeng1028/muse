# 降级策略（DEGRADATION）

本文列出各子系统在故障时的降级行为、用户可见提示，以及对应代码位置。
规则：**每个降级行为都必须能在代码里找到实现。找不到实现的，如实写"当前无降级"。**

## 降级策略矩阵

| 子系统 | 故障场景 | 降级行为 | 用户可见提示 | 对应代码位置 |
|---|---|---|---|---|
| AI 编剧 | LLM 不可用 / 超时 | 回退到模板生成器；可用 `?mode=ai/template` 指定；响应带 `source` 字段标识来源 | 响应里 `source` 表明是 `template` 而非 AI | `com.dramafactory.service.LlmScriptService`（v2.3） |
| 视频 provider | 熔断打开 / 调用超时 / 连续失败 | Resilience4j CircuitBreaker + 指数退避重试（max-attempts=8）；任务状态机保持可重试 | 任务停留在可重试状态，重试次数耗尽后报错 | `com.dramafactory.service.video`（mock/agnes 双实现 + CircuitBreaker，v2.2） |
| ffmpeg 相关 | ffmpeg 缺失 / 执行失败 | **当前无降级**：`FfmpegException`（RuntimeException）直接抛给上层，按 500 报错 | "无法启动命令: …" 等错误信息 | `com.dramafactory.service.FfmpegService.FfmpegException` |
| auth-service 代理 | auth-service 不可达 / 超时 | **当前无降级**：连接超时 5s、请求超时 15s，失败返回 502 `{"code":"AUTH_UPSTREAM_UNAVAILABLE","message":"账号服务暂时不可用"}` | 502 + "账号服务暂时不可用" | `com.dramafactory.controller.AuthProxyController`（upstreamUnavailable） |
| H2 文件库 | 文件损坏 / 打不开 | 启动时 Flyway + Hibernate 双重校验（`ddl-auto: validate`）；异常则启动失败，恢复走备份流程 | 启动失败日志；恢复按运维手册 | `docs/OPERATIONS.md` 备份/恢复章节；`scripts/restore.sh` |
| 鉴权（开放模式） | `AUTH_JWT_SECRET` 为空 | 进入开放模式，功能可用但**无多用户隔离**（所有资源按 `local` owner 归属） | 启动 warn | `com.dramafactory.config.JwtAuthFilter`；`com.dramafactory.config.CurrentUser` |

## 分项说明

### AI 编剧（已实现降级）
LLM 调用失败时不直接报错，回退到模板生成器。`?mode=ai/template` 可显式选择，响应 `source` 字段区分来源。代码：`LlmScriptService`。

### 视频 provider（已实现降级）
`service/video` 下 provider 有 mock/agnes 两个实现。熔断与重试由 Resilience4j 提供：CircuitBreaker 防雪崩，指数退避重试 max-attempts=8。重试耗尽后任务报错，但状态机保留可重试性。

### ffmpeg（当前无降级，按异常报错）
`FfmpegService.run()` 里 `pb.start()` 的 IOException 包成 `FfmpegException("无法启动命令: " + cmd)` 抛出；超时则中断并抛异常。没有备用剪辑路径——ffmpeg 是成片管线的硬依赖，缺失时相关接口直接 500，靠部署时 Dockerfile 预装保证（compose/Dockerfile 均已装 ffmpeg）。

### auth-service 代理（当前无降级，按 502 透传）
`AuthProxyController` 用 `java.net.http.HttpClient`：connectTimeout 5 秒、单请求 timeout 15 秒。auth-service 不可达/超时/返回异常时，统一走 `upstreamUnavailable()` 返回 502 `{"code":"AUTH_UPSTREAM_UNAVAILABLE","message":"账号服务暂时不可用"}`。登录/刷新等鉴权链路因此是强依赖，auth-service 挂了就登不上——这是已知限制，不藏着。

### H2 文件库
启动时 Flyway migrate + Hibernate `validate` 双重校验，schema 对不上直接启动失败（fail-fast，不带病运行）。数据损坏恢复走 `docs/OPERATIONS.md` 的备份恢复流程（`scripts/backup.sh` / `scripts/restore.sh`，v2.4 已真实跑通）。

### 开放模式（无 JWT secret）
`JwtAuthFilter` 在 `AUTH_JWT_SECRET` 为空时开放所有请求（启动 warn）。此时功能可用，但没有多用户隔离，所有资源按 `local` owner 归属（v2.6 起由 `CurrentUser` 统一回退）。生产环境必须设置该变量。
