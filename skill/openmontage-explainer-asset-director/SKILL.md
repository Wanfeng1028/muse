---
name: openmontage-explainer-asset-director
version: "1.0.0"
description: 解说视频资产制作导演技能，根据场景计划与脚本批量生成旁白配音、图像、图表、代码片段与背景音乐，适用于需要把制作计划落地为磁盘上真实素材文件的生成式视频流水线阶段。
metadata:
  license: AGPL-3.0
---

# 资产导演 — 解说流水线

## 适用时机

你负责生成式解说视频的素材制作。手上会有带素材需求的 `scene_plan` 和含旁白文本的 `script`。目标是产出全部所需资产：旁白音频、图像、图表、代码片段、背景音乐。收尾前每个文件都必须真实存在于磁盘上。

计划在这一步变成真实文件。缺失或低质量的素材会毁掉成片。

## 动画实现选型

动手写任何 Remotion 动画组件前，先读 `skills/meta/animation-runtime-selector.md`，它是决定用 Remotion 原语还是 GSAP 插件的路由权威。

常见解说场景的快速路由：

| 场景类型 | 推荐做法 |
|---|---|
| 标题卡、淡入、滑动、缩放 | Remotion 原语 —— `interpolate()` + `spring()` |
| 与旁白同步的词级字幕高亮 | 现成的 `CaptionOverlay` 组件（已在 `remotion-composer/src/components/`） |
| 逐字符动态字体（“字母逐个炸开”） | GSAP SplitText —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 4 段以上补间组成的多步编排 | GSAP timeline —— 读 `.agents/skills/gsap-timeline/SKILL.md` |
| Logo 构建（描边、路径揭示） | GSAP DrawSVG —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 数据图表（柱/线/饼/KPI） | Remotion 内置图表组件 —— 见 `remotion-composer/SCENE_TYPES.md` |
| 终端或 CLI 演示 | Remotion TerminalScene —— 读 `.agents/skills/synthetic-screen-recording/SKILL.md` |

**能简则简原则**：如果 Remotion 原语 20 行以内就能搞定某个场景，就用它。只有 GSAP 插件确实值那份打包体积时才引入。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | 产物校验 |
| 上游产物 | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["proposal"]["proposal_packet"]` | 决定要做什么 |
| Playbook | 当前生效的风格 playbook | 图像提示词、图表风格、音频偏好 |
| 工具 | `tts_selector`、`image_selector`、`video_selector`、`diagram_gen`、`code_snippet`、`music_gen`，选择器会自动从注册表发现可用 provider | 生成能力 |
| 成本跟踪 | `tools/cost_tracker.py` | 预算管控 |

## 流程

### 第 1 步：清点所需素材

遍历场景计划里每个场景，对每个 `required_assets` 条目建立资产任务：

```
Asset Task:
  scene_id: scene-3
  type: diagram
  description: "Mermaid flowchart: query -> encode -> search -> rank -> return"
  source: generate
  tool: diagram_gen
  estimated_cost: $0.00
```

此外还要建：

- **旁白音频** —— 每个脚本小节一条（用 `tts_selector` 或具体 TTS provider）
- **背景音乐** —— 整片一条（用 `music_gen` 或从素材库选）
- **音效** —— 按 playbook 的 `sfx_style`（可选，用 `music_gen` 或现成音效）

### 第 2 步：预算检查

动手生成之前：

1. 汇总所有资产任务的预估成本
2. 与成本跟踪器剩余预算比对
3. 超预算时：
   - 换便宜工具（用 `tts_selector` 的 `preferred_provider` 指向更便宜的 TTS；用 `image_selector` 指向更便宜的图像 provider）
   - 减少图像数量（合并相似场景）
   - 砍掉可选资产（音效、B-roll）
4. 通过成本跟踪器取得费用批准后再继续

### 第 2b 步：样例预览（避免浪费性开销）

批量生成前，对每种高价资产先产出一条样例并交用户确认：

1. **TTS 样例**：若脚本含 `script.voice_performance.sample_section_id` 就生成该节；否则挑演绎要求最高的一节。放给用户听，确认音色、语速、停顿、重音、语气都过关再批量跑其余部分。
2. **图像样例**：为最具代表性的场景生成一张。给用户看，确认风格、质量、提示词思路后再批量出图。
3. **音乐样例**（若用 `music_gen`）：生成一段短片段，确认情绪与能量再决定。

用户打回样例时：

- 调整参数（音色、提示风格、provider）并重新出样例。
- 样例未通过前不要批量生成。
- 每类资产最多迭代 3 次样例，仍不行就升级给用户决策。

这一步通常总共花 $0.03–0.08，能省下 $1–3 的废生成。

### 第 3 步：生成旁白

对每个脚本小节：

1. 取出旁白文本
2. 读 `script.voice_performance` 与小节的 `delivery_cues`
3. 有 `delivery_cues.provider_text` 就用它；否则仅在所选 provider 支持时，用有意义的标点和停顿标签改写小节文本
4. 套用脚本里的说话人指示（语速、重音、情绪）
5. 套用 playbook 的 `audio.voice_style`
6. 把提示映射到 provider 参数：
   - OpenAI：仅 `model: "gpt-4o-mini-tts"` 时支持 `instructions`；输出格式用 `response_format`
   - Google TTS：用 `<break>` 标签时设 `input_type: "ssml"`，配合 `speaking_rate`（0.25..2.0）与 `pitch`（-20..20）
   - ElevenLabs：`stability`、`similarity_boost`、`style`、`speed`、`use_speaker_boost`
   - Azure：声音别名（`andrew`、`brandon`、`ava`、`guy`、`jenny`）或任意 Azure 短名，SSML 的 `rate`（如 `"-4%"`）、`pitch`（如 `"+1st"`）、`style`（如 `"narration-professional"`）—— 见 `azure-text-to-speech` 技能
7. 用 `tts_selector` 生成 —— 它会按用户偏好与可用性自动路由到最合适的 TTS provider。查注册表的 `best_for` 字段了解各家强项。
8. 在每个旁白资产上记录实际生效的 `voice_performance` 元数据
9. 确认音频文件存在，时长与预期时间吻合（±15%）

**发音指南**：脚本里若有技术术语、行话或发音不直观的专名，在 TTS 请求里附上发音映射表。

**平淡音色失败**：已确认的音色若听起来单调、机械、急促或忽略了预期停顿，不要批量跑其余小节。修订 `voice_performance` 计划或 provider 参数，重出样例。

### 第 4 步：生成视觉资产

按工具分组处理资产任务以提高效率：

**图像（`image_selector`）**：

1. 依据场景真实意图构建提示词：
   - 来自 `shot_language`、`shot_intent`、`texture_keywords` 的场景专属镜头/灯光/质感线索
   - 从 playbook 或自定义身份改编的视觉锚点
   - 具体主体/动作/环境
   必要时用 `lib/shot_prompt_builder.py`。
2. 加上 playbook 的负面提示
3. 加入一致性锚点（同一角色/世界/色系），但不要每张图都复用完全相同的措辞
4. 生成并确认文件存在
5. 结果不符预期就细化提示词并重生成（最多重试 2 次）

**图表（`diagram_gen`）**：

1. 把场景描述转成合法 Mermaid 语法
2. 套用 playbook 的 `asset_generation.diagram_style`
3. 生成 SVG/PNG
4. 核对所有节点与边都在

**代码片段（`code_snippet`）**：

1. 从场景描述中提取语言与代码
2. 套用 playbook 覆盖层样式里的语法高亮主题
3. 生成高亮图或 Remotion 兼容数据

### 第 5 步：生成音乐

1. 读 playbook 的 `audio.music_mood` 与 `audio.music_volume`
2. 查 `proposal_packet.production_plan.music_source` 里的音乐决策（由提案导演设定）
3. 按此优先级获取背景音乐：
   - **用户选定素材库曲目**：提案指定了 `music_library/` 里某首就复制到 `projects/<project>/assets/music/background_music.mp3`
   - **用户音乐库（`music_library/`）**：目录存在且有曲目，就按 playbook 的 `audio.music_mood` 挑最匹配的，列出候选文件名让 EP 定夺
   - **音乐生成 API**：用 `music_gen`（ElevenLabs）或可用的 `suno_music`。先查注册表状态，工具不可用或额度耗尽就直接跳过（不要尝试后静默失败）
   - **无音乐可用**：在资产清单里清晰记录 `"music_status": "unavailable"` 及原因。不要静默产出无音乐的视频 —— EP 和用户应当知情
4. 时长至少覆盖全片时长。不足时合成阶段可循环
5. 确认音频文件存在于 `projects/<project>/assets/music/background_music.mp3`

**关键点**：音乐生成失败或不可用，立刻在资产清单里报告 —— 不要把问题留给合成阶段。

### 第 6 步：构建资产清单

把所有生成的资产汇总成清单：

```json
{
  "version": "1.0",
  "assets": [
    {
      "id": "narration-s1",
      "type": "audio",
      "subtype": "narration",
      "path": "assets/narration/s1.mp3",
      "source_tool": "tts_selector",
      "scene_id": "scene-1",
      "duration_seconds": 8.2,
      "cost_usd": 0.003
    },
    {
      "id": "img-scene-3",
      "type": "image",
      "path": "assets/images/scene-3-diagram.png",
      "source_tool": "diagram_gen",
      "scene_id": "scene-3",
      "cost_usd": 0.00
    },
    {
      "id": "music-bg",
      "type": "audio",
      "subtype": "music",
      "path": "assets/music/background.mp3",
      "source_tool": "music_gen",
      "duration_seconds": 62,
      "cost_usd": 0.05
    }
  ],
  "total_cost_usd": 0.053,
  "generation_summary": {
    "narration_sections": 5,
    "images_generated": 8,
    "diagrams_generated": 2,
    "music_tracks": 1
  }
}
```

### 生成提示词的前后自检

> 向任何生成工具（`image_selector`、`diagram_gen`、`video_selector`，甚至 `code_snippet` 的样式提示）发送提示词之前，按 CHAI 监督回路（“Building a Precise Video Language with Human-AI Oversight”，arXiv 2604.21718v2）做三步自检。成本很低（不增加工具调用），收益很大（避免废生成）。这对 `diagram_gen` 的 Mermaid 提示和 `image_selector` 的插画提示同样适用 —— 糟糕的解说视觉失败方式一样：缺主体、缺取景、含糊地“让它看起来有教育感”。
>
> **第 1 步 — 前置描述。** 按你今天会写的方式先写一版提示，别过度修饰，力求完整初稿。
>
> **第 2 步 — 评审。** 按 5 个维度打分（主体 / 主体运动 / 场景 / 空间取景 / 摄影机）。每个维度：
> - 是否已指明？没指明是故意的（如“摄影机不适用 —— Remotion 原生场景”“无主体运动 —— 静态图表”）还是疏漏？
> - 易混术语是否消歧？（dolly vs zoom、pan vs truck、鸟瞰 vs 航拍、鱼眼 vs 桶形、全景 vs 特写；图表则：flowchart vs sequence vs state、自上而下 vs 左右布局）
> - 情绪化形容词（“干净”“专业”“现代”）是否换成了视觉成因（无衬线字体、充足留白、单色加一点强调色）？
> - 多镜头提示：各镜头之间是否逐字固定了身份锚点？对反复出现的 `image_selector` 提示（同一角色或世界出现在多个场景），是否逐字指定了一致性锚点？
>
> **第 3 步 — 后置描述。** 补齐缺失维度、修正易混术语、替换主观措辞后重写。发送给生成工具的是这一版。
>
> 把（前置、评审、后置）三元组记录进资产元数据以备追溯。这与 CHAI 工作流一致，也留下可供审阅者审计的记录。

### 第 7 步：校验所有资产

**存在性检查：**

- [ ] 每个资产 `path` 在磁盘上存在
- [ ] 每个旁白小节都有对应音频文件
- [ ] 每个带 `required_assets` 的场景，资产都已生成
- [ ] 背景音乐文件存在

**质量检查：**

- [ ] 旁白时长在预期时间 ±15% 内
- [ ] 旁白资产记录了 `voice_performance.delivery_cues_applied`
- [ ] 已通过的 TTS 样例与批量结果使用同一 provider、音色与表现力设置
- [ ] 图像符合 playbook 风格（检查一致性锚点）
- [ ] 图表清晰完整
- [ ] 总成本在预算内

### 第 8 步：自评

打分（1-5）：

| 维度 | 问题 |
|-----------|----------|
| **完整性** | 每个场景的必需资产都齐了吗？ |
| **音频质量** | 旁白听起来自然、节奏对吗？ |
| **视觉一致性** | 所有图像看起来属于同一支视频吗？ |
| **预算遵从** | 总成本在批准的预算内吗？ |
| **Playbook 保真度** | 资产符合 playbook 风格指南吗？ |

任一项低于 3 分，先修再继续。

### 第 9 步：提交

对 asset_manifest 做 schema 校验，并通过 checkpoint 持久化。

### 制作中事实核查

素材生成过程中遇到不确定：

- 用 `web_search` 核对主体视觉准确性（比如这栋楼实际长什么样？）
- 用 `web_search` 在生成插画前找参考图
- 决策日志记录：`category="visual_accuracy_check"`

视觉准确性很重要。脚本提到具体地点、人物或物品，就先生成前核实它的真实外观。不要依赖 AI 模型的训练数据 —— 可能过时或错误。

## 常见坑

- **不查预算就生成**：永远先估算总成本。60 秒视频 15 张图能很快烧掉 $3+。
- **图像风格不一致**：每次 `image_selector` 调用彼此独立。用一致锚点，但按场景调整。把同一段风格前缀贴进每条提示，视频会显得机械重复。
- **忽略旁白时间**：10 秒小节若 TTS 出了 12 秒音频，剪辑阶段会很难办。务必核对时长。
- **忽略演绎提示**：有 `provider_text` 或 `delivery_cues` 却直接读原始文本会拉平语调。先应用语音表现契约。
- **缺发音指南**：“PostgreSQL”或“Kubernetes”没有明确指引就会被念错。
- **只重试一次就放弃**：图不匹配就针对性地细化提示词 —— 别拿同一提示反复重试。
- **用 AI 生成含精确文字的图像（CTA、商家名、联系方式）**：AI 图像模型经常幻觉出错误文本 —— 商家名错、电话错、拼写错。**凡文字必须逐字准确的场景，绝不用 AI 出图。** 改用 Remotion `text_card`。适用于：CTA 页、带商家名的标题卡、联系方式叠层、法律免责声明。场景计划里某场景 `type` 为 `text_card`，就不要为它生成图像 —— 跳过，让合成阶段用 Remotion 原生渲染。

## 不确定怎么做时

遇到拿不准的生成技法、provider 行为或提示模式：

1. **搜网** 找当前最佳实践 —— 模型和 API 变化快，agent 的训练数据可能过时
2. **查 `.agents/skills/`** 里已有的 Layer 3 知识（provider 专属提示指南、API 模式）
3. **都不管用**，就在 `projects/<project-name>/skills/<name>.md` 写一份项目级技能记录你的收获
4. **标注来源 URL**，让知识可追溯
5. **记录**到决策日志：`category: "capability_extension"`、`subject: "learned technique: <name>"`

对以下情况尤其重要：

- **视频生成提示** —— 模型对各版本专属词汇的响应会变
- **图像模型参数** —— FLUX、GPT Image、Imagen 的最佳设置不同且持续演进
- **音频 provider 特性** —— 声音克隆、音乐生成、TTS 各有模型专属最佳实践
- **Remotion 组件模式** —— 框架演进会带出新的合成技法

不要依赖陈旧知识。拿不准就先搜。

---

## 关卡提醒（强制）

本阶段以人工批准为关卡（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打 checkpoint，呈现摘要（Backlot 看板会渲染产物），然后**结束本轮**。不要在同一次回复里启动下一阶段。批准按关卡生效 —— 早前的“继续”不覆盖本关卡。
