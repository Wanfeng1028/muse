# 生产就绪对照报告 v0.8.0

- 版本：v0.8.0
- 主题：PDF 文本提取
- 日期：2026-10-16
- 改动范围：PdfExtractor fork+exec 无 shell、Indexer .pdf 接入、Hit.file_type、Passage.page_no、/api/search 与 /api/locate JSON 加字段、Web UI 徽标、Docker 运行镜像加 poppler-utils、kVersion→0.8.0。
- DB schema 无变更（user_version 保持 3）。

## 1. 可靠性

- 通过：PdfExtractor 采用 fork+exec（无 shell），避免命令注入与 shell 解析差异。
- 通过：pdftotext 缺失时 .pdf 文件跳过并记 warn，不影响其他格式索引。
- 通过：损坏 / 加密 PDF 跳过，批量索引继续（CorruptedSkippedBatchContinues）。
- 未验证：失败注入未做（沿用 v0.5.0 结论）。

## 2. 可观测性

- 通过：PDF 提取失败走 warn 日志，含文件路径。
- 通过：/api/search 命中含 file_type；/api/locate 命中含 page_no，便于客户端观测。
- 通过：Web UI 展示文件类型徽标（HTML/MD/TXT/PDF）。

## 3. 数据与状态

- 通过：DB schema 无变更，user_version 保持 3，向前兼容。
- 通过：PDF 文本以既有 documents / documents_fts 结构入库，复用现有检索路径。
- 通过：Passage.page_no 为派生字段，不落库。
- 未验证：备份恢复未专项验证（沿用 v0.5.0 结论）。

## 4. 部署运维

- 通过：Docker 运行镜像（debian:12-slim）安装 poppler-utils 作为 PDF 提取运行时依赖。
- 通过：宿主部署需自行安装 poppler-utils，README 已说明；缺失时降级为跳过 .pdf。
- 通过：镜像清理 apt 列表，控制体积。

## 5. 安全健壮性

- 通过：fork+exec 直接传递 argv，无 shell 介入，无注入面。
- 通过：fileTypeLabel / hasPdfExt 仅按扩展名小写化比较，无路径拼接副作用。
- 通过：页码逻辑按命中词字节偏移数换页符定页（findTermCi 大小写不敏感定位首个命中词，pdfPageForOffset 计数），空 matched_terms 回落为第 1 页，无越界风险。
- 通过：/api/search、/api/locate 新增字段均经 jsonEscape 输出。

## 6. 可维护性

- 通过：file_type / page_no 均为独立字段，向后兼容，不破坏既有 JSON 消费者。
- 通过：新增测试覆盖搜索命中类型标记、locate 页码、非 PDF page_no 归零。
- 通过：README 与生产对照报告同步更新。
- 已知：WatcherTest.SubDir 为已知 inotify 时序 flaky（v0.5.0 已有，本轮重跑通过）。
- 测试数字（编排者实测回填）：`ctest` 口径 123 例全部通过（v0.7.0 的 108 例 + 本轮新增 15 例：PdfSelfCheck MD5/RC4 自检 2 + PdfTest 13）。WatcherTest.SubDir 为已知 inotify 时序 flaky（v0.5.0 已有），本轮全量中一次通过、一次 flaky 后重跑通过，与本轮改动无关。
- 编排者修正记录（透明）：① B3 初版页码按窗口起始行 `line_start` 换算，因 rankPassages 返回滑动窗口导致次页命中被算回第 1 页，修正为按首个命中词字节偏移定页；② 换页符恰好落在行起始偏移处时需含等号计数（`i <= offset`）。两次修正均有单测覆盖（PdfTest.LocateReportsPageNo）。
- ③ 视觉验收发现 rankPassages 会把纯 `\\f` 行当成段落返回（空 matched_terms 的垃圾 anchor），在 locator 的 PDF 分支加空白段落过滤（isBlankText），/api/locate 实测已干净。
- ④ B2 遗漏：service.cpp 里 /api/health 与服务启动日志的版本号硬编码为 0.7.0，已同步为 0.8.0（main.cpp kVersion 在 B2 已改）。
