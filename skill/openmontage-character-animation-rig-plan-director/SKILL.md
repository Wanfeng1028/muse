---
name: openmontage-character-animation-rig-plan-director
version: "1.0.0"
description: 将角色设计转换为可动画化的骨骼绑定方案与姿态库，适用于二维角色动画流水线的前期准备阶段，输出 rig_plan 与 pose_library 两个产物，为后续时间线编译与姿态插值提供结构化数据。
metadata:
  license: AGPL-3.0
---

# 骨骼绑定方案导演（Rig Plan Director）

## 目标

以 `character_design` 为输入，产出两份核心产物：

- `rig_plan`：描述每个角色的可动部件、枢轴、层级与约束。
- `pose_library`：为已确认场景定义命名姿态集合。

## 工作流程

1. **拆分角色为绑定部件**。对每个角色逐一列出：
   - 身体主体
   - 头部
   - 眼睛与瞳孔
   - 眉毛
   - 口型（嘴形集合）
   - 四肢 / 翅膀
   - 尾巴与附属饰品
   - 随身道具

2. **为每个可动部件定义枢轴（pivot）**。任何会移动或旋转的部件都必须有明确的旋转中心，否则后续插值会漂移。

3. **确定图层顺序**。前后遮挡关系必须在绑定阶段写清，渲染阶段不再动态推断。

4. **声明约束条件**。对关节角度设定上下限，防止肢体旋转到物理上不可能的位置。

5. **为已确认场景定义命名姿态**。姿态名需唯一，且与场景规划中的 beat 对齐。

6. **仅在以下情况定义动作循环（action cycle）**：
   - 该动作在片中至少被复用两次；
   - 或者该动作是叙事的核心支柱。

## 运行时模式

角色之间的差异应当被当作**数据**处理，而非代码分支。渲染器不需要为“老鼠”和“鸟”各写一套逻辑。

- 鸟可能拥有 `wing_left` 部件；
- 老鼠可能拥有 `tail` 部件；
- 但两者都汇入同一套姿态插值与时间线编译器。

绑定数据的结构必须统一，差异化字段通过命名与数据表表达。

## 质量检查清单

- [ ] 每个可动部件都分配了枢轴。
- [ ] 每个必需动作都有对应的姿态，或有一条程序化生成策略。
- [ ] 每个姿态都明确列出它改变了哪些部件。
- [ ] 高风险动作被显式标注出来，而不是藏在默认值里。

## 工具使用

使用 `svg_rig_builder` 起草绑定数据结构。

```bash
# 调用绑定构建工具，生成初步 rig 数据
svg_rig_builder --input character_design.json --output rig_draft.json
```

使用 `pose_library_builder` 起草初始姿态库。

```bash
# 生成初始姿态库草稿
pose_library_builder --rig rig_draft.json --scenes approved_scenes.json --output pose_library_draft.json
```

代理（agent）可以在写入检查点（checkpoint）之前，对这两个工具的输出进行修订。

---
