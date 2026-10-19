---
name: openmontage-character-animation-asset-director
version: "1.0.0"
description: 角色动画管线中的资产统筹环节，负责产出 asset_manifest，涵盖角色部件、背景、道具、音频、音乐与预览件，适用于开工前清点并生成动画所需素材的场景。
metadata:
  license: AGPL-3.0
---

# 资产导演（角色动画管线）

## 目标

产出 `asset_manifest`，把角色部件、背景、道具、音频、音乐以及预览件登记齐全，作为后续合成的输入。

## 第三层技能闸门

动手撰写或生成动画资产之前，先读取相关的第三层技能文档：

- `character-rigging`
- `svg-character-animation`
- `pose-library-design`
- 使用 p5/canvas 特效时读 `canvas-procedural-animation`
- 评审前读 `character-animation-qa`
- 涉及 GSAP/Remotion 时读 `gsap-core`、`gsap-timeline`、`gsap-react`
- 做 Remotion 渲染时读 `remotion` 与 `remotion-best-practices`
- 做 HyperFrames 时读 `hyperframes` 与 `hyperframes-cli`

在调用图像、TTS、音乐生成之前，从注册表里读取对应工具的 `agent_skills`。

## 资产目录结构

角色资产写入：

```text
projects/<project-name>/assets/characters/<character-id>/
```

并在其下建子目录：

```text
parts/
poses/
previews/
```

生成的背景放在：

```text
projects/<project-name>/assets/backgrounds/
```

## 处理流程

1. 只产出或采集 `rig_plan` 要求的部件，不多做。
2. 每个可动部件独立成件，不要合并。
3. 部件保留透明背景。
4. 记录提示词、随机种子、供应商与模型名称。
5. 先做一个小尺寸预览，再全量铺开资产。

## 质量门槛

`rig_plan` 引用的所有部件必须在合成前存在。缺件属于阻塞项，除非动作时间线已经移除了依赖该部件的动作。

---

## 闸门提醒（强制）

本阶段需人工审批（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，展示摘要（Backlot 看板会渲染该产物），然后**结束本轮回复**。不要在同一个回复里启动下一阶段。审批按闸门逐次进行——早先的一句“继续”不覆盖本闸门。
