---
name: openmontage-cinematic-idea-director
version: "1.0.0"
description: 用于预告片、品牌片、情绪蒙太奇等以节奏与氛围为核心的影视化项目立项，梳理素材现实、情绪弧线、交付形态与配乐方案，适用于需要情感推进而非直接讲解的短片创作场景。
metadata:
  license: AGPL-3.0
---

# 创意总监（影视化流水线）

## 何时使用

当项目目标是预告片、品牌片、戏剧化蒙太奇，或任何以节奏、氛围、情绪递进为主要卖点的情绪化短片时，使用本阶段。

不要仅仅因为用户说了一句"要电影感"就启用本流水线。如果项目本质上是产品演示、讲解视频或素材再利用，应改走对应路线。

## 参考输入

- `docs/cinematic-best-practices.md`
- `skills/creative/cinematic.md`
- `skills/creative/storytelling.md`

## 流程

### 1. 判定素材现实

记录素材来源模式：

- `footage_only`
- `footage_plus_stills`
- `still_led`
- `generated_support`
- `mixed_montage`

同时判断交付是否强制要求动态画面，将结果以布尔值写入 `brief.metadata.motion_required`。

当视频的核心卖点依赖于运动镜头或动画构图、而非静态帧时，置 `motion_required = true`。典型情形包括：

- 科幻预告片；
- 电影感先导片；
- 动作或造势剪辑；
- 智能体/虚拟形象输出；
- 任何质量取决于生成视频片段的概念。

除非用户已提供，或当前环境确实能产出，否则不要假定已有库存素材、生成的 B-roll 或音乐。

### 2. 定义情绪弧线

用平实语言选定弧线：

- 紧张 → 揭示
- 惊叹 → 宏大
- 亲密 → 回馈
- 紧迫 → 化解
- 悬念 → 行动号召

简报要告诉后续阶段：这条片子希望让观众感受到什么，而不只是讲的是什么。

### 3. 确定交付形态

常见输出形态：

- `teaser`
- `trailer`
- `hero_brand_film`
- `mood_cut`
- `social_cutdown`

更细的规划信息存入 `brief.metadata`。

推荐元数据字段：

- `source_mode`
- `motion_required`
- `delivery_shape`
- `emotional_arc`
- `anchor_assets`
- `music_strategy`
- `generated_support_level`
- `aspect_ratio_plan`
- `rights_constraints`

### 4. 对方案做现实核查

如果用户素材薄弱且没有生成路径，要直说。电影感成品依然需要足够的画面或声音素材来撑起氛围。

若 `motion_required = true`，必须明确说明动态实现路径：

- 确认计划使用的片段生成服务商；
- 确认目标构图是否需要 Remotion；
- 若任一环节不可用或不稳定，将方案标记为 blocked，而不是悄悄改成静帧方案。

### 5. 配乐方案（强制）

影视化视频的成败很大程度取决于音频。**在用户确认简报之前，先把配乐情况摆到台面上。**

按以下顺序检查可用性：

1. **用户曲库**：查询 `registry.get_by_capability("music_library")` 并查看 `music_library/` 目录，列出可用曲目及其时长、情绪。
2. **免版税搜索**：查询 `registry.get_by_capability("music_search")`，报告可用服务商、授权限制及密钥要求。
3. **音乐生成 API**：查询 `registry.get_by_capability("music_generation")`，如实报告状态、配额、成本与质量取舍。
4. **自带曲目**：用户可从其他授权渠道把曲目放入 `music_library/`。

向用户明确列出选项：

```
MUSIC PLAN
├── 你的曲库: [N 首 / 空]
├── 免版税搜索: [服务商 / 不可用]
├── AI 生成: [服务商] — [可用/不可用] [成本]
└── 自带: 在素材阶段前把曲目放进 music_library/

选项:
  (a) 使用曲库曲目（哪一首？）
  (b) 搜索免版税服务商
  (c) 提供自己的曲目
  (d) 通过 API 生成（如可用）
  (e) 不带音乐继续（影视化项目不推荐）
```

把最终选择连同来源与路径/提示词写入 `brief.metadata.music_strategy`。

### 6. 质量门

- 素材现实明确；
- 简报写明动态是否为硬性要求；
- 情绪弧线具体；
- 输出形态与现有素材匹配；
- 配乐方案已敲定（选好来源或明确延后）；
- 之所以称其为影视化有明确理由，而不是只贴了个标签。

## 常见坑

- 把带黑边的普通剪辑说成电影感。
- 未检查工具就假定能生成插入镜头。
- 把动态主导的简报悄悄改成静帧主导的先导片。
- 规划预告片形态却没有揭示或回馈节点。

---

## 门禁提醒（约束）

本阶段以人工确认为门禁（`human_approval_default: true`）。评审通过后：
以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染产物），并**结束本轮回复**。不要在同一轮回复里启动下一阶段。
门禁按次生效——此前的一次"继续"不覆盖本次门禁。
