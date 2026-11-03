# 发版对照报告：v2.21 第 20 轮「分支覆盖冲 90%」

- 日期：2026-10-15
- 基线：分支 89.30% / 行 91.20%（本轮开工前全量实测，3299 分支）
- 本轮：分支 **90.36%** / 行 **91.51%**（2981/3299 覆盖）
- 目标：分支 90% —— **达成**（+1.06pp，余量 0.36pp）
- 测试总数：1634 → **1673**（+39，全绿，2 skipped 为既有）
- 生产代码：零逻辑修改（仅 pom JaCoCo 门禁棘轮）
- 生成方式：微信 ChatAPI DeepSeek-V4-Flash，分 5 批生成（A/B/C/D/E），编排验收修 17 处

## 各批交付

| 批 | 新测试文件 | 测试数 | 目标分支命中 |
|---|---|---|---|
| A | SkillServiceV221ATest | 10 | SkillService 11→3（publish slug-blank/publishVersion promptTemplate/list 匹配臂/install null计数/rate null计数/renderTemplate blank版） |
| B | QuickToolsServiceV221BTest | 5 | QuickToolsService 8→5（batchRename空Map/超长名/extractAudio非视频/shotNo非空/路径越界） |
| C | AceStepMusicProviderV221CTest + DashScopeImageProviderV221CTest | 4+5 | AceStep 8→4（apiKey-blank/modelId-blank/probe-key-blank/apiBase-blank）、DashScope 6→2（task_id null/poll无密钥/url null/message null/probe 200） |
| D | AssetControllerV221DTest | 10 | AssetController 15→**0**（file() 端点整体零覆盖，一次清零：filter lambda/非法路径/越界与不存在/mimeType双臂/updateTags null body） |
| E | AceStepMusicProviderV221ETest + SkillServiceV221ETest + DashScopeImageProviderV221ETest | 3+1+1 | 补 null 臂：AceStep generate/probe null key + null base、SkillService publishVersion null template、DashScope probe 302 |

## 门禁棘轮（只升不降）

- pom JaCoCo：LINE 0.91 保持（实测 91.51%）、BRANCH 0.89→**0.90**；全量 `mvn -o verify` 已验证新门禁通过

## 本轮修 dpsk 输出 17 处

1. Batch A 输出被 dpsk-call.py 默认 `--max-tokens 1024` 截断（4500 字符断在半截）→ 重跑时显式 `--max-tokens 8000`。教训：测试文件一批必须给足 8000+ tokens。
2. C 批 `VideoProvider.ConnectivityResult` 当 AceStep probe 返回类型 → 实为 `MusicProvider.ConnectivityResult`（同包内层 record，编造类型，v2.20 已犯过又犯）
3. C 批 `result.url()` → PollResult 真实访问器是 `imageUrl()`（编造方法，v2.20 已犯过又犯）
4. C 批 `VideoProvider.ConnectivityResult` 当 DashScope probe 返回类型 → 实为 `ImageProvider.ConnectivityResult`
5. C 批 `result.message()` → ConnectivityResult 真实访问器是 `detail()`（prompt 里我写错了签名，编排核对源码后统一改）
6. C 批缺 `import com.dramafactory.service.video.VideoProvider;`（裸用 VideoProvider.ConnectivityStatus）
7. E 批 SkillServiceV221ETest 编造 `SkillReviewRepository`/`SkillUsageRepository`（真实是 SkillInstallRepository/SkillRatingRepository）+ 漏四个 repository import
8. E 批 DashScopeImageProviderV221ETest 漏 `import static org.mockito.Mockito.mock/when` 与 `import static org.mockito.ArgumentMatchers.any`
9. E 批 DashScopeImageProviderV221ETest 漏 `import com.dramafactory.service.CredentialResolver;`（跨包）
10. C 批 prompt 里我误写 `PROBE_TIMEOUT`（DashScope 源码实际是 `Duration.ofSeconds(15)`）→ 动笔前自查源码后修正
11. B 批 `"a".repeat(201)` 测 `len > 200` 通过，但 L122 的 `len < 1` 臂恒不可达（name 已过 blank 校验，trim 后长度恒 ≥1）→ 列入诚实跳过
12. 展示层脱敏再确认：`sed` 看到的 `"Bearer <redacted>"` 经 `od -c` hex 核验实为 `"Bearer test-key"`（dpsk 按 prompt 要求写的明示假值），显示被脱敏而已，文件无问题
13-17. 其余为 import 顺序、Mockito `isNull()` vs `any()` 等机械问题（编排直接修）

## 诚实跳过清单（经源码级论证不可达，本轮不写测试）

- **QuickToolsService L173/L225**（convertVideo/extractAudio 的"输出路径非法"）：out = storageDir.resolve("assets/tools/UUID").normalize()，词法上恒为 storageDir 子路径，抛异常臂不可达
- **QuickToolsService L337**（csvEscape 的 `value == null`）：调用链只有 exportShotCsv→csvRow→csvEscape，且 exportShotCsv 在进 csvRow 前已把全部单元格三元转为非 null；csvRow/csvEscape 均为 private，无其他调用方
- **QuickToolsService L122**（`len < 1`）：name 已通过 `name.trim().isEmpty()` 校验，len 恒 ≥1
- **AceStep L83/L142**（`response.body() == null`）：httpClient 为 private final 无注入点，只能走真实 `BodyHandlers.ofString`，恒返回非 null
- **AceStep L84**（`code < 200`）：JDK HttpServer 对 1xx 按 interim 处理致客户端超时（v2.20 已实测 199 触发 40 秒超时），本地造不出终态 1xx
- **AceStep L96**（`audioUrl.isBlank()`）：extractAudioUrl 内部已用 `!asText().isBlank()` 过滤，返回值恒非空或 null
- **DashScope L242**（truncate 的 `value == null`）：两处调用传入的 responseBody 均已在之前被 `== null ? ""` 规范化

## 基线数据诚实注记

- v2.20 报告写"行 91.90%"，但本轮开工前两次全量实测（12:37 与 13:16 UTC 的 jacoco.xml）均为 **91.20%**。本轮以实测 91.20% 为基线，终值 91.51%（+0.31pp）。差异原因未定位（可能为 v2.20 某次中间态报告），此处如实记录。

## 本轮教训

1. **null 臂是独立分支**：`a == null || a.isBlank()` 的 null 臂与 blank 臂是两个分支。旧测试只传过 `"   "` 从未传过 null，导致 C 批"补 blank 臂"后 L48/L105/L207/L139 依然红。教训：prompt 里必须明确要求 null 与 blank 双臂。
2. **max-tokens 给足**：dpsk-call.py 默认 1024 tokens 不够一个测试文件，今后测试批次一律 `--max-tokens 8000` 起步。
3. **prompt 签名我写错 dpsk 照抄**：C 批 prompt 里我把 PollResult 写成 `url`、ConnectivityResult 访问器写成 `message()`，dpsk 照抄后编译失败。教训：prompt 里的"事实来源"节必须逐字核对源码，不能凭记忆写。
4. **展示层脱敏会骗人**：`sed` 看到 `<redacted>` 时先 `od -c` hex 核验再下结论（v2.19 教训的反向应用）。

## DoD 未通过项新排期

- v2.22 分支覆盖冲 91%（候选：LlmTransport 16、ScriptService 15、AgnesVideoProvider 14、UsageService 14、ByokGenerateService 13、ScriptSplitterService 13、MvService 13、FfmpegService 13 等；需约 33 个分支）
- Agnes/Qwen submit/poll 真实链路（需外部 API）
- h2c 锁定待产品确认
- testFullPipeline flaky 根因（本轮一次通过，根因未消）
