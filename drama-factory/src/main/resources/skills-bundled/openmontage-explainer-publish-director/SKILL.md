---
name: openmontage-explainer-publish-director
version: "1.0.0"
description: 解说视频发布阶段的总监技能，负责根据渲染报告生成 SEO 元数据、缩略图方案、章节标记，并打包导出目录与发布日志，适用于成片完成后面向各平台分发前的封装环节。
metadata:
  license: AGPL-3.0
---

# 发布总监 — 解说视频流水线

## 何时启用

你是生成式解说视频的发布负责人。手上有一份包含最终视频文件的 `render_report`。你的职责是让视频准备好分发：生成 SEO 元数据、制作缩略图、打包导出、记录发布事件。

这是好视频触达观众的一步。没有恰当的元数据与包装，再好的内容也会被埋没。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/publish_log.schema.json` | 产物校验 |
| 上游产物 | `state.artifacts["compose"]["render_report"]`、`state.artifacts["proposal"]["proposal_packet"]`、`state.artifacts["research"]["research_brief"]` | 视频文件与原始提案 |
| Playbook | 当前生效的风格 playbook | 缩略图视觉风格 |

## 流程

### 第 1 步：汇集上下文

收集元数据所需的全部信息：
- **提案包**：标题、钩子、要点、目标平台、调性
- **渲染报告**：输出路径、时长、分辨率
- **脚本**：用于描述与章节的分段摘要

### 第 2 步：生成 SEO 元数据

**标题**（YouTube 上限 60 字符）：
- 含提案包里的主关键词
- 以钩子或数字开头
- 避免标题党，但要有吸引力
- 例：「向量数据库 60 秒讲清」优于「关于向量数据库」

**描述**（前 150 字符最关键——会出现在搜索结果中）：
- 首行：用主价值主张重述钩子
- 正文：覆盖的关键话题，自然嵌入相关关键词
- 章节：为每个主要分段（来自脚本）加时间戳
- 行动号召：订阅/点赞/关注
- 链接：视频中提到的相关资源

**标签/关键词**（因平台而异）：
- 从提案包 key_points 派生 5-10 个具体标签
- 泛与专混合：「机器学习」+「向量数据库教程」
- 包含主题、格式（「解说」）及相关词

**话题标签**（社交平台）：
- 3-5 个相关话题标签
- 热门与垂类混合

### 第 3 步：生成缩略图方案

描述一张缩略图，需满足：
1. 沿用 playbook 的视觉风格
2. 视觉上呈现视频核心概念
3. 含 3-5 个词（钩子或关键数据）
4. 高对比、小尺寸下可读
5. 文字使用 playbook 强调色

```json
{
  "thumbnail": {
    "concept": "Split screen: left side shows slow SQL query (red X), right shows fast vector search (green check). Large text: '100x FASTER'",
    "text_overlay": "100x FASTER",
    "style_notes": "Use playbook accent colors, bold Inter font, dark background"
  }
}
```

*注：实际缩略图生成走 image_selector（如可用），否则仅作为人工制作的方案。*

### 第 4 步：创建章节标记

从脚本分段生成 YouTube 风格章节：

```
0:00 - Introduction
0:15 - What are Vector Databases?
0:45 - How Embeddings Work
1:20 - The Search Algorithm
1:55 - Real-World Examples
2:30 - When to Use Vector DBs
```

每个章节映射到脚本分段的 `start_seconds`。

### 第 5 步：打包导出

用 `export_bundle` 工具（能力 `publish`）确定性地完成打包——传入最终 `video_path`（来自 `render_report`）、`title`，以及你准备好的元数据（`description`、`tags`、`hashtags`、`chapters`，可选 `subtitles_path` 与 `thumbnail_path`/`thumbnail_concept`）。它会布置导出目录、写入元数据文件，并返回一份 schema 合法的 `publish_log`（`status: "exported"`），位于 `data["publish_log"]`，由你持久化为阶段产物。

产出结构如下：

```
exports/
  <project_name>/
    video/
      output.mp4            # Final rendered video (subtitles.srt alongside if provided)
    metadata/
      metadata.json         # All SEO metadata
      chapters.txt          # Chapter markers
      description.txt       # Ready-to-paste description (+ chapters)
      tags.txt              # One tag per line
    thumbnails/
      concept.json          # Thumbnail concept (or the copied thumbnail image)
```

`export_bundle` 是本地、离线的打包器——它不上传。联网的发布器（例如 YouTube 上传器）会是另一个 `publish` 能力供应商。

### 第 6 步：构建发布日志

`export_bundle` 已经返回 schema 合法的 `publish_log` 于 `data["publish_log"]`——直接持久化它，不要手工拼。**不要**额外添加条目字段（schema 设了 `additionalProperties: false`，只允许 `platform`、`status`、`url`、`video_id`、`visibility`、`export_path`、`timestamp`、`metadata_used`、`error`）。其返回形如：

```json
{
  "version": "1.0",
  "entries": [
    {
      "platform": "youtube",
      "status": "exported",
      "export_path": "projects/vector-db-explainer/exports",
      "timestamp": "2026-01-15T10:30:00+00:00",
      "metadata_used": {
        "title": "Vector Databases Explained in 60 Seconds",
        "description": "What vector databases are and when to use them.",
        "hashtags": ["#ai", "#vectordb"],
        "chapters": [{ "start_seconds": 0, "title": "Introduction" }]
      }
    }
  ]
}
```

### 第 7 步：自评

打分（1-5）：

| 维度 | 问题 |
|------|------|
| **SEO 质量** | 标题和描述在该主题下会有好的排名吗？ |
| **描述完整度** | 描述是否包含章节、CTA 和关键词？ |
| **缩略图方案** | 这张缩略图能在信息流中脱颖而出吗？ |
| **导出包** | 创作者需要的东西在导出目录里都齐了吗？ |
| **平台契合** | 元数据是否为目标平台量身定制？ |

任何一项低于 3 分，修正。

### 第 8 步：提交

将 publish_log 按 schema 校验，通过 checkpoint 持久化。

## 常见坑

- **标题太泛**：「关于 X 的视频」永远输给「X 60 秒讲清」。要具体、要吸引。
- **没有章节**：YouTube 会奖励带章节的视频。务必包含。
- **描述堆砌关键词**：先为人写，再为搜索引擎写。用自然语言把关键词织进去。
- **忘记 CTA**：每条描述都应以行动号召收尾。
- **平台格式错配**：YouTube 描述与 TikTok 文案不同。按目标平台调整。

---

## 门禁提醒（强制）

本阶段以人工批准为门禁（`human_approval_default: true`）。审阅通过后：
以 `status="awaiting_human"` 打 checkpoint，展示摘要（Backlot 看板会渲染产物），然后**结束本轮回复**。不要在同一个回复里启动下一阶段。
批准是按门禁逐次生效的——之前的「继续吧」不覆盖本门禁。
