---
name: openmontage-character-animation-executive-producer
version: "1.0.0"
description: 角色动画流水线的总制片人技能，用于统筹可复用动画角色类交付物的全流程编排与治理，适用于卡通短片、吉祥物讲解、音乐驱动角色场景、简单角色对话及参考风格本地动画等需要角色表演的项目。
metadata:
  license: AGPL-3.0
---

# 角色动画流水线 · 总制片人

## 何时启用本流水线

当交付物依赖**可复用的动画角色**时，走本流水线。典型场景包括：

- 卡通短片
- 吉祥物式讲解视频
- 以音乐驱动的角色场景
- 简单角色之间的对话段
- 受参考素材启发的本地动画

**不适用**的情况：

- 没有表演需求的一次性动态图形 → 改走 `animation` 流水线
- 虚拟形象口型同步播报 → 改走 `avatar-spokesperson` 流水线

## 契约

本流水线产出的是**本地、确定性**的角色动画。严禁用静帧位移冒充角色表演。如果当前骨架、资产或运行时无法实现所需的角色运动，必须显式抛出阻塞项，而不是偷偷降级。

## 阶段顺序

1. `research` —— 调研参考、技法与可行性
2. `proposal` —— 给出概念方案、运行时选项、成本、音乐计划、样片计划
3. `script` —— 撰写便于动作化的节拍与对白/旁白
4. `character_design` —— 定义角色、剪影、情绪、动作
5. `rig_plan` —— 定义部件、枢轴、图层、约束、姿势
6. `scene_plan` —— 把故事节拍映射到角色场景
7. `assets` —— 制作或采集角色部件、背景、道具、音频
8. `edit` —— 编译带时间轴的动作剪辑
9. `compose` —— 通过已批准的运行时渲染并执行 QA
10. `publish` —— 打包最终产物

## 治理规则

- 在 `proposal` 之前必须先跑 registry 预检。
- 若 Remotion 与 HyperFrames 均可用，锁定 `render_runtime` 之前必须把两者都呈现给用户。
- 在批量生成全部资产之前，先产出 10–15 秒样片。
- 角色之间的差异应体现在骨架数据中，不得写成一次性的代码分支。
- 每个生成式或运行时代写的资产都要列出所读取的 Layer 3 技能。
- 交付前需经过 `character_animation_reviewer` 以及最终 `final_review`。

## 打回触发条件

出现以下情况必须打回重做：

- `character_design` 缺少必需动作或情绪跨度不足
- `rig_plan` 中需要活动的部件没有对应枢轴
- `pose_library` 里没有可读的表演姿势
- `action_timeline` 包含骨架无法渲染的动作
- `compose` 使用了 `proposal` 阶段未批准的运行时

## 关键检查清单

- 是否已完成 registry 预检
- 是否已明确 `render_runtime` 并获得用户批准
- 样片是否已获批
- 资产清单是否完整且注明来源
- Layer 3 技能引用是否齐全
- 是否已通过 `character_animation_reviewer` 与 `final_review`
