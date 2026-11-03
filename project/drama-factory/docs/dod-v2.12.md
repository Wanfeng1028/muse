# DoD v2.12 — 分支覆盖攻坚 + 门禁修复（第 11 轮）

- 里程碑：v2.12（对应 docs/dod-v2.11.md 中 v2.12 排期：分支覆盖冲 70%）
- 时间：2026-10-14；编排：cron muse-dpsk-daily-build
- 结论：**70% 目标未达成（68.7%，差 1.3pp），但修复了构建门禁变红事故**；测试 636/636 全过；BUILD SUCCESS；门禁棘轮上调并锁定。

## 背景：基线漂移事故（本轮关键发现）

v2.11 结束时记录分支 67.3%（1266/1882）。本轮开工实测发现 bundle 已跌至 **63.3%/76.6%，门禁（行 0.78/分支 0.65）变红、构建失败**。

根因：v2.11 之后合入的 **BYOK 提交（62e6b27，图片/音乐/数字人真实生成 v1.0）新增约 442 个分支**（byok 包：ByokGenerateService/DashScopeImageProvider/DidAvatarProvider/MiniMaxMusicProvider/ByokController/CredentialResolver），几乎零测试覆盖，直接把全仓覆盖率拉穿门禁。v2.11 的 67.3% 基线已过期，后续排期必须按新分母（2328）制定。

## 本轮交付（5 批 dpsk 生成 + 编排验收）

| 批 | 内容 | 结果 |
|---|------|------|
| A | RunServiceTest 追加 21 例（markSucceededIfAllDone/cancel/rerun/readPlanPreview/approve/retryStep/requireRun/toXxx/stats/sanitizeJson） | 54/54 全过；RunService 分支 70.1%→**89.1%**（+35） |
| B | LlmScriptServiceTest 追加 12 例（validate/parseScenes/buildUserContent/doGenerate 重试） | 46/46 全过；分支 68.8%→**73.2%**（+6） |
| C | RunExecutorTest 追加 12 例（advanceRun/tick/审批门/QC/recordToolCall/finalize） | 48/48 全过；分支 77.2%→**87.3%**（+16） |
| D | ByokGenerateService 可测性接缝（DownloadSender 函数式接口 + @Autowired 双构造器）+ 新建 ByokGenerateServiceTest 28 例 | 28/28 全过；分支 8.2%→**71.3%**（+86）、行 87.0% |
| E | SurrogateAuthClient Unix socket 接缝（SocketExchange 函数式接口 + @Autowired 双构造器）+ 新建 SurrogateAuthClientTest 19 例 | 19/19 全过；分支 0%→**80.4%**（+37） |

- `Tests run: 636, Failures: 0, Errors: 0, Skipped: 0`；BUILD SUCCESS；JaCoCo 新门禁（行 0.80/分支 0.68）通过（`verify -DskipTests` 复核：All coverage checks have been met）。
- 全量行覆盖 **80.5%**（4429/5499），分支覆盖 **68.7%**（1599/2328）——70% 目标未达成，差 30 个分支（1.3pp）。
- 门禁棘轮：pom JaCoCo LINE 0.78→**0.80**、BRANCH 0.65→**0.68**（只升不降，按实测 80.5%/68.7% 锁定）。

## 对照（生产级 checklist 相关条）

- [通过] 测试金字塔补强（新增 92 例：21+12+12+28+19；目标类分支大幅收敛）
- [通过] 门禁棘轮（行 0.80/分支 0.68，verify 阶段强制；本轮从变红修复为绿）
- [通过] 可测性接缝（ByokGenerateService.DownloadSender、SurrogateAuthClient.SocketExchange；均沿用 LlmTransport HttpExecutor 先例；双构造器均加 @Autowired，避开 v2.7 坑）
- [未通过→排期] 分支覆盖 70%（差 30 分支；见下）
- [未通过→排期] Agnes/Qwen 真实 provider submit/poll 分支（需外部 API）、LlmTransport 真实代理链路（沙箱无外网）——口径不变
- [未通过→排期] resolveExtension 的 "bin" 回退分支不可达（三个调用点的 extHint 恒为合法值 png/mp3/mp4）——死代码，建议 v2.13 删掉或放宽
- [已知 flaky] DramaV2ApiIntegrationTest.testFullPipeline 偶发 500（ffmpeg 环境抖动）：本轮 full verify 首次跑挂，单跑 94 秒通过，重跑 full verify 全绿。v2.11 已记录，保持观察。

## 本轮教训（已沉淀为工具/流程改进）

1. **管道 exit code 陷阱**：`mvn verify 2>&1 | grep ...` 的 exit code 是 grep 的，不是 mvn 的——本轮曾误判"BUILD SUCCESS"，实际门禁变红。以后判断构建成败必须看日志里的 BUILD SUCCESS / "All coverage checks have been met"，不许只看管道 exit code。
2. **基线必须每轮实测**：功能提交（BYOK）会改变分母，排期里的"剩余大头"数字会过期。开工先跑一遍全量 jacoco 再定目标。
3. **dpsk 输出 END 标记**：`=== END PATCH ===` / `=== END FILE ===` / `--- END ---` 多种变体残留；apply_patches.py 已加通用清理（PATCH 与 FILE 分支均处理）。
4. **apply_patches.py 多组 OLD/NEW**：单个 PATCH 块里多组会被贪婪 NEW 吞掉；已要求 dpsk 每块只放一组，脚本侧也加了健壮切分。
5. **dpsk 编造与断言错位**：VideoTaskStatus.SUCCEEDED（实际为 DONE）；parseScenes 单场景 JSON 撞"应为 4"校验；doGenerate 重试包装导致 message 断言要走 cause 链；resolveExtension "bin" 分支不可达——均已当场修正，prompt 红线继续加码。

## v2.13 排期

- 分支覆盖冲 70%（差 30 个分支；候选：ProviderService 56、DashScopeImageProvider 37、ByokController 30、DidAvatarProvider 26、MiniMaxMusicProvider 24；BYOK provider 的真实网络链路分支需录制回放或声明不可达）
- 删掉 resolveExtension 不可达的 "bin" 分支（或放宽 extHint 校验，产品确认）
- Agnes/Qwen submit/poll 录制回放扩到真实链路（需外部 API 时）
- h2c 锁定待产品确认（v2.9 遗留）

## 覆盖率数字说明

本机 `mvn -o verify` 实测；CI 环境跑全量后以 CI 为准。
