---
name: openmontage-talking-head-publish-director
version: "1.0.0"
description: 口播视频流水线的发布阶段技能，基于渲染报告生成平台元数据、缩略图概念与导出包，适用于成片完成后准备发布物料与发布记录的收尾环节。
metadata:
  license: AGPL-3.0
---

# Publish Director — Talking Head Pipeline

## When to Use

You have a render report with the final video. Your job is to prepare metadata, thumbnails, and an export package for publishing.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact validation |
| Prior artifacts | Render report, Brief | Video file and context |

## Process

### Step 1: Generate Metadata

Create platform-specific metadata:
- **Title**: Based on the brief's title and hook
- **Description**: Summary of the content with relevant keywords
- **Tags**: Derived from brief's key_points
- **Chapters**: From script section timestamps

### Step 2: Thumbnail Concept

Describe or generate a thumbnail:
- Extract a compelling frame from the footage (if frame_sampler available)
- Add text overlay concept (title or key stat)

### Step 3: Package Export

Create the export directory:
- Video file
- Metadata JSON
- Description text file
- Chapter markers
- Thumbnail concept

### Step 4: Build Publish Log

Document the publish event with platform, status (draft), and export path.

### Step 5: Self-Evaluate

| Criterion | Question |
|-----------|----------|
| **Metadata quality** | Is the title compelling and description informative? |
| **Completeness** | Is the export package complete? |

### Step 6: Submit

Validate the publish_log against the schema and persist via checkpoint.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
