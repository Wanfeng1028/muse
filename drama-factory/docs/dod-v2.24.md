# 发版对照报告：v2.24 第 23 轮「分支覆盖冲 94%」

- 日期：2026-10-16（00:07 cron 轮）
- 基线：分支 93.07%（3089/3319）/ 行 92.52%（v2.23 终值）
- 本轮：分支 **94.03%**（3121/3319）/ 行 **92.62%**
- 目标：分支 94% —— **达成，超额 2 个分支**（+0.96pp，+32 分支）
- 测试总数：1795 → **1855**（+60，全绿，2 skipped 为既有）
- 生产代码：零逻辑修改（仅 pom JaCoCo 门禁棘轮 BRANCH 0.93→0.94）
- 生成方式：微信 ChatAPI DeepSeek-V4-Flash，分 7 批（A/B/C/D/E/F/G），B 批拆分为两个包，G 批 dpsk 两轮编造后由编排手工落盘（见下）

## 各批交付

| 批 | 新测试文件 | 测试数 | 目标分支命中 |
|---|---|---|---|
| A | ByokGenerateServiceV224ATest | 6 | ByokGenerateService：L199 musicProvider null→IllegalStateException、L334 drain catch（见下注）、L373 resolveExtension 无斜杠臂（反射）、L422 assetService null 臂（顺带） |
| B1 | ProviderProbeV224BTest | 2 | AceStep L84 code>=300 臂、DashScope L235 2xx→OK 臂 |
| B2 | ServiceBranchV224BTest | 5 | ScriptSplitter L137 title null 臂、L347 catch 重抛臂、MvService L255 尾空行臂、QuickTools L122 len>200 臂、L266 shotNo null 臂 |
| C | MiniMaxMusicProviderV224CTest | 16 | MiniMax：L69/L74/L154 校验臂、L214/L217 truncate 臂等 7 分支 |
| D | MvControllerV224DTest | 6 | MvController：L111 body null（直接调用）、L126/L127 null 回退、L227 缺失/目录臂、L237 safe 双臂 |
| E | MvLyricsServiceV224ETest | 9 | MvLyrics：L35/36/39 prompt 组装臂、L117/L121 stripFence 臂等 6 分支 |
| F | MvTimelineServiceV224FTest | 10 | MvTimeline：L43/L171/L174/L207 等 5 分支 |
| G | ByokFixV224GTest | 6 | MiniMax L119 code<200 臂、Byok L211 audioUrl null 臂、L186 imageUrl null 臂、L259 videoUrl null 臂、MvLyrics L121 lastFence<0 臂、Byok L334 未进 catch 臂 |

注：A 批 L334（download drain catch）的"进入 catch"臂上一轮已由 v2.23-B 覆盖；本轮 G 批补的是"500+正常关闭→不进 catch"臂。实证过程：先误判为 mock 未生效，逐行核验 JaCoCo 后定位到 try-with-resources 的双臂模型。

## 门禁棘轮（只升不降）

- pom JaCoCo：BRANCH 0.93→**0.94**（实测 94.03%），LINE 0.92 保持（实测 92.62%）；`mvn -o verify` 全量验证通过（BUILD SUCCESS，1855 用例 0 失败）

## 本轮修 dpsk 输出 / 编排手工修（共 11 处）

1. B 批包可见性：原文件放在 `com.dramafactory.coverage` 包，调不到 service/byok 两包的包可见构造器与方法。拆成 `ProviderProbeV224BTest`（byok 包）与 `ServiceBranchV224BTest`（service 包）；附带修 `ImageProvider.ConnectivityResult` 类型笔误（非 VideoProvider 的）。
2. B 批 ScriptSplitterService 9 参构造器在 coverage 包不可见——拆包后解决。
3. MiniMax C 批 4 处 NPE：auth 校验看的是 `entry.getKey()` 不是 value，`Map.entry("Authorization","")` 永远过校验。改为 `new AbstractMap.SimpleEntry<>("", "Bearer test-key-123")` / `(null, ...)`。
4. Byok A 批 L373：`URI.create("file.mp3")` 无 scheme，`HttpRequest.newBuilder().uri()` 在 downloadSender 之前先抛。改为反射直测 private static resolveExtension。
5. Byok A 批附带：删 dpsk 的 filler 测试（`downloadSenderLambda_acceptsHttpRequest_compilesAndRuns`，零分支价值）。
6. G 批 dpsk 第一轮：编造 `ByokAuthResolver`/`ByokProvider`/`ByokProviderRepository`、照抄 `<redacted>`、用错 `org.springframework.http.HttpRequest`。打回。
7. G 批 dpsk 第二轮：仍编造 `byok.provider` 包与私有方法直调。两轮用尽，编排按已验证模式手工落盘 6 个测试（A/C/E 批的既有写法照抄），并在文件中注明。
8. G 批补漏时发现三处子臂误判（上一轮按陈旧行号设计打偏）：MiniMax L119 缺的是 code<200 臂（非 code>=300）、Byok L211 缺的是 null 臂（非 blank）、Byok L259 实为 videoUrl 检查（非 FAILED 检查，行号错位）。逐个实证修正。
9. MvControllerV224DTest：`@TempDir` 传构造器 storageDir，直测 video() 的缺失/目录/正常三臂。
10. `throws Exception` 遗漏 7 处（`doReturn().when(gateway).exchange()` 的受检异常声明）。
11. 缺 import 3 处（CredentialResolver、VideoProvider、anyBoolean、HttpResponse）。

## 诚实跳过清单（经源码级论证不可达，本轮不写测试）

- **ByokGenerateService L141** switch default：generate() L118 已校验 module∈{IMAGE,MUSIC,AVATAR}（v2.23 既有）。
- **ByokGenerateService L180/L253** 轮询 deadline：写死 150_000L/240_000L，触达需真实 sleep（v2.23 既有）。
- **ByokGenerateService L334** try 体抛异常臂：try 体仅为 `// drain and ignore` 空语句，异常只可能来自 close()；"try 体抛"臂不可达。
- **ByokGenerateService L422** path==null 臂：registerAsset 的 path 来自 download() 返回值，恒为 "/api/byok/file/..." 非 null。
- **MiniMaxMusicProvider L138** audioUrl==null 臂：`root.path("data").path("audio").asText("")` 永不返回 null。
- **MiniMaxMusicProvider L144** durationNode==null 臂：`root.path(...).path(...)` 缺字段返回 MissingNode 永不 null。
- **MvLyricsService L78** lyrics==null 臂：`n.path("lyrics").asText("")` 永不 null。
- **MvController L219** sid 校验：`String.valueOf(Long)` 恒匹配正则，直接调用也构造不出反例。
- **MvController L224** 路径穿越：sid 恒为数字，resolve 后恒在 baseDir 内。
- **MvTimelineService L80** cp<1：行经 trim 且空行已丢弃，codePointCount 恒 ≥1。
- **MvTimelineService L122** sumAfterClamp≤0：每行钳制下限 800ms 且至少一行，和恒 >0。
- **MvTimelineService L145** flatLines 为空：sections 非空（L43/L207 已抛），flatLines 恒非空。
- **AceStepMusicProvider L83/L142** body()==null：HttpClient.ofString 的 body() 永不 null，真机 HttpServer 也造不出。
- **AceStepMusicProvider L96** isBlank 臂：extractAudioUrl 只返回非空串或 null。
- **DashScopeImageProvider L242** truncate null 臂：所有调用点传入的 responseBody/e.getMessage() 经 `==null?""` 处理或恒非空。
- **QuickToolsService L173/L225** 输出路径非法：out 由 storageDir resolve 生成并 normalize，恒以 storageDir 为前缀。
- **QuickToolsService L337** csvEscape null：只被 csvRow 调用，cells 永不 null（v2.21 既有）。

## DoD 未通过项新排期

- v2.25 分支覆盖冲 95%（候选：剩余可达分支约 15 个，多为控制器/服务的边角；诚实跳过清单已占大头，继续冲的边际收益递减，建议转入功能深耕）
- Agnes/Qwen submit/poll 真实链路（需外部 API）
- h2c 锁定待产品确认
- testFullPipeline flaky 根因（本轮未复现）
