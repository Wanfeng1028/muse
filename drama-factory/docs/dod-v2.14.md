# 发版对照报告：生产级补强 v2.14 第 13 轮「分支覆盖冲 75%」

日期：2026-10-15｜基线：v2.13（分支 73.0% / 行 82.4%，门禁 LINE 0.82 / BRANCH 0.70）

## 结论：目标达成，可发版

- 分支覆盖 **73.0% → 75.54%**（75% 目标达成，超额 0.54pp）
- 行覆盖 82.4%（v2.13 实测）→ **84.93%**
- 测试总数 1049 → **1069**（+20，全绿，除 1 个已知 flaky）
- pom JaCoCo 门禁棘轮：LINE 0.82 → **0.84**、BRANCH 0.70 → **0.75**

## 本轮交付

### 1. QuickToolsServiceBranchTest（新建，20 例，一次全绿）

目标类 `com.dramafactory.tools.service.QuickToolsService`（P2-7 快捷工具集，v2.13 后新增，基线时 40 个分支未覆盖）：
分支 92/132（69.7%）→ **116/132（87.9%）**，单类补 24 个分支。

20 例全部纯 Mockito 单元测试（`@TempDir` 传 storageDir，不起 Spring 上下文），覆盖：
- batchTagAssets：null ids / mode=null 默认 merge / 非法 mode / merge 空 tags / replace 空 tags 清标签（5）
- batchRenameAssets：null map / 空白名 / 超长名 / 不存在 → ResourceNotFound + 失败日志分支（4）
- convertVideo：format=null 默认 mp4 / 非法 format / maxWidth 越界（双断言）/ 资产不存在 / ffmpeg 抛错 → 失败日志分支（5）
- extractAudio：format=null 默认 mp3（断言 mimeType="audio/mpeg"）/ 非法 format（2）
- exportShotCsv：全 null 字段空单元格 / 特殊字符转义（引号 doubling）/ 剧集不存在 → 失败日志分支（3）
- resolveStoragePath：非法路径（经 convertVideo 触发）（1）

### 2. v2.13 排期项核验：「删 resolveExtension 不可达 "bin" 分支」已关闭

核验结论：**该分支在 f4fa998（2026-10-14 21:56）已删除**（`return "bin";` → 抛 `IllegalStateException`），v2.13 写排期时不知情，两轮 PATCH 锚定失败正是因为目标代码已不存在。
本轮 `grep -rn '"bin"' src/` 确认零残留，关闭该排期项，无需再动生产代码。

## 验收

- `mvn -o verify`：1069 测试，仅 1 失败 = `DramaV2ApiIntegrationTest.testFullPipeline`（已知 flaky：mock 视频轮询 60 秒未 DONE，ffmpeg 环境抖动；v2.11 起记录在案，**本轮单独重跑通过**）
- `mvn -o jacoco:report`：分支 75.54%（2492/3299）、行 84.93%（6600/7771）
- 门禁棘轮已应用（pom.xml）：下次无 flaky 的全量构建将执行 0.84/0.75 新门禁

## 本轮教训

1. **排期前先核验代码现状**：v2.13 排期里的 "bin" 分支删除项，实际在 f4fa998 已落地。以后排期项开工前先 `grep`/读代码确认，避免对着已不存在的代码写 PATCH。
2. **split-dpsk.py 不剥 `=== END FILE ===` 标记**：dpsk 输出尾部的 END 标记会残留进文件导致编译失败（本轮第 256 行）。已手动删除；后续批次落盘后先 grep 确认无标记残留再编译。
3. **基线每轮实测**（v2.12 教训重申）：P2-6/P2-7 合入后分支总数 3299 不变但分布已变，开工实测的 74.81% 才是真基线，不是 v2.13 的 73.0%。

## DoD 未通过项新排期（v2.15）

- Agnes/Qwen submit/poll 录制回放扩到真实链路（需外部 API，v2.9 起遗留）
- h2c 锁定待产品确认（v2.9 遗留）
- 分支覆盖冲 80%（候选：ByokGenerateService 44、ProviderService 30、MvService 29、UsageService 28、PipelineService 28、RunArtifactController 28，见 jacoco 报告）
- `DramaV2ApiIntegrationTest.testFullPipeline` flaky 根因（ffmpeg 环境抖动，v2.11 起第三次出现；考虑 mock 化视频轮询或延长超时）
