---
name: openmontage-avatar-spokesperson-asset-director
version: "1.0.0"
description: 为口播数字人流水线准备核心素材，包括旁白、数字人或口型同步画面、字幕文件、品牌背景与最低限度的辅助图形，适用于需要真实播报形象的短视频制作场景。
metadata:
  license: AGPL-3.0
---

# 素材总监 · 数字人口播流水线

## 适用时机

本阶段负责把"谁在说、说什么、画面长什么样"落实成可渲染的素材：旁白音频、数字人或口型同步视频、字幕、背景板，以及少量辅助图形。产出必须真实存在，不能停留在设想。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | 校验素材清单 |
| 上游产物 | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["idea"]["brief"]` | 播报计划与旁白需求 |
| 工具 | `talking_head`、`lip_sync`、`tts_selector`、`subtitle_gen`、`image_selector`、`audio_enhance`（选择器会自动发现注册表中的可用提供方） | 数字人、旁白与辅助素材 |
| Playbook | 当前激活的风格手册 | 背景、字体与字幕规范 |

## 处理流程

### 1. 锁定数字人生成路径

只能选一条主路径，并明确记录：

- `talking_head`：由静图加音频驱动；
- `lip_sync`：用已有播报画面搭配新音频；
- 外部渲染：在本运行时之外生成好的数字人素材。

如果这条路径被阻塞，必须如实记录，不允许隐瞒。

### 1b. 采样预览（避免浪费预算）

批量生成前，先对每种昂贵素材产出一个小样给用户确认：

1. **TTS 采样**：如果旁白需要合成，先生成一段。确认音色、语速、人设后再批量。
2. **数字人采样**：如果走 `talking_head`，先生成一段短测试片段。确认画质可接受再全面铺开。

被否决就调参重试，最多 3 轮。未获批准前不要批量。

### 2. 先解决旁白，再谈辅助图形

口播视频的命脉是声音。确认旁白属于以下哪种情况：

- 用户提供；
- TTS 合成；
- 已内嵌在播报画面里。

若旁白缺失且没有可用的 TTS 工具，将项目标记为 blocked，不要假装本阶段完成。

### 3. 构建最小辅助套件

只做场景计划真正需要的部分：

- 字幕文件；
- 一套统一的角标系统；
- CTA 卡片；
- 背景或底板素材；
- 可选的产品/静帧支持图。

### 4. 用元数据说明能力实情

建议使用的元数据键：

- `avatar_generation_path`
- `narration_assets`
- `subtitle_assets`
- `background_assets`
- `scene_asset_index`
- `blocked_assets`

### 5. 质量门

- 数字人路径明确；
- 旁白与数字人素材互相对齐；
- 辅助图形保持克制；
- 每个被引用的文件都真实存在。

## 无数字人路径

当 EP 触发"旁白配图"转向（`talking_head` 与 `lip_sync` 都不可用）时，跳过数字人生成，改为产出图形驱动的素材包：

### 需要产出：
1. **旁白音频** — 通过 `tts_selector`（强制项；若连 TTS 也没有，项目直接 blocked）。
2. **场景视觉** — 通过 `image_selector` 或 `video_selector`。每个场景一张主视觉，强化口播要点（示意图、插画、产品图或素材画面）。
3. **字幕文件** — 与标准路径一致。
4. **文字卡** — 要点覆盖、数据卡、CTA 收尾卡。
5. **背景** — 与风格手册一致的统一家族。

### 需要跳过：
- 不调用 `talking_head`、`lip_sync`。
- 不产出播报构图元数据。
- `avatar_generation_path` 写为 `"none — narration-over-graphics pivot"`。

### 该路径的元数据：
- `avatar_generation_path`：`"narration_over_graphics"`
- `pivot_reason`：为什么选择无数字人路径
- 其他元数据键保持不变。

### 制作中的事实核查

生成素材时如果遇到不确定：

- 用 `web_search` 核对主体的真实外观（比如某栋建筑到底长什么样）；
- 用 `web_search` 找参考图，再开始生成插画；
- 在决策日志中记录：`category="visual_accuracy_check"`。

视觉准确性很重要。脚本提到具体地点、人物或物品时，先查清它的实际形态再生成图像。别依赖模型训练数据——可能过时或错误。

## 常见陷阱

- 旁白路径尚未定下来就急着做装饰性素材。
- 在简单的口播视频里混用多种数字人生成策略。
- 核心播报素材还只是设想就把阶段标为完成。
- （无数字人路径）生成与旁白毫无关联的填充画面——每张图都必须强化口播要点。

## 遇到不熟悉的做法时

如果遇到拿不准的生成技术、提供方行为或提示词模式：

1. **联网搜索**当前最佳实践——模型与 API 变化很快，训练数据可能已过时；
2. **查阅 `.agents/skills/`** 中已有的 Layer 3 知识（提供方提示词指南、API 模式）；
3. **若都不解决问题**，在 `projects/<project-name>/skills/<name>.md` 写一个项目级技能文档记录你学到的东西；
4. **在技能文档里标注来源 URL**，方便追溯；
5. **写入决策日志**：`category: "capability_extension"`，`subject: "learned technique: <name>"`。

以下情形尤其重要：
- **视频生成提示词** — 每个版本对词汇的反应都不一样；
- **图像模型参数** — FLUX、GPT Image、Imagen 的最优设置各不相同且持续演进；
- **音频提供方的怪癖** — 声音克隆、音乐生成、TTS 各有最佳实践；
- **Remotion 组件模式** — 框架演进会带来新的合成技巧。

不要依赖过时知识。有疑问，先搜索。

---

## 门禁提醒（强制）

本阶段以人工审批为门禁（`human_approval_default: true`）。评审通过后：
用 `status="awaiting_human"` 打检查点，展示摘要（Backlot 面板会渲染产物），并**结束本轮**。不要在同一轮响应里启动下一阶段。审批是按门禁计数的——早前的"继续"不覆盖本次门禁。

## HeyGen Avatar V

对明确获批的 HeyGen 数字分身使用 `heygen_avatar`。渲染前先核对形象：Avatar V 要求 `supported_api_engines` 中包含 `digital_twin` 和 `avatar_v`。传入脚本加 voice_id，或提供一个音频源。轮询超时后保留返回的 resume_job/job_path，恢复任务而不是重新提交。形象不合规就是阻塞点，绝不能擅自切换到 Avatar IV。请阅读 provider-model-refresh 技能。
