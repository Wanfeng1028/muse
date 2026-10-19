---
name: openmontage-character-animation-scene-director
version: "1.0.0"
description: 为绑定角色动画规划逐场方案，确保每个场景在骨骼动画下可行，产出符合共享 schema 的 scene_plan，并强制在人工审批关口停下等待确认。
metadata:
  license: AGPL-3.0
---

# 场景导演（Scene Director）

## 目标

产出 `scene_plan`，其中每个场景都必须对绑定角色动画而言是可执行的——不能出现绑定系统无法表现的动作或视角。

## 场景规划字段

每个场景需要包含以下字段：

- 角色 ID 列表
- 情绪节拍（emotional beat）
- 动作序列
- 镜头与取景
- 背景
- 道具
- 特效
- 所需资产
- 转场说明

对于有绑定角色表演的场景，使用 `type: "character_scene"`。

角色特有的表演细节一律存放在 `character_actions` 字段中。**不要**把逐场景的表演数据塞进任意 metadata，因为共享的 `scene_plan` schema 会拒绝未知的逐场景字段。

## 复杂度预算

宁少而精，不求多而杂。推荐的单场景节拍结构：

1. 一个建立镜头（establish）
2. 一个动作节拍（action beat）
3. 一个反应节拍（reaction beat）
4. 一个收束节拍（resolution beat）

除非用户明确批准，否则避免出现需要大量独立视角或复杂肢体接触的场景。

---

## 关口提醒（强制约束）

本阶段以人工审批为关口，`human_approval_default: true`。

评审通过后：

- 以 `status="awaiting_human"` 写入检查点；
- 呈现摘要（Backlot 看板会渲染产物）；
- **结束本轮回复**。

不得在同一轮回复中启动下一阶段。审批按关口独立计算——之前某一次“继续”不覆盖当前关口。

---
