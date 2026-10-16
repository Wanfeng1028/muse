# 降级策略（DEGRADATION_POLICY）

本文档是 drama-factory 的完整降级策略说明，覆盖各故障场景下的降级行为、重试与熔断参数、当前尚不具备降级能力的诚实清单、已知限制与演练建议。

- 适用范围：Java 21 + Spring Boot 的 AI 短剧 Harness。
- 阅读前提：本文所有类名、参数、端点、指标均取自现有实现，未做推测。
- 相关文档：`docs/DEGRADATION.md`（矩阵速查）、`docs/OPERATIONS.md`（备份恢复、生产部署约束）。

---

## 1. 降级矩阵

| 故障场景 | 降级行为 | 用户可见提示 | 恢复流程 | 对应代码 / 文档位置 |
| --- | --- | --- | --- | --- |
| LLM 不可用 / 超时 | `LlmScriptService` 回退到模板生成器；可用 `?mode=ai/template` 显式指定 | 响应 `source` 字段标识来源（`ai` / `template`），前端据此展示来源 | LLM 恢复后按 `mode` 语义自动回到 AI 路径；无需重启 | `LlmScriptService`（v2.3） |
| 视频 provider 限流 / 超时 / 抛异常（首选 agnes） | `VideoProviderRouter` 按优先级链 `agnes,qwen` 自动试下一通道；agnes 抛 `RateLimitedException` / 超时 / `RuntimeException` 时降级 | 任务详情 `provider` 字段显示实际生效通道；`GET /api/settings/effective-provider` 的 `lastFallback` 展示最近降级 | 首选通道恢复后，后续任务按优先级链重新优先选 agnes | `com.dramafactory.service.video.VideoProviderRouter`、`video_tasks.fallback_reason`（V13 迁移） |
| 视频 provider 限流 / 超时 / 抛异常（首选 qwen） | 优先级链为 `qwen,agnes`，qwen 失败时自动试 agnes | 同上 | 同上 | 同上 |
| 视频 provider 为 mock | 仅本地模拟，不参与降级链 | 无降级提示 | 不适用 | 同上 |
| ffmpeg 执行失败——瞬时 | FinalCutService（concat / burn-subtitles / probe-duration）瞬时失败最多重试 3 次，退避 2s / 4s；VideoTaskService 瞬时失败走 8 次指数退避（10s / 20s / 40s … 封顶 10min） | 任务进入重试，前端可见状态流转；重试耗尽后任务 FAILED | 重试成功后任务继续；重试耗尽可走 retry 接口手动重试 | `FfmpegService.FfmpegException#isTransient()`（超时 / 信号杀死 137/143 / OOM 为瞬时）；`FFMPEG_RETRY_ATTEMPTS` / `FFMPEG_RETRY_BACKOFF_MS` 可配 |
| ffmpeg 执行失败——永久 | 直接 FAILED，不重试 | 任务 FAILED | 需人工修复（补二进制 / 修参数）后走 retry 接口手动重试 | `FfmpegService.FfmpegException#isTransient()`（`无法启动命令`（二进制缺失）/ 参数编程错误为永久） |
| ffmpeg 缺失 | **无降级**（详见第 3 节） | 任务失败 | 修复部署（compose / Dockerfile 均预装 ffmpeg） | 同上 |
| auth-service 不可达 / 超时 | **无降级**，直接失败（详见第 3 节） | HTTP 502，`{"code":"AUTH_UPSTREAM_UNAVAILABLE","message":"账号服务暂时不可用"}` | auth-service 恢复后即可登录 | `AuthProxyController`，`java.net.http.HttpClient`，connectTimeout 5s / 单请求 timeout 15s |
| H2 文件损坏 | fail-fast：启动时 Flyway migrate + Hibernate `ddl-auto: validate` 双重校验，对不上直接启动失败 | 启动失败，进程退出 | 走 `docs/OPERATIONS.md` 备份恢复流程（`scripts/backup.sh` / `scripts/restore.sh`，v2.4 真实跑通，12 张表可查） | Flyway + Hibernate validate；`docs/OPERATIONS.md` |
| 鉴权开放模式 | `AUTH_JWT_SECRET` 为空时 `JwtAuthFilter` 放行所有请求；所有资源按 `local` 归属（`CurrentUser` 回退） | 启动时 warn 日志 | 配置 `AUTH_JWT_SECRET` 后重启，恢复多用户隔离 | `JwtAuthFilter`、`CurrentUser` |
| 磁盘满 | **无任何处理，待实现**（详见第 3 节） | 无专门提示，表现为底层写失败 | 待实现（当前需人工清理磁盘） | 待实现 |

---

## 2. 重试 / 幂等 / 熔断参数表

| 组件 | 策略 | 参数（次数 / 退避 / 超时） | 耗尽后行为 |
| --- | --- | --- | --- |
| 视频 provider 路由（`VideoProviderRouter`） | 优先级链降级 | 按 `drama.video.provider` 首选构建链（agnes→`agnes,qwen`；qwen→`qwen,agnes`） | 链内全部失败则任务失败 |
| 视频 provider 熔断 / 限流 | Resilience4j 熔断 + 限流 | **单实例内存级**（多实例不共享熔断窗口，见第 4 节） | 熔断打开期间走降级链或失败 |
| `VideoTaskService` 轮询 | 指数退避 | 最多 8 次，退避 10s / 20s / 40s … 封顶 10min | 任务 FAILED；状态机保留可重试性，可走 retry 接口手动重试 |
| `FinalCutService`（concat / burn-subtitles / probe-duration） | 瞬时失败重试 | 最多 3 次，退避 2s / 4s（`FFMPEG_RETRY_ATTEMPTS` / `FFMPEG_RETRY_BACKOFF_MS` 可配） | 仍失败则 FAILED |
| `VideoTaskService`（ffmpeg 瞬时失败） | 指数退避 | 8 次，退避 10s / 20s / 40s … 封顶 10min | 任务 FAILED，可手动重试 |
| `VideoTaskService`（ffmpeg 永久失败） | 不重试 | — | 直接 FAILED |
| `VideoTaskService#submit` | 提交幂等（v2.1 落地） | — | 重复提交被幂等处理 |
| `AuthProxyController` → auth-service | 无重试 / 无降级 | connectTimeout 5s，单请求 timeout 15s | 返回 502 `AUTH_UPSTREAM_UNAVAILABLE` |

---

## 3. "当前无降级"的诚实清单

以下场景当前**没有任何降级路径**，如实列出，不做美化。

1. **ffmpeg 缺失**
   - 现状：无备用剪辑路径，ffmpeg 是硬依赖。二进制缺失时 `FfmpegException#isTransient()` 归类为永久失败，直接 FAILED。
   - 缓解：compose / Dockerfile 均预装 ffmpeg。
   - 排期建议：评估引入纯 Java 剪辑兜底的可行性；短期内在启动自检中增加 ffmpeg 存在性检查并提前告警。

2. **auth-service 挂**
   - 现状：`AuthProxyController` 无降级，auth-service 挂了就登不上。
   - 排期建议：评估本地缓存 / 只读降级模式；至少在健康检查中暴露上游不可用状态，便于运维快速定位。

3. **磁盘满**
   - 现状：当前无任何处理，待实现。
   - 排期建议：在写入路径前置磁盘水位检查，达到阈值时拒绝新任务并给出明确提示；接入监控告警。

---

## 4. 已知限制

1. **熔断 / 限流为单实例内存级**：多实例部署不共享熔断窗口，各实例独立计数，集群整体故障判定不准确。若需集群级熔断，需引入共享存储（如 Redis）改造。
2. **开放模式无隔离**：`AUTH_JWT_SECRET` 为空时 `JwtAuthFilter` 放行所有请求，功能可用但无多用户隔离，所有资源按 `local` 归属。仅适用于本地 / 单用户场景，禁止用于多租户生产。
3. **生产部署约束**：prometheus 端点不得暴露公网，具体约束见 `docs/OPERATIONS.md`。

---

## 5. 演练建议

| 故障场景 | 演练要点 |
| --- | --- |
| LLM 不可用 / 超时 | 断开 LLM 上游网络或注入超时，调用剧本生成接口，确认响应 `source` 为 `template`；再用 `?mode=ai` / `?mode=template` 分别验证显式指定行为。 |
| 视频 provider 限流 / 超时 | 让首选 provider 返回 `RateLimitedException` 或注入超时，提交视频任务，检查任务详情 `provider` 字段切换到下一通道，并核对 `video_tasks.fallback_reason`、warn 日志、`GET /api/settings/effective-provider` 的 `lastFallback`。 |
| ffmpeg 瞬时失败 | 注入超时 / 模拟信号杀死（137 / 143）/ OOM，观察 FinalCutService 退避 2s / 4s 重试与 VideoTaskService 指数退避；核对 `dramafactory_ffmpeg_retries_total`、`dramafactory_video_poll_skipped_total` 指标。 |
| ffmpeg 永久失败 | 移除 ffmpeg 二进制或传入编程错误参数，确认 `isTransient()` 返回 false 且任务直接 FAILED，不重试。 |
| auth-service 不可达 | 停掉 auth-service 或断网，调用代理接口，确认返回 502 `AUTH_UPSTREAM_UNAVAILABLE`；再验证恢复后登录正常。 |
| H2 文件损坏 | 在测试环境破坏 H2 文件，重启应用，确认 fail-fast 启动失败；再走 `scripts/backup.sh` / `scripts/restore.sh` 恢复，核对 12 张表可查。 |
| 鉴权开放模式 | 清空 `AUTH_JWT_SECRET` 启动，确认 warn 日志出现、请求全部放行、资源归属 `local`；再配置密钥重启，确认隔离恢复。 |
| 磁盘满 | 在测试环境填满磁盘，提交任务，记录当前行为（预期为底层写失败，无专门提示）；为后续实现水位检查提供基线。 |
| 幂等 | 并发 / 重复调用 `VideoTaskService#submit`，确认只产生一个任务。 |

---

## 6. 与 docs/DEGRADATION.md 的关系

- `docs/DEGRADATION.md`（43 行）是**速查版**：以矩阵加分项说明的形式，快速回答"某场景降级到什么"。
- 本文档 `docs/DEGRADATION_POLICY.md` 是**完整策略版**：在速查版基础上补齐了重试 / 幂等 / 熔断参数、当前无降级的诚实清单、已知限制、演练建议与文档关系说明，是 DoD 第 5 轮要求的正式《降级策略》文档。
- 两份文档**并存，不互相替代**：速查版用于日常快速查阅，策略版用于评审、排期与演练。策略版更新时需同步检查速查版是否仍然一致。
- 本文档**不删除、不覆盖** `docs/DEGRADATION.md`。
</｜DSML｜ parameter>
</｜DSML｜ invoke>
</｜DSML｜ calls>