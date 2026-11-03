# 发版对照报告：v2.20 第 19 轮「分支覆盖冲 89%」

- 日期：2026-10-15
- 基线：分支 88.09% / 行 90.80%（v2.19 实测，3299 分支）
- 本轮：分支 **89.30%** / 行 **91.90%**（2946/3299 覆盖）
- 目标：分支 89% —— **达成**（+1.21pp，余量 0.30pp）
- 测试总数：1554 → **1634**（+80，全绿，2 skipped 为既有）
- 生产代码：零逻辑修改（仅 pom JaCoCo 门禁棘轮）
- 生成方式：微信 ChatAPI DeepSeek-V4-Flash，分 4 批生成（A/B/C/D），编排验收修 11 处

## 各批交付

| 批 | 新测试文件 | 测试数 | 目标分支命中 |
|---|---|---|---|
| A | QuickToolsServiceV220ATest | 15 | QuickToolsService 16→8（batchRename/convertVideo/extractAudio/exportShotCsv/resolveStoragePath/splitTags/csvEscape） |
| B | SkillServiceV220BTest | 17 | SkillService 14→11（publish/publishVersion/list/install/rate/renderTemplate） |
| C | SubtitleServiceV220CTest + ShotServiceV220CTest | 11+11 | SubtitleService 11→**0**、ShotService 9→**0**（两类清零） |
| D | AceStepMusicProviderV220DTest + DashScopeImageProviderV220DTest | 13+13 | AceStepMusicProvider 13→8、DashScopeImageProvider 10→6 |

## 门禁棘轮（只升不降）

- pom JaCoCo：LINE 0.90→**0.91**、BRANCH 0.88→**0.89**；`mvn -o verify -DskipTests` 已验证新门禁通过

## 本轮修 dpsk 输出 11 处

1. `s.setDurationSeconds(12.5)` 传 double 给 Integer 参数 → 改 25（编排机械修，断言同步改 "25"）
2. 同一 mock 方法写两个 doAnswer stub（第一个被覆盖 → UnnecessaryStubbing）→ 删冗余 stub
3. `VideoProvider.ConnectivityResult` 当 AceStep probe 返回类型 → 实为 `MusicProvider.ConnectivityResult`（编造类型）
4. `result.url()` → PollResult 真实访问器是 `imageUrl()`（编造方法）
5. `VideoProvider.ConnectivityResult` 当 DashScope probe 返回类型 → 实为 `ImageProvider.ConnectivityResult`
6. `generate_nullResponseBody` 断言"响应解析失败" → Jackson 2.17 `readTree("")` 返回 MissingNode 不抛异常，实际走"未返回音频地址"臂（v2.13 已证实的坑又踩一次）
7. `generate_httpBelow200` 用 HttpServer 发 199：1xx 被 HttpClient 当 interim 等最终响应，40 秒超时 → 诚实删除（真实服务端不会返回最终态 <200）
8. `submit_nullGatewayBody` 断言"响应解析异常" → 实际走"未返回 task_id"臂（同 6）
9. `poll_nullGatewayBody` 断言抛异常 → 实际走 switch default 返回 QUEUED（同 6）
10. D 批零 `<redacted>` 残留：prompt 明确点名"既有测试里的 `Bearer <redacted>` 是脱敏占位符不许照抄"，dpsk 本次没犯（v2.19 教训落地有效）
11. C 批 ShotService 构造器 2 参、Records 记录构造器参数顺序：prompt 事先给了白名单，一次通过

## 诚实跳过清单（经源码/实测论证不可达或不可触发，本轮不写测试）

- AceStep probe 的 `objectMapper.writeValueAsString` 抛异常臂：objectMapper 为 private final 无法注入，本地 HttpServer 触发不了（文件顶部注释已写明）
- AceStep generate 的 `code < 200` 臂：JDK HttpServer 发 199 会被 HttpClient 当 1xx interim 等待（实测 40 秒超时）；真实服务端不返回最终态 <200
- SubtitleService buildSrt 的 `Files.writeString` IOException 臂：@TempDir 真实目录写失败需 chmod 只读目录，但 root 用户无视权限位，触发不了（已在文件顶部注释写明）
- 其余未命中分支多为防御性分支（null 防护、空集合），留待后续轮次评估

## 本轮教训

1. **排期前先算数继续有效**：本轮开工前用 jacoco.csv 算出需 31 个分支，瞄准 73 个候选，最终命中 40 个，一次达标。v2.19 的"瞄准 38 个"方法论成立。
2. **Jackson 空 body 三连坑**：`readTree("")` → MissingNode 不抛异常，这个行为在 v2.13 已证实，本轮 D 批 dpsk 又按"解析失败"写了 3 个错误断言。教训：prompt 里凡涉及"空 body/空字符串解析"必须明示"readTree 空串不抛异常，走 MissingNode 后续分支"。
3. **1xx 状态码陷阱**：不要试图用本地 HttpServer 发 199/1xx 测 `code < 200` 臂，HttpClient 会当 interim 一直等。
4. **`<redacted>` 防线有效**：prompt 里点名警告后，D 批 27 个测试零残留。以后凡涉及既有测试文件里出现过脱敏占位符的，一律在 prompt 里点名。

## DoD 未通过项新排期

- v2.21 分支覆盖冲 90%（候选：SkillService 11、QuickToolsService 8、AceStepMusicProvider 8、DashScopeImageProvider 6、LlmTransport 16、AssetController 15、ScriptService 15 等；需约 23 个分支）
- Agnes/Qwen submit/poll 真实链路（需外部 API）
- h2c 锁定待产品确认
- testFullPipeline flaky 根因（本轮一次通过，根因未消）
