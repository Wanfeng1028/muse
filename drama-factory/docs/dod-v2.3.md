# v2.3 发版对照报告（DoD）

对照仓库统一的 `PRODUCTION_CHECKLIST.md` 7 大类逐条核对。结论用 [通过] / [未通过] / [不适用] 标注。

## 1. 可观测性

- [通过] 结构化日志 + request_id 全链路（v2.2 沿用，v2.3 的 LlmScriptService 日志同样带 request_id）。
- [通过] 响应新增 `source`（ai / template / template-fallback）、`model`、`latencyMs` 字段，前端展示来源、模型、场数、耗时。
- [通过] 降级事件可在日志中定位（抛 LlmScriptUnavailableException → 捕获 → 记录降级原因）。

## 2. 容错与稳定性

- [通过] LlmScriptService 指数退避重试，`max-retries` 可配（默认 2）。
- [通过] 失败降级策略显式：任何失败 → LlmScriptUnavailableException → ScriptService 降级模板（source=template-fallback），产线不停。
- [通过] `mode=template` 可强制走模板，绕过 AI 调用。
- [通过] 传输策略：HTTP 主用 + CLI 回退。`LlmTransport` 无有效代理环境变量时直连（普通部署正确行为）；`callModel` 在 HTTP 抛 RuntimeException 且 CLI 可用时改调 `chat.py`（`drama.script.llm.cli-path`，为空则按 `$HOME`/`user.home` 自动探测 skill 路径；显式配置但不可执行则启动 fail-fast）。
- [通过] Resilience4j 熔断限流（视频提交，v2.2 沿用）。
- [通过] 提交幂等（v2.2 沿用）。
- [通过] 优雅关闭（v2.2 沿用）。

## 3. 配置管理

- [通过] `drama.script.llm.*` 全部环境变量化：`enabled` / `model` / `max-tokens` / `timeout-seconds` / `max-retries` / `cli-path`（`DRAMA_SCRIPT_LLM_CLI_PATH`）。
- [通过] 启动时校验配置，非法值直接 fail-fast，不带病启动；CLI 回退路径在启动时一次性解析并打日志（"AI 剧本传输策略: HTTP 主用，CLI 回退可用(…)"）。

## 4. 数据与迁移

- [通过] Flyway 版本化迁移（v2.2 沿用，v2.3 无新增 schema 变更）。

## 5. 接口契约与错误处理

- [通过] `IllegalArgumentException` 统一映射为 HTTP 400。
- [通过] 非法 `mode` 值有专门单测覆盖（ScriptServiceAiFallbackTest）。
- [通过] 剧集不存在场景有单测覆盖。

## 6. 测试覆盖

- [通过] 新增 12 个单测：
  - `LlmScriptServiceTest`（8 例）：纯 JSON、```json 围栏、前后废话容错、非法 JSON、场次不足、未启用、重试成功、重试耗尽。
  - `ScriptServiceAiFallbackTest`（4 例）：降级、模板直走、非法 mode、剧集不存在。
- [未通过] 剧本生成无失败注入测试（fault injection）。排期：v2.4 补。
- [通过] 真实 DeepSeek 调用已在 2026-10-13 冒烟中实测：`POST /api/episodes/1/generate-script?mode=ai` 返回 `source=ai, model=Deepseek-v4-flash, scenes=4, latency≈14s`，4 场剧本（暴雨街头→废弃仓库→警局审讯室→地下停车场，人物/道具线连贯）成功解析落库。调用路径为 CLI 回退（本沙箱限制 Java 进程 TCP 出站，HTTP 主用失败后自动切 chat.py；日志有 "CLI 回退调用成功" + "AI 剧本生成成功" 两条可观测记录）。

## 7. 部署与运维

- [通过] Docker Compose 一键部署（v2.2 沿用）。
- [通过] 前端三按钮（AI 生成剧本 / 模板生成 / 查看剧本）+ 额度提示 + 来源展示已接入，无新视觉语言引入。
- [通过] 「查看剧本」modal：生成成功后自动打开，可随时查看本集 4 场剧本正文（场号/地点/时间/画面/对白）。
- [通过] 附带修复既有 bug：`bootstrap.Modal`/`bootstrap.Toast` 在全站从未存在（tabler.min.js 导出的是 `tabler.Modal`/`tabler.Toast`），"从剧本生成分镜" modal 与 chat 页 toast 的打开/关闭调用一直静默失败，已全量改为 `tabler.*` 并经 CDP 真实点击验证。

## 已知限制（诚实记录）

- [未通过] AI 生成无专门限流，沿用全局限流。排期：v2.4 加 `scriptSubmit` 限流。
- [不适用] 多用户 / tenant 隔离——单用户自托管定位，不在本期范围。

## 发版结论

**发版（v2.3）。**

本轮已验证：
- AI 编剧链路端到端接通（服务、配置、降级、可观测、前端）。
- **真实 DeepSeek 调用冒烟实测通过**（2026-10-13）：ai 模式返回 source=ai 的 4 场连贯剧本，经 CLI 回退路径，全链路日志可观测。
- 12 个新单测全绿，全量 38/38 BUILD SUCCESS。
- 配置环境变量化 + 启动 fail-fast 生效；传输策略（HTTP 主用 + CLI 回退）日志可查。
- 视觉验收亲眼通过：三按钮行、「查看剧本」modal（真实 4 场剧本渲染）、额度提示；顺带修了全站 `bootstrap.*` 误用既有 bug。

遗留项（需排期跟进）：
1. `scriptSubmit` 专门限流 —— v2.4。
2. 剧本生成失败注入测试 —— v2.4。

以上两项不阻塞 v2.3 发布，但必须在 v2.4 前闭环。
