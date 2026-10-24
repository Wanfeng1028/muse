# Jellyfish 存档与集成笔记（2026-10-24）

## 它是什么

**Jellyfish**（Forget-C/Jellyfish）——AI 短剧制作工作台（AI Short Drama Studio）：
从剧本输入 → 结构化分镜拆解 → 一致性管理（角色/场景/道具/服装）→ 分镜准备 →
视频生成 → 导出的端到端生产流程。技术栈：后端 FastAPI（Python）+ 前端 React/Vite，
异步生成任务系统（Celery），OpenAI 兼容的模型接入。

- 上游：https://github.com/Forget-C/Jellyfish
- 存档时上游 HEAD：`a967819`
- star：6,841 / fork：1,175（GitHub API 实测，2026-10-24）
- 许可证：**Apache-2.0**（LICENSE 原件随仓保留）

## 存了什么

整仓原件 791 个文件（不含 .git），与上游逐文件 diff 无差异；无单个 >50MB 文件，
无排除项。本地 clone 另存 `~/workspace/jellyfish`。

## 集成了什么（剧坊 drama-factory）

Jellyfish 最核心、最可直接借鉴的机制是**分镜视频生成准备度（shot video readiness）**：
生成前聚合检查——待确认的素材/台词候选、按生成模式要求的参考帧、进行中的生成任务，
并派生视频提示词预览。本轮按剧坊现有模型与"只报告不拦截"的既有检查器惯例
（ShotContinuityChecker、SlideshowRiskScorer）独立实现为只读报告，不改生成行为：

- `ShotReadinessService`：对单个分镜做准备度检查（描述、视频提示词、时长为阻塞项；
  景别/运镜缺失、配音开启但无台词为警告项；进行中的 VideoTask 仅作状态提示；
  无现成提示词时按描述+景别+运镜+时长派生预览提示词并标注"派生"）。
- `ShotReadinessController`：`GET /api/episodes/{episodeId}/shots/{shotId}/readiness`
  与 `GET /api/episodes/{episodeId}/shots-readiness`（整集批量）。
- 测试：`ShotReadinessServiceTest`（9 个）+ `ShotReadinessApiTest`（4 个），共 13/13 全绿，亲跑核实。

## 为何其余不集成

- Jellyfish 本体是 Python FastAPI + Celery 栈，剧坊是 Java Spring Boot 栈，整仓移植不成立。
- 剧本拆解 Agent 链（script_divider / element_extractor / consistency_checker 等）与
  剧坊已有的 ScriptSplitterService、PromptRecipe、连续性检查器在能力上重叠，
  本轮不重复造；其"待确认候选"工作流（素材/台词候选 accept/ignore）与
  "统一异步任务追踪"两项设计记为后续借鉴候选。
- 前端 React 工作台不与剧坊现有前端体系混用。
