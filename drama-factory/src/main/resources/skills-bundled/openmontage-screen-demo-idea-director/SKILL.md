---
name: openmontage-screen-demo-idea-director
version: "1.0.0"
description: 屏幕演示流水线的创意导演技能，负责判断采用真实录屏还是合成终端、分析源素材、确定演示原型与交付意图，并产出带制作细节的 brief。适用于需要把用户需求转成可执行演示视频方案的立项阶段。
metadata:
  license: AGPL-3.0
---

# 创意导演 — 屏幕演示流水线

## 运行时选择（强制：列出所有可行选项）

在创意阶段就要和制作模式一起锁定 `render_runtime`。可行运行时取决于模式：

| 制作模式 | 可行运行时 |
|---------|-----------|
| `real_capture`（真实录屏） | `remotion`（首选，便于叠加浮层）、`ffmpeg`（纯拼接/裁剪） |
| `synthetic_terminal`（Remotion `TerminalScene`） | 仅 `remotion` |
| `synthetic_ui`（自定义 HTML 界面演示） | `remotion` 或 `hyperframes` —— 真实二选一，两者都要列出 |

依据 AGENT_GUIDE.md 中「必须同时呈现两个合成运行时（硬性规则）」：当模式允许多种运行时且机器上两者都可用（查 `video_compose.get_info()["render_engines"]`），必须把两者连同针对本简报的分析一并呈现给用户，给出推荐，等待确认。禁止悄悄用默认值。当模式本身限定了选择（如 `synthetic_terminal` 只能用 Remotion），要明确告知用户这一约束，而不是默默锁定。每个选择都要记录到 `decision_log` 的 `render_runtime_selection` 下，包含所有被考虑过的选项。

## 适用时机

只要交付物是屏幕录制风格的演示，就走这条流水线。共有**两种制作模式**，在 brief 里选定其一：

| 模式 | 源素材 | 何时选它 |
|------|-------|---------|
| **`real_capture`** | 通过 `screen_recorder`、`cap_recorder` 或 `playwright-recording` 采集的真实录屏（MP4） | 真实应用界面、实时行为、浏览器流程、IDE 插件，或用户明确要求用自己的屏幕 |
| **`synthetic_terminal`** | 无，不做采集。你为 Remotion 编写 `terminal_scene` 片段 | CLI / 终端 / 安装流程 / make 目标 / git clone / API key 配置 —— 一切命令与输出都可预测的脚本化场景 |

**判断问题：**「我能在开拍前预测每一条命令及其输出吗？」能 → 合成；不能 → 真实采集。

**把模式记进 `brief.metadata.production_mode`。** 素材导演读这个字段来决定是做采集+浮层素材，还是做一份配合旁白节奏的 `steps` 列表。

若选 `synthetic_terminal`，继续之前还要读 `.agents/skills/synthetic-screen-recording/SKILL.md` —— 里面写明了那条曾毁掉一次演示渲染的节奏规则（命令在 40% 的场景时长里全跑完，剩下 60% 终端冻在那里）。

本阶段的任务是把用户需求转成清晰的流程性视频方案。主交付物是一份 schema 合法的 `brief`，流水线专属细节放在 `brief.metadata` 里。

## 工作原则

屏幕演示的最佳实践高度一致：

- 讲流程优先于讲理论，
- 范围收敛到一条工作流或一个结果，
- 让旁白对应可见动作，
- 注意力引导要克制，
- 可读性优先于风格。

参考文档：
- `docs/screen-demo-best-practices.md`
- `skills/creative/screen-recording.md`

## 流程

### 1. 检查源素材

写 brief 之前先用分析工具：

- `frame_sampler` 取代表性帧，并在可能的关键时刻附近密集采样
- `scene_detect` 找窗口切换、页面变化与大幅布局变动
- `transcriber` 判断录制是带旁白、只有系统音，还是静音

要识别出：

- 展示的软件与界面区域，
- 所教的单条工作流，
- 关键交互：点击、输入、滚动、提交、出结果，
- 明显需要放大或高亮支撑的时刻，
- 无效时间：安装、构建、加载、重复输入，
- 以及 `9:16` 在不丢信息的前提下是否可行。

### 2. 归类演示原型

选定一个主导原型：

- `tutorial`：一步步完成某项任务
- `feature_showcase`：展示某功能能做什么
- `troubleshooting`：复现并修复一个问题
- `walkthrough`：讲解跨工具的多步流程
- `comparison`：对比两种做法或两种结果

如果素材混合了多种原型，挑出应当主导节奏与包装的那一个。

### 3. 确定交付意图

屏幕演示要窄、要结果导向：

- `30-60s`：快速技巧或功能揭示
- `60-120s`：聚焦的产品走查或缺陷修复
- `120-300s`：带章节的教程

默认取能干净教会该任务的最短时长。除非用户明确要一份尽量不压缩的培训素材，否则不要保留原始时长。

### 4. 选择可行的输出形态

围绕可读性而非流量压力来规划平台：

- 密集的桌面界面用 `youtube` 或 `linkedin`，
- 只有当有效画面能扛住窄幅裁切时才用 `instagram` 或 `tiktok`，
- 界面含多面板或代码窗口时，优先 `1:1` 或 `16:9`。

### 5. 撰写 brief

用 schema 字段承载简洁的创作契约，把更丰富的制作细节放进 `metadata`。

推荐的 `metadata` 键：

- `source_path`
- `source_duration_seconds`
- `source_resolution`
- `has_voiceover`
- `software_shown`
- `demo_archetype`
- `critical_moments`
- `dead_time_segments`
- `recommended_aspect_ratios`
- `notes_for_scene_planner`

brief 应回答：

- 观众将学到什么，
- 这是给谁看的，
- 视频最后要落到什么证据/结果上，
- 必拍动作是哪些，
- 哪些裁切方向是安全的。

### 6. 质量闸门

存档前确认：

- 工作流足够窄，配得上所选时长，
- 「原来如此」的那个结果被清楚识别出来，
- 目标平台与界面密度匹配，
- brief 里点名了真实软件，而不是含糊描述，
- metadata 给下游阶段提供了足够的制作事实。

## 常见坑

- 把一段 7 分钟的录制默认当成 7 分钟的交付物。
- 只因为用户要 Shorts 就给密集桌面录制选 `9:16`。
- 用户其实要的是完成任务，却写了一份概念味很重的 brief。
- 没标注静音；若没有旁白，下游阶段必须立刻知道。

---

## 闸门提醒（有约束力）

本阶段以人工批准为闸门（`human_approval_default: true`）。审阅通过后：
以 `status="awaiting_human"` 存档，呈交摘要（Backlot 看板会渲染产物），然后**结束本轮**。
不要在同一次回复里启动下一阶段。批准是按闸门计的 —— 之前的「继续吧」不覆盖本闸门。
