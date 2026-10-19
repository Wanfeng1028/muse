---
name: openmontage-podcast-repurpose-script-director
version: "1.0.0"
description: 播客二次创作流水线的剧本导演技能，产出转写文本、说话人归属、高光集合与章节结构，适用于后续所有阶段的素材基础构建。
metadata:
  license: AGPL-3.0
---

# 剧本导演 · 播客二次创作流水线

## 何时使用

本阶段负责建立转写真相、说话人归属、高光集合与章节结构，后续每个阶段都依赖这些产物。

## 前置条件

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/script.schema.json` | 校验产物结构 |
| 上游产物 | `state.artifacts["idea"]["brief"]` | 交付物组合与素材真实信息 |
| 工具 | `transcriber`、`audio_enhance` | 带说话人分离的转写与音频清理 |

## 流程

### 1. 保护转写质量

若源音频质量较差，在转写前或转写同时使用 `audio_enhance`。说话人分离质量直接影响引言归属与切片质量。

```bash
# 先增强音频再转写，提升说话人分离准确度
audio_enhance --input raw_audio.wav --output clean_audio.wav
```
说明：对原始音频做降噪与均衡处理，输出适合转写的干净音轨。

### 2. 生成带说话人信息的转写

对多说话人节目而言，说话人分离不是可选项。尽早在 `script.metadata` 中记录更详细的分离信息。

建议的元数据键：

- `speaker_map`
- `transcript_path`
- `chapter_candidates`
- `highlight_candidates`
- `rejected_highlights`

```bash
# 执行带说话人分离的转写
transcriber --input clean_audio.wav --diarize --output transcript.json
```
说明：开启说话人分离，输出带时间戳与说话人标签的转写文件。

### 3. 对高光时刻排序

从整集转写中找出：

- 简洁的洞见
- 出人意料的论断
- 情绪高点
- 争论片段
- 实用建议
- 令人印象深刻的措辞

每一条高光都要评估：

- 是否可独立成篇
- 钩子强度
- 署名可信度
- 平台适配度

### 4. 为长版包装构建章节

如果用户需要整集陪伴式产物，此时就要标出话题切换点。它们会成为章节标记，也是后续的视觉转场节点。

### 5. 保持 Schema 干净

用 `sections[]` 承载面向生产的结构化分段，把更丰富的高光清单放进 metadata。

### 6. 质量门

- 说话人署名可信；
- 高光集合足以支撑所请求的交付物；
- 弱切片被拒绝，而不是用来凑数；
- 章节标记能干净地覆盖长版对话。

## 制作中事实核查

在撰写剧本过程中遇到不确定时：

- 用 `web_search` 在写入剧本前核实事实性论断；
- 用 `web_search` 查找参考图像以保证视觉准确；
- 在决策日志中记录核查：`category="visual_accuracy_check"`。

剧本中的每条事实性论断都应能追溯到 `research_brief`。若你写下研究里没有的论断，需补充研究并附上来源。不要编造统计数据、日期或署名。

## 常见陷阱

- 把改变"谁说了这句话"的说话人分离错误当成小事。
- 选择那些需要过多前文铺垫才能理解的切片。
- 让整批产出过度集中在节目的某一个段落。

---

## 门禁提醒（强制）

本阶段以人工审批为门（`human_approval_default: true`）。评审通过后：
以 `status="awaiting_human"` 打检查点，展示摘要（Backlot 面板会渲染产物），
并**结束本轮回复**。不要在同一次回复里启动下一阶段。
审批按门独立生效——早先的"可以继续"不覆盖当前这道门。
