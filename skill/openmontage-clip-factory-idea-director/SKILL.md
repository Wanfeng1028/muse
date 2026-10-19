---
name: openmontage-clip-factory-idea-director
version: "1.0.0"
description: 剪辑工厂的创意导演技能，负责把长视频源素材拆解为一个按质量排序的短视频片段组合，规划片段类型、产出目标、平台适配与筛选标准，适用于网络研讨会、访谈、直播回放等长内容的拆条策划。
metadata:
  license: AGPL-3.0
---

# 创意导演 — 剪辑工厂流水线

## 适用场景

当源素材是长视频，而交付目标是一批短视频时使用本流水线：网络研讨会片段、访谈切片、直播高光、主题演讲摘录、演示短片等。

你不是在规划一条视频，而是在规划一个经过排序的片段组合。

## 运行时选择（强制——需向用户呈现约束，不得私自决定）

锁定 `render_runtime = "remotion"`（用于带逐词字幕的合成片段）或 `"ffmpeg"`（用于纯拼接/裁剪、不做合成）。**本流水线在 Phase 1 阶段不接受 HyperFrames**——剪辑工厂依赖 Remotion 的逐词字幕烧录能力，HyperFrames 目前尚未对齐该能力。

依据 AGENT_GUIDE.md 中“同时呈现两种合成运行时（硬性规则）”：不得悄悄锁定 remotion。必须把约束抛给用户确认：“你的机器上 HyperFrames 也可用，但剪辑工厂依赖的 Remotion 字幕烧录能力 HyperFrames 尚未对齐，所以这里只能选 remotion——可以继续吗？” 在 `decision_log` 中记录该决定，类别为 `render_runtime_selection`，并把 hyperframes 记为被拒选项（`rejected_because: "caption-burn parity deferred on clip-factory"`）。

## 参考输入

- `docs/clip-factory-best-practices.md`
- `skills/creative/short-form.md`
- `skills/creative/video-editing.md`

## 流程

### 1. 理解素材与目标

先确定源素材形态：

- webinar（网络研讨会）
- interview（访谈）
- panel（圆桌讨论）
- keynote（主题演讲）
- stream（直播）
- customer story（客户故事）

再确定业务目标：

- awareness（认知）
- thought leadership（思想领导力）
- lead generation（线索获取）
- product education（产品教育）
- event recap（活动回顾）

### 2. 选择片段组合策略

一个好的批量应当混合多种片段类型，而不是反复抽取同一种调性。

常见的片段家族：

- `hook`：惊人论断或强力冷开场
- `insight`：有价值的要点或经验
- `story`：带情绪起伏的叙事瞬间
- `proof`：数据、案例研究、演示结果
- `opinion`：犀利观点、分歧、反主流立场

用 brief 的 metadata 定义这些家族之间的预期配比。

### 3. 设定务实的产出目标

参考区间：

- `15-30 分钟`：3-6 条强片段
- `30-60 分钟`：5-10 条强片段
- `60 分钟以上`：在源素材质量允许的前提下，8-15 条

不要为了凑整数而虚增片段数。少而精的批量胜过注水后的弱批量。

### 4. 抽取之前先做平台映射

提前规划平台适配：

- `9:16` 用于 Shorts、Reels、TikTok
- `1:1` 用于 LinkedIn 及更安全的动态流复用
- `16:9` 当涉及幻灯片、演示或需要横向上下文时

如果源素材的取景明显撑不过竖屏裁切，就在这一步写进 brief 的 metadata。

### 5. 撰写 brief

保持 schema 级 brief 简洁，把更丰富的批量计划放进 `brief.metadata`。

建议的 metadata 键：

- `source_type`
- `source_duration_seconds`
- `clip_target_range`
- `clip_families`
- `primary_platforms`
- `secondary_platforms`
- `selection_criteria`
- `known_visual_constraints`
- `distribution_goal`

### 6. 质量门

- 片段数量目标是否现实
- 平台组合是否匹配内容
- brief 是否在抽取开始前就定义了排序标准
- 智能体是否已经承认所有明显的重新取景限制

## 常见陷阱

- 先想数量再想质量。
- 默认任何源素材都能干净地产出竖屏片段。
- 把所有片段视为可互相替换，而不是有意做出差异化。
- 在没有定义“对本批次而言何为好”的情况下就动手抽取。

---

## 质量门提醒（强制）

本阶段需经人工审批（`human_approval_default: true`）。评审通过后：用 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染产出物），然后**结束本轮**。不得在同一回复里启动下一阶段。审批按门独立生效——此前的“继续”不代表本门已通过。
