# 发版对照报告：v2.23 第 22 轮「分支覆盖冲 92%」

- 日期：2026-10-15（23:07 cron 轮）
- 基线：分支 91.91% / 行 92.33%（v2.22 终值，3299 分支）
- 本轮：分支 **93.07%** / 行 **92.52%**（3089/3319 覆盖）
- 目标：分支 92% —— **达成且超额**（+1.16pp）
- 测试总数：1725 → **1795**（+70，全绿，2 skipped 为既有）
- 生产代码：零逻辑修改（仅 pom JaCoCo 门禁棘轮）
- 生成方式：微信 ChatAPI DeepSeek-V4-Flash，分 5 批生成（A/B/C/D/E），编排验收修 6 处

## 本轮意外：agent-canvas POC 稀释了行覆盖

v2.22 终值行覆盖 92.33%，但其后落地的 agent-canvas POC（commit b726b25）新增了 `CanvasProjectService`（107 行）——分支 0%、行仅 7.55%，把全量行覆盖稀释到 **91.92%**，低于 0.92 门禁。本轮首轮 `mvn -o verify` 门禁变红（`lines covered ratio is 0.91, but expected minimum is 0.92`；测试 1781 全绿，是门禁不是测试挂）。遂加 E 批专门补 CanvasProjectService 覆盖（20 分支→0，100%），行覆盖回到 92.52%，门禁通过。教训：**新功能合入后、覆盖轮开工前，先跑一次门禁看基线是否被稀释**，不要默认上一轮终值仍有效。

## 各批交付

| 批 | 新测试文件 | 测试数 | 目标分支命中 |
|---|---|---|---|
| A | UsageServiceV223ATest | 13 | UsageService 14→**0**（分支 100%）：summary/requests/byDay 三处空串过滤臂、排序比较器双 null/ta 非 null 臂、byDay null tokens/cost 臂 |
| B | ByokGenerateServiceV223BTest | 10 | ByokGenerateService 13→9：size/imageUrl/audioUrl/videoUrl 空白臂、matchImage/matchAvatar 全变体、download drain IOException 臂、resolveExtension #fragment 臂、registerAsset null-assetService/文件不存在臂 |
| C | ScriptSplitterServiceV223CTest | 13 | ScriptSplitterService 13→2：skillId 非 null 臂、title null 三元两臂、scriptText null 臂、oldShots 非空臂、skillPrompt 空白/非空臂、status 199 臂、content NullNode 臂、toResponse 三处 null 臂（反射） |
| D | MvServiceV223DTest | 15 | MvService 13→5：importAudio null 文件名（手写 MultipartFile stub）/mime 变体臂、buildLyricsJsonFromText 尾空行臂、writeSrt null text 臂（反射）、muxAudio null/blank ffmpeg 臂 + false 假命令非零退出臂（反射） |
| E（加急） | CanvasProjectServiceV223ETest | 14 | CanvasProjectService 20→**0**（分支 100%）：load 文件不存在/存在/损坏、save 全部校验臂（null/非 object/version 缺失/非 int/≠1/nodes-edges 缺失非数组）、mcpTools |

终态：UsageService、CanvasProjectService 分支 **100%**；ScriptSplitterService 剩 2、MvService 剩 5、ByokGenerateService 剩 9。

## 门禁棘轮（只升不降）

- pom JaCoCo：LINE 0.92 保持（实测 92.52%）、BRANCH 0.91→**0.93**（实测 93.07%）；全量 `mvn -o verify` 已验证新门禁通过（BUILD SUCCESS，1795 用例 0 失败）

## 本轮修 dpsk 输出 6 处

1. C 批 `request.body()` —— `java.net.http.HttpRequest` 根本没有 `body()` 方法（是 `bodyPublisher()`），且 `toString()` 读不出内容。手工加 `bodyOf` helper（照抄既有 ScriptSplitterCallModelTest 的订阅式实现），两处调用点替换。
2. C 批 `ShotSize.中景` / `CameraMove.固定机位` —— 中文枚举值编造（v2.17 同类教训重犯：PUSH_IN/MEDIUM），实为 `ShotSize.ZHONG_JING` / `CameraMove.GU_DING`。
3. A 批 `AgentType.CODER` —— 枚举值编造 7 处，实为 SCRIPT/BOARD/VIDEO/EDIT/QC/LYRICS/COMPOSE，改 `AgentType.SCRIPT`。
4. **编排 prompt 设计失误**：A 批 `summary(null, "", 0)` 命中了 noFilter 快捷分支（provider/model 双空且 days≤0），空串过滤臂根本没进循环，taskCount 断言 1 实际 0。days 改 1 绕过快捷分支。教训：给 dpsk 的"用例设计"必须自己先过一遍分支可达性。
5. A 批 strict-stubs 下 helper 多余 stub 报错 3 处 —— 空串测试里 filter 短路，getter 永不被调用。helper 的 `when()` 改 `lenient().when()` 包裹（各用例仍做真实行为断言，不是放水）。
6. A 批 byDayVideoLoop 里 `when(r.getModelUsed())` —— model="" 时 L174 在 `!isEmpty()` 短路，该 stub 永不触发，删除。

## 诚实跳过清单（经源码级论证不可达，本轮不写测试）

- **ByokGenerateService L141** switch default：generate() L118 已校验 module∈{IMAGE,MUSIC,AVATAR}，default 不可达。
- **ByokGenerateService L180/L253** 轮询 deadline：deadline 写死 150_000L/240_000L，触达需真实 sleep 150/240 秒，不可达。
- **MvService L453** render clips.isEmpty()：空 sections 的 Timeline 经 fromJson/align/buildInstrumentalTimeline 都构造不出来，public 路径不可达（v2.15 既有结论）。
- **MvService L468** render 字幕过滤：需走完真实 ffmpeg 渲染链路，mock 下断言脆弱（v2.15 既有结论）。
- **MvService L541** findStep getSeqNo()==null：AgentStep.SEQ_NO 列 NOT NULL，mock 硬造无业务意义（v2.15 既有结论）。
- **MvService L570** resolveLocalAudio filePath==null：Asset.FILE_PATH 列 NOT NULL，同理（v2.15 既有结论）。
- **CanvasProjectService** save 内 ATOMIC_MOVE 失败回退分支：是否支持原子移动取决于文件系统，不可确定性触发。

## DoD 未通过项新排期

- v2.24 分支覆盖冲 94%（候选：ByokGenerateService 9、MvService 5、QuickToolsService 5、AceStepMusicProvider 4、ScriptSplitterService 2、DashScopeImageProvider 2 等；需约 31 个分支）
- Agnes/Qwen submit/poll 真实链路（需外部 API）
- h2c 锁定待产品确认
- testFullPipeline flaky 根因
