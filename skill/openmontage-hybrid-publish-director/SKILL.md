---
name: openmontage-hybrid-publish-director
version: "1.0.0"
description: 混合管线发布导演技能，负责把主片及其衍生版本整理成清晰的发布包，保留源素材与支撑素材的真实构成标注，并组织跨输出说明与平台文案映射。适用于混合视频交付物打包与发布的最终阶段。
metadata:
  license: AGPL-3.0
---

# 混合管线发布导演

## 适用场景

将混合管线的输出打包，使主片与其衍生版本保持条理清晰，源素材/支撑素材的构成一目了然。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["compose"]["render_report"]`、`state.artifacts["idea"]["brief"]`、`state.artifacts["script"]["script"]` | 最终输出与混合框架 |
| Playbook | 当前激活的风格 playbook | 语气一致性 |

## 流程

### 1. 区分主片与变体

将输出归类为：

- 主片剪辑
- 短形态衍生
- 格式变体
- 分章或情境变体

### 2. 在包装中保留源素材真实性

若项目以访谈、录屏或产品实拍作为锚点，元数据应如实反映这一点，而不是按纯生成类作品来包装。

### 3. 保存跨输出说明

推荐元数据键：

- `master_output`
- `derivative_outputs`
- `source_mix_notes`
- `platform_copy_map`

### 4. 质量关口

- 主片与变体标注清晰；
- 元数据与真实源素材构成一致；
- 导出文件夹按用途组织；
- 打包成果无需手动清理即可使用。

## 常见陷阱

- 隐藏哪一个才是主片。
- 把源素材主导的项目按通用生成类素材包装。
- 在各变体间丢失平台专属文案与标注。

---

## 关口提醒（具约束力）

本阶段以人工批准作为关口（`human_approval_default: true`）。评审通过后：
以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 面板会渲染 artifact），然后**结束本轮**。不要在同一次回复里启动下一阶段。
批准是按关口独立的——之前某一次的“继续”不覆盖本关口。
