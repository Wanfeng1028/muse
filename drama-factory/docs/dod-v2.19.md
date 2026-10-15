# 发版对照报告：v2.19「分支覆盖冲 88%」（第 18 轮）

> 日期：2026-10-15。DoD v2.18 排期首项。微信 ChatAPI DeepSeek-V4-Flash 生成 7 批测试，编排验收。

## 结论

- 测试总数：1519 → **1554**（+35），全绿（2 skipped 为既有）。
- 分支覆盖：87.09% → **88.09%**（+1.00pp，**88% 目标达成**）；行覆盖 90.52% → **90.80%**。
- pom JaCoCo 门禁棘轮：LINE 0.90（保持），BRANCH 0.87 → **0.88**。
- 生产代码：**零逻辑修改**（纯测试新增）。

## 本轮 7 批

| 批 | 新测试文件 | 测试数 | 目标分支 |
|---|---|---|---|
| A | V219BatchATest | 8 | AssetService L80 null 臂（手写 MultipartFile stub）、CurrentUser L37（value.isBlank 臂，见下）、VideoProviderConfig L20、MvSong/VideoTask/DramaProject/PromptRecipe @PrePersist 臂 |
| B | VideoTaskServiceTimeoutTest | 1 | L224 超时退出臂 + L233 仍在途臂（单测耗时 25.5s，覆盖 25 秒关闭收尾超时路径） |
| C | DramaMetricsBranchTest | 4 | L97 model null/blank 归一化两臂、L115 ok=false 臂 |
| D | V219BatchDTest | 7 | ByokController L97 目录臂/L110 无扩展名臂、SkillController L135×2/L251/L284/L337 |
| E | V219BatchETest | 6 | EpisodeStatusFlowService L65、CREDENTIAL L85/L96、PromptRecipeService L133/L213、PresetService L97 |
| F | V219BatchFTest | 4 | RecipeController L99/L108/L109、RunController L88×2/L170/L171 |
| G | V219BatchGTest | 5 | SettingsController L63/L66/L70×2/L94 |

## 本轮破案：AssetService L80"存疑"根因

v2.18 遗留"第 80 行 blank 臂测试已执行但探针仍报 missed，未定位"。本轮用新鲜 jacoco.exec 单跑复现 + javap 反编译定位：

- 真相：Spring 6.1 的 `MockMultipartFile` 构造器把 `null` 的 originalFilename **规范化成了 `""`**（字节码：`aload_2; ifnull 24; ldc ""; putfield originalFilename`）。
- 因此 v2.18 的 `upload_nullOriginalName_fallsBackToFile` 传 null 实际走的是 `isBlank()→true` 臂（与 blank 测试重复），**从未覆盖 `originalName == null→true` 臂**。
- 修复：手写实现 `MultipartFile` 接口的极简 stub（`getOriginalFilename()` 严格返回 null），新测试一次命中，L80 探针翻绿。

## 诚实跳过清单（经源码级论证不可达，本轮不写测试）

- ByokController L94 `!p.startsWith(baseDir)`→true：module 被 FILE_MODULES 白名单限定，filename 字符集 `^[A-Za-z0-9._-]{1,128}$` 不含 `/`，p 恒为 baseDir 直接子路径。
- VideoTaskService L264 switch 隐式 default：RemoteStatus 四值穷举，null 会先 NPE。
- PipelineService L159 switch default：VideoTaskStatus 四值穷举，null 在 L156 已 continue。
- PresetService L55 `list == null`：presets.json 固定 16 预设全带 models 数组，ObjectMapper 对数组永不返回 null。
- RunService L422/L431 `qcStep != null`→false：approve() 内 findWaitingQcStep 在 L414（经 findFinalCutId）与 L418 被调两次，同输入结果恒一致；为 null 时 L415 已抛异常，到不了分支。
- RunLogService L77/L78 `read <= 0`：单线程下 start<length 时 read 必 >0（需并发截断文件才可达）；L103 `!file.startsWith(baseDir)`：runId/seqNo 纯数字校验拦死穿越。

## 本轮教训

1. **dpsk 会照抄展示层脱敏占位符**：既有 CredentialResolverBranchTest 在展示时密钥被脱敏为 `<redacted>`，dpsk 生成新测试时把 `assertEquals("Bearer <redacted>", …)` 当字面量照抄，导致"expected 与 actual 看似相同却失败"（hex dump 才现形）。修法：断言必须用真实期望值（如 `"Bearer " + "mini-k"`）。教训：prompt 里凡涉及既有测试的密钥断言，必须明示"用真实值，不许抄 <redacted>"。
2. **v2.18 排期的"88%"数学是错的**：13 个候选分支全中也只能到 87.48%。本轮实际瞄准 38 个分支，留足余量。教训：排期前先算数。
3. **慢测试是正当的**：25 秒超时测试覆盖的是生产代码真实行为（关闭收尾 25 秒超时），不是为了凑覆盖率硬造的 sleep。
4. **行号必须以源码为准**：本轮初版把 CurrentUser L37 误判为 `if (request == null)`（实为 L29），真正的 L37 是 `if (value.isBlank())`。且 `ServletRequestAttributes.getRequest()` 是 final 方法，Mockito 无法 stub——改用 `new ServletRequestAttributes(mock(HttpServletRequest.class))` 真实包装才走通。教训：写 prompt 前用 awk 打印目标行原文逐行核对。

## DoD 未通过项新排期

- v2.20 分支覆盖冲 89%（候选：QwenVideoProvider 4、ProviderController 5、ProjectService 5、Skill 6、GlobalExceptionHandler 6、VideoProviderRouter 6 等）
- Agnes/Qwen submit/poll 真实链路（需外部 API）
- h2c 锁定待产品确认
- testFullPipeline flaky 根因（本轮一次通过，根因未消）
