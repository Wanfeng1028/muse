---
name: openmontage-character-animation-character-design-director
version: "1.0.0"
description: 角色动画管线的角色设计环节，产出一小组轮廓清晰、角色定位与情绪动作明确的角色设定，适用于确定演员阵容、视图需求与道具附件的场景。
metadata:
  license: AGPL-3.0
---

# 角色设计导演（角色动画管线）

## 目标

产出 `character_design`：一个规模精简的角色阵容，要求剪影清晰、角色定位明确、情绪与动作可辨识，并给出风格锚点。

> **需要手绘墨线“涂鸦”角色？**（一根会自己画出来的火柴人/铅笔人，然后走路、跳舞、挥手、跳跃）→ 使用 **Ink Puppet** 系统：`skills/creative/ink-theater.md` 与 `ink-theater/README.md`。该骨骼与身体比例无关，通过 `InkPuppet.choreograph([{clip:'wave'},{clip:'twist'},…])` 播放**真实动捕**片段——片段名来自 `ink-theater/mocap/catalog.json`（12 段 CMU 来源动作）；代理只挑选具名动作，**绝不手动调参动作**；用 `node ink-theater/mocap/add-motion.mjs` 追加动作。命令：`/ink-art`。

## 处理流程

1. 列出每个角色的 `id`、角色定位、体型与风格。
2. 找出故事所需的最小情绪范围。
3. 找出故事所需的最小动作清单。
4. 确定所需视图：正面、3/4、侧面、背面。最小可用版本只保留一到两个视图。
5. 标注挂在角色身上的道具，如围巾、羽毛、包、眼镜。

## 约束

- 一到两个角色是最小可用版本的理想规模。
- 动物角色需要物种专属部件与动作循环。
- 视图越多，资产与姿势的需求量成倍增长。
- 不要设计超出已批准时长能容纳的姿势数量。

## 工具使用

用 `character_spec_generator` 生成结构化草稿。只有在视觉风格与角色表要求都明确之后，才使用 `image_selector`。调用图像生成之前，从注册表读取该工具的第三层技能。

## 质量门槛

只有当动画师或工具能据此推断出必须存在哪些部件、表情与动作时，角色设计才算就绪。

---

## 闸门提醒（强制）

本阶段需人工审批（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，展示摘要（Backlot 看板会渲染该产物），然后**结束本轮回复**。不要在同一个回复里启动下一阶段。审批按闸门逐次进行——早先的一句“继续”不覆盖本闸门。
