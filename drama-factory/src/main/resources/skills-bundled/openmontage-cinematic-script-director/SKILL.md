---
name: openmontage-cinematic-script-director
version: "1.0.0"
description: 为电影感作品搭建节拍图、台词选段与标题卡文案的技能，适用于以节奏和揭示结构为核心的短片剧本设计阶段。
metadata:
  license: AGPL-3.0
---

# 剧本导演（电影感流水线）

## 何时使用

本阶段为电影感作品搭建节拍图、精选台词、标题卡文案与揭示结构。你在塑造节奏，而不是写一篇密实的解说稿。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/script.schema.json` | 校验产物结构 |
| 前置产物 | `state.artifacts["proposal"]["proposal_packet"]` | 情感弧线与事实来源 |
| 工具 | `transcriber`、`scene_detect` | 可选的台词挖掘与素材审阅 |

## 流程

### 1. 先搭节拍图

使用简单结构：

- 钩子
- 升级
- 揭示
- 落地

若作品更长，可在中点加一次转折。不要让结构变成论文体。

### 2. 谨慎使用台词

若源素材中有语音，可用 `transcriber` 找出：

- 能独立成立的强句
- 带情绪的短语
- 简短的宣言
- 揭示性短语

若没有可用的台词，就让剧本走标题卡或旁白路线，并在元数据中说明。

### 3. 标题卡要短

标题卡文案应像预告片：

- 字更少
- 对比更强
- 留白更多
- 时点更准

### 4. 把节拍事实存进元数据

推荐使用的元数据键：

- `beat_map`
- `dialogue_selects`
- `title_card_copy`
- `music_turns`
- `silence_windows`

### 5. 质量门

- 节拍图升级清晰
- 台词与标题卡不重复解释同一件事
- 揭示落点独特
- 收尾给观众留下一个最终感受或行动

### 制作中事实核验

若在写剧本时遇到不确定：
- 用 `web_search` 核实事实性断言，再写入剧本
- 用 `web_search` 查找参考图像以保证视觉准确
- 在决策日志中记录核验：`category="visual_accuracy_check"`

剧本中的每一条事实断言都应能追溯到 `research_brief`。若你写入研究里没有的断言，请补充调研并加上来源。不要杜撰统计数据、日期或归属。

## 常见坑

- 写整段解释性文字而非节拍。
- 标题卡用得过多。
- 过早亮出最好的时刻。

---

## 关卡提醒（强制）

本阶段以人工批准为关卡（`human_approval_default: true`）。评审通过后：
以 `status="awaiting_human"` 做 checkpoint，呈现摘要（Backlot 看板会渲染产物），并**结束你的回合**。不要在同一回复里开启下一阶段。批准按关卡生效——早前的“可以继续”不覆盖本关卡。
