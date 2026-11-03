# 幕间 Interlude — 生产级对照报告（v1.1，2026-10-15）

> 对照标准：`~/workspace/muse-build/PRODUCTION_CHECKLIST.md`（用户亲定：不裁剪、全量大厂标准）。
> 每条结论：通过 / 未通过 / 不适用+理由。未通过项给出排期或明确声明为已知限制。
> 结论口径：凡本轮实测覆盖到的项，以本轮证据为准；v1 已通过且本轮未变动的项，标注"v1 结论延续"。

## v1.1 新增验证通过的事实

- **测试 28/28 全过**：单元 24 例（ParserTest / ValidatorTest / ExtractorTest / GraphLayoutTest）+ 端到端 4 例（EndToEndTest：示例剧本解析→5 条规则→问题报告全链路）。运行方式为 kotlinc 直编 + JUnit Platform Console（Gradle daemon 本机不可用，见"环境限制"）。
- **CLI 实测通过**：`interlude-lint lint sample.interlude --log-json` 输出 stdout 报告 5 个问题（UNINIT_VAR hall:13、DEAD_END orphan:37、UNREACHABLE orphan:37、DEAD_END deadend:40、UNREACHABLE deadend:40），stderr 为 JSON 行日志，含 timestamp / level / op / file / scenes / issues / errors / warnings / durationMs，退出码 1；`--log-level warn`、`--log-level debug` 实测通过；非法参数输出用法并退出码 2。
- **日志脱敏实测通过**：日志只含路径、scene id、行号、code、计数、耗时，不含剧本正文内容。
- **新增文件落地**：src/main/kotlin/com/interlude/log/Log.kt、src/main/kotlin/com/interlude/lint/Report.kt、src/main/kotlin/com/interlude/LintCli.kt、src/test/kotlin/com/interlude/EndToEndTest.kt、docs/OPS.md、CHANGELOG.md、.github/dependabot.yml。
- **本轮修复 3 个真 bug**：CLI 位置参数解析死循环（`else -> printUsageAndExit` 导致 `lint <文件>` 永远 exit 2）、测试用了不存在的 `assertContains(CharSequence)` 重载、测试期望顺序与 Validator 实际排序（severity,line）不符。三项均已修复并重测通过。
- **本轮未做**：.bak 自动备份（v1 报告曾排期 v1.1，但本轮 lane 范围限定 6 项，不含它）。

## 1. 可靠性

- 测试金字塔：**部分通过**。单元 24 例 + 端到端 4 例，合计 28/28 全过（v1.1 新增端到端，EndToEndTest 覆盖解析→校验→报告全链路）。失败注入测试缺失，**未通过—排期 v2**。
- 错误处理策略：**通过（v1 结论延续）**。解析器行号精确报错（Fail-fast，含行号/原因）；UI 解析失败展示错误条不崩溃；CLI 非法参数输出用法并退出码 2。重试/降级/幂等不适用（纯本地工具，无网络调用）。
- 数据库迁移：**不适用**（无数据库；剧本为纯文本文件）。
- 健康检查/优雅关闭：**不适用**（单机桌面应用）。

## 2. 可观测性

- 结构化日志：**通过**。新增 Log.kt 统一日志门面，CLI `--log-json` 实测输出 JSON 行日志，字段含 timestamp / level / op / file / scenes / issues / errors / warnings / durationMs；`--log-level warn|debug` 实测通过。
- 关键指标：**通过**。本地工具等价物为"校验耗时/问题数"，已随 JSON 日志落地（durationMs / issues / errors / warnings 实测有值）。
- 报错定位：**通过（v1 结论延续）**。Issue 含 sceneId + 行号，UI 问题列表点击定位到 DSL 行；本轮 CLI 实测问题均带行号（如 UNINIT_VAR hall:13）。
- 告警规则：**不适用**（无服务端）。日志告警等价物为退出码：有问题退出码 1、用法错误退出码 2，已实测。

## 3. 数据与状态

- 自动备份/恢复：**未通过—排期后续版本**。本轮 lane 范围限定 6 项，未含 .bak 自动备份；一键恢复流程未做。已在"已知技术债"记为后续版本偿还。
- 敏感数据处理：**通过**。不收集、不上传任何数据；本轮实测日志不含剧本正文内容（只含路径/scene id/行号/code/计数/耗时）。
- 配置与密钥分离：**通过（v1 结论延续）**。无密钥；无外部配置（零配置）。
- 多用户设计：**不适用**（单机单用户桌面工具；文件级天然隔离）。

## 4. 部署与运维

- 一键部署：**未通过—环境限制**。`build.gradle.kts` 配置完整（Kotlin 2.1.0 + Compose 1.7.3 + JUnit5），本沙箱 Gradle daemon 不可用；正常机器上 `./gradlew run` 即为一键运行。Docker 不适用（桌面 GUI 应用）。
- 滚动更新/零停机/资源限制/日志轮转/数据卷：**不适用**（单机桌面应用）。
- 运维手册：**通过**。新增 docs/OPS.md，覆盖构建、运行、常见问题排查。
- 桌面 UI 截图验收：**未通过—已知限制**。本沙箱无 GUI 构建环境，Compose 插件后端崩溃（前端语义分析零错误，崩溃在 JVM 后端 IR lowering），待正常环境 `./gradlew run` 后补截图，不虚报为已验收。

## 5. 安全与健壮性

- 输入校验：**通过（v1 结论延续）**。DSL 解析器对非法缩进/未知关键字/未闭合引号等全部报错到行号；恶意输入不导致静默错误（解析失败→Issue/错误条，无异常崩溃路径已由单测覆盖）。本轮 CLI 非法参数实测走用法+退出码 2。
- 依赖更新机制：**通过**。新增 .github/dependabot.yml 配置。
- 限流/超时/熔断：**不适用**（无网络）。

## 6. 可维护性

- 模块边界：**通过（v1 结论延续）**。dsl / lint / i18n / ui 四包单向依赖（ui→dsl/lint，无环）；本轮新增 log 包，依赖方向为 lint/cli→log，无环。
- CHANGELOG + 升级指南：**通过**。新增 CHANGELOG.md，随版本记录变更。
- 技术债记录：**通过**（见下"已知技术债"）。
- 代码与文档同步：**通过（v1 结论延续）**。README 的 DSL 示例与 Parser 实现一致；本轮新增 docs/OPS.md 与 CLI 实测行为一致。

## 7. 发版前对照报告

- **通过**。本报告即 v1.1 对照报告，存于 docs/ 并记入 PROJECTS.md；每条给出通过/未通过/不适用结论，未通过项均有排期或已知限制声明。

## 8. 周期机制

- 技术债清理轮：**通过**。本轮即一次技术债清理轮：补端到端测试、结构化日志、运维手册、CHANGELOG、Dependabot，并修复 3 个真 bug（CLI 位置参数死循环、测试断言重载错误、测试期望排序不符）。
- 真实负载验证：**未通过—已知限制**。本轮仅用示例剧本（9 场景）跑通，未用接近真实数据量/并发验证；桌面单机工具，排期后续版本用大剧本压测。
- 故障演练抽查：**未通过—排期 v2**。本轮未做杀进程/断网/磁盘满演练；无网络组件，演练范围限定为进程被杀后的恢复与 .bak 恢复，随 .bak 功能一并排期 v2。

## 环境限制（诚实声明）

1. **Gradle daemon 在本沙箱不可用**（2026-10-13 与 2026-10-15 多次验证：daemon 能启动但客户端 dispatch 后即 "Could not receive a message from the daemon"；回环 TCP 正常，非 OOM）。构建与测试改用 kotlinc 直编 + JUnit Platform Console 验证。`build.gradle.kts` 保留正确配置，供真实机器使用。
2. **Compose UI 在本沙箱无法编译为可运行二进制**：手动组装 kotlinc 2.1.0 + compose-compiler-plugin 2.1.0 时，插件在 JVM 后端 IR lowering 阶段崩溃（连最简 `@Composable fun Hello()` 都崩；属手工拼装编译器环境缺失组件，非项目代码问题——前端语义分析零错误）。因此桌面 UI 未做截图视觉验收，不伪造截图。
3. **Maven 在本沙箱不可用**（代理认证失败），Compose 依赖改用 curl 从 Maven Central 直拉 jar（共 18 个）完成前端验证。

## 已知技术债

| 位置 | 影响 | 偿还计划 |
|---|---|---|
| 无集成/端到端测试 | 回归风险 | 已偿还（v1.1，EndToEndTest 4 例，28/28 全过） |
| 无结构化日志 | 问题排查靠肉眼 | 已偿还（v1.1，Log.kt + --log-json 实测） |
| 无 Dependabot | 依赖过期无提醒 | 已偿还（v1.1，.github/dependabot.yml） |
| 无 .bak 自动备份 | 用户误操作丢改动 | 后续版本（本轮 lane 范围未含） |
| UI 未在沙箱截图验收 | 视觉风险未亲眼排除 | 在正常机器 `./gradlew run` 后补截图 |
| 无失败注入测试 | 关键路径健壮性未验证 | 排期 v2 |

## 结论

v1.1 在 v1 基础上补齐端到端测试、结构化日志、运维手册、CHANGELOG、Dependabot，并修复 3 个真 bug，测试 28/28 全过，CLI 与日志行为实测通过。UI 截图验收与 Gradle 一键部署受本沙箱环境限制未通过，.bak 自动备份与失败注入测试排期后续/v2——均如实声明，**不虚报为已验收**。以上未通过项均有排期或明确声明。
