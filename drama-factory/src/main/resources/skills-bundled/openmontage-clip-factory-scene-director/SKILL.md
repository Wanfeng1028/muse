---
name: openmontage-clip-factory-scene-director
version: "1.0.0"
description: 为剪辑工厂流水线中已选片段规划取景与包装方案，确定各平台适配的画幅、安全区与版式一致性。适用于需要逐片设计首帧构图、字幕区、钩子文本区并输出可校验 scene_plan 产物的场景。
metadata:
  license: AGPL-3.0
---

# Scene Director · 剪辑工厂流水线

## 何时使用

当你需要为每一段已选中的片段规划如何在目标平台上取景与包装时，进入本阶段。此处的判断会直接证明或推翻某个片段的可用性。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | 产物校验 |
| 上游产物 | `state.artifacts["script"]["script"]`、`state.artifacts["idea"]["brief"]` | 已选片段与平台目标 |
| 工具 | `frame_sampler`、`scene_detect` | 画面抽帧检查与边界确认 |
| Playbook | 当前启用的风格 playbook | 版式语言与安全区定义 |

## 流程

### 1. 为每个片段挑选合适的画幅

不要一律套用 `9:16`。

- 人脸为主的裁切成立时用 `9:16`；
- 说话人与环境上下文同等重要时用 `1:1`；
- 涉及幻灯片、演示或多人并排宽度时用 `16:9`。

OpenMontage 目前还没有一等公民级别的自动重构图能力。若某个竖版裁切效果薄弱，就老老实实改用更安全的画幅，而不是假设裁切一定能成功。

### 2. 规划首秒构图

对每个片段明确以下要素：

- 观众在第 1 帧看到什么；
- 钩子文本可以安全出现的位置；
- 字幕可以放置的位置；
- 说话人是否需要推近（punch-in），还是原始取景已经足够。

### 3. 统一整批风格

借助 scene plan 锁定系列一致性：

- 顶部钩子区一致；
- 字幕区一致；
- 水印／品牌区一致；
- 下三分之一（lower-third）逻辑一致。

### 4. 将重构图细节写入 metadata

schema 本身是通用的，因此更丰富的版式备注放入 `scene_plan.metadata`。

推荐的 metadata 键：

- `clip_layouts`
- `safe_zones`
- `crop_variants`
- `speaker_positions`
- `platform_variants`

### 5. 用 scene 表示交付物

每个 scene 应对应一个片段变体或一个片段族交付物。`description` 保持人类可读，`required_assets` 用于声明钩子叠加层、下三分之一或品牌边框等素材。

### 6. 质量门

- 每个片段都具备平台感知的取景方案；
- 钩子区与字幕区不重叠冲突；
- 效果差的竖版裁切被诚实地降级处理；
- 整批一起渲染时视觉上保持一致。

## 常见坑

- 把宽画幅直接中心裁切，就号称完成了竖版优化。
- 只盯人脸，忽略幻灯片或屏幕共享内容。
- 让每个片段各自发明一套版式。
- 忘记首帧决定观众是否继续看下去。

---

## 关卡提醒（强制）

本阶段默认需要人工审批（`human_approval_default: true`）。评审通过后：
用 `status="awaiting_human"` 打检查点，展示摘要（Backlot 看板会渲染产物），然后**结束本轮**。不要在同一次回复里启动下一阶段。
审批是按关卡独立的——之前某次“继续吧”不覆盖本关卡。
