---
name: openmontage-character-animation-script-director
version: "1.0.0"
description: 将角色动画剧本写成可用姿态表演的节拍，而非单纯旁白，锁定音频架构并输出带元数据的 script 产物，适用于绑定角色动画的编剧阶段。
metadata:
  license: AGPL-3.0
---

# 剧本导演（Script Director）

## 目标

剧本要写成**可表演的动画节拍**，而不是一段旁白配画面。

## 工作流程

1. **锁定音频架构**。四选一，开写前必须确定：
   - 纯音乐
   - 旁白
   - 角色对白
   - 旁白 + 角色音效 / 对白

2. **把故事拆成可以用姿态表演的节拍**。每个节拍应当对应一组明确的姿态变化。

3. **为每个节拍写明视觉上发生了什么变化**：
   - 情绪
   - 视线
   - 身体姿态
   - 道具交互
   - 镜头
   - 环境

## 写作规则

- 优先使用短小的视觉节拍，配合可读的停留（hold）。
- 除非已获批准，避免需要大量独立手绘姿态的动作。
- 对白要足够短，以便用口型近似（mouth-shape approximation）表现。
- 无声或纯音乐驱动的场景，需要更强的肢体表演注释。

## 输出说明

在 `script` 产物的 metadata 中，必须包含：

- `audio_architecture`
- `character_beats`
- `required_emotions`
- `required_actions`

```json
{
  "audio_architecture": "narrator_plus_dialogue",
  "character_beats": [],
  "required_emotions": [],
  "required_actions": []
}
```

以上字段用于下游绑定与场景规划阶段反查需求，缺一不可。

---

## 关口提醒（强制约束）

本阶段以人工审批为关口，`human_approval_default: true`。

评审通过后：

- 以 `status="awaiting_human"` 写入检查点；
- 呈现摘要（Backlot 看板会渲染产物）；
- **结束本轮回复**。

不得在同一轮回复中启动下一阶段。审批按关口独立计算——之前某一次“继续”不覆盖当前关口。
