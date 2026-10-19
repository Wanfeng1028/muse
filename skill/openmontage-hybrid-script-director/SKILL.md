---
name: openmontage-hybrid-script-director
version: "1.0.0"
description: 混合管线中的剧本导演技能，把故事分配到源素材主导节拍与辅助主导节拍之间，并决定何处由源素材承载信息、何处用辅助素材澄清。适用于混合结构剧本创作与事实核查。
metadata:
  license: AGPL-3.0
---

# 混合管线 · 剧本导演

## 适用时机

本阶段要把故事映射到源素材主导的节拍与辅助主导的节拍之上。你在此决定：哪些部分由源素材传递信息，哪些部分由辅助资产来澄清。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/script.schema.json` | 校验剧本产物 |
| 前置产物 | `state.artifacts["idea"]["brief"]` | 提供锚定媒介与交付物组合 |
| 工具 | `transcriber`、`scene_detect`、`audio_enhance` | 可选的源素材分析 |

## 流程

### 1. 标注源素材主导与辅助主导的节拍

对每个段落标明其承载方式：

- 由源对白或源画面承载
- 由旁白承载
- 由图示或叠加层承载
- 仅由文字承载

### 2. 当源语音优于改写时，直接用源语音

如果提供的素材中已经包含有力的台词，用 `transcriber` 提取并保留其真实感。不要用多余的旁白替换掉好的源素材。

### 3. 辅助素材只用于澄清

辅助主导的节拍应回答以下问题：

- 什么是画面中看不到的
- 什么需要概括
- 什么需要强调
- 面向不同平台时什么需要调整

### 4. 用元数据表达结构

推荐使用的元数据键：

- `anchor_sections`
- `support_sections`
- `narration_sections`
- `required_support_assets`

### 5. 质量门

- 源素材主导节拍有清晰标注
- 辅助主导节拍均有合理依据
- 剧本不依赖虚假或不可得的资产而未加说明
- 该结构能够产出预期的交付物

## 制作中的事实核查

剧本写作过程中若遇到不确定之处：
- 用 `web_search` 核实事实性主张，再写入剧本
- 用 `web_search` 查找参考图片以保证视觉准确
- 在决策日志中记录核查：`category="visual_accuracy_check"`

剧本中每一条事实性主张都应可追溯到 `research_brief`。
若你写入了一条不在研究材料中的主张，需补充研究并加上来源。
不要杜撰统计数据、日期或归属。

## 常见陷阱

- 把强有力的源对白改写成更弱的旁白。
- 在画面本身已讲清楚的地方硬加图示或卡片。
- 把无支撑的需求藏到资产生成阶段才暴露。

## 命令模板

```bash
# 转写源素材语音，为节拍划分与台词提取提供文本依据
transcriber --input source.mp4 --lang zh --out transcript.json

# 检测源素材镜头切点，辅助节拍边界判断
scene_detect --input source.mp4 --threshold 0.4 --out cuts.json

# 对源音频做增强，提升语音清晰度后再转写
audio_enhance --input source.mp4 --out enhanced.wav
```

## 验收要点

- 每个段落的承载方式均已标注。
- 辅助节拍的理由已在剧本中说明。
- 事实性主张均可追溯到研究简报。
- 结构可支撑目标交付物。

---

## 门禁提醒（强制）

本阶段以人工审批为门禁（`human_approval_default: true`）。审核通过后：
以 `status="awaiting_human"` 做 checkpoint，呈现摘要（Backlot 看板会渲染产物），然后**结束本轮**。
不要在同一响应中启动下一阶段。审批按门禁独立生效——此前的"继续"不覆盖本门禁。
