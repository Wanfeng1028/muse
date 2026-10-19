---
name: openmontage-character-animation-edit-director
version: "1.0.0"
description: 角色动画管线的剪辑环节，产出 edit_decisions 与 action_timeline，把场景节拍转成带时间的角色动作，适用于设计表演节奏与动作映射的场景。
metadata:
  license: AGPL-3.0
---

# 剪辑导演（角色动画管线）

## 目标

产出 `edit_decisions` 与 `action_timeline`。

## 处理流程

1. 从已批准的提案中沿用 `render_runtime`。
2. 把场景节拍转换为带时间的角色动作。
3. 在合适处补上预备、停顿、动作与跟随。
4. 让口型/手势节拍对齐台词或音乐。
5. 保持动作密度可读，不要堆叠。

## 时间模式

多数表演节拍需要：

```text
预备 -> 动作 -> 停顿/反应 -> 落定
```

不要全程持续动画。停顿本身就是表演的一部分。

## 工具使用

先用 `action_timeline_compiler` 跑第一遍，若表演或节奏偏弱，再回头修改时间线。

## 质量门槛

每个场景都有带时间的动作。每个动作都能映射到渲染器可理解的姿势、动作循环或程序化特效。
