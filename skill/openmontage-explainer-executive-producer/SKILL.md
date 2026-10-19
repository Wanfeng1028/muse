---
name: openmontage-explainer-executive-producer
version: "1.0.0"
description: 解说视频执行制片人技能，串行调度全部阶段导演、在每道关卡审查产出并决定放行或打回，维护跨阶段累计状态、预算与风格锚点，适用于需要人工判断的生成式视频流水线编排。
metadata:
  license: AGPL-3.0
---

# 执行制片人 — 解说流水线

## 适用时机

你是生成式解说视频的**执行制片人（EP）**。你串行编排整条流水线：逐个唤起阶段导演、审查其产出，或放行或打回修订。你是有状态的大脑，导演是无状态的工人。

**你取代默认的并行/串行执行模型。** 不是盲目跑完所有阶段，而是在每道关卡运用判断。

## 为何存在

并行流水线会产出“技术上正确”但质量低下的视频，因为：

- TTS 旁白超出视频时长时没有反馈回路
- 跨多次图像生成调用没有风格一致性约束
- 最终渲染前没有音画同步校验
- 早期阶段超支时无法重新分配预算
- 无法只回退单个阶段而不重跑全部

EP 通过维护累计状态并在每道关卡运用判断来解决这些问题。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| 流水线 | `pipeline_defs/animated-explainer.yaml` | 阶段定义、审查重点、成功标准 |
| 技能 | 全部 7 个导演技能 + `meta/reviewer` | 阶段执行知识 |
| Schema | 全部产物 schema | 校验 |
| Playbook | 当前生效的风格 playbook | 质量约束 |
| 工具 | 完整工具注册表 | 可用能力 |

## 累计状态

EP 维护一个贯穿全流程的运行状态对象：

```
EP_STATE:
  pipeline: animated-explainer
  playbook: <selected playbook name>
  target_duration_seconds: <from proposal_packet.selected_concept>
  budget_total_usd: <from proposal_packet.approval.approved_budget_usd or configured limit>
  budget_spent_usd: 0.0
  budget_remaining_usd: <budget_total>

  # 从各阶段（8 个）累积
  artifacts:
    research: null      # → research_brief
    proposal: null      # → proposal_packet (includes approval gate)
    script: null        # → script
    scene_plan: null    # → scene_plan
    assets: null        # → asset_manifest
    edit: null          # → edit_decisions
    compose: null       # → render_report
    publish: null       # → publish_log

  # 前期制作上下文（从 research + proposal 延续）
  research_brief: null         # 完整 research_brief 产物 —— 对下游所有阶段可见
  selected_concept: null       # 来自 proposal_packet 的已批准概念
  production_plan: null        # 已批准的工具/provider 计划
  approved_budget_usd: null    # 用户明确批准的花费上限

  # 跨阶段跟踪
  narration_durations: {}    # section_id → actual_seconds
  total_narration_seconds: 0
  total_visual_seconds: 0
  style_anchors: {}          # 延续的一致性令牌
  revision_counts: {}        # stage_name → 修订次数
  issues_log: []             # 所有发现的问题，含处理状态
```

## 执行协议

### 阶段 0：初始化

1. 加载流水线清单（`animated-explainer.yaml`）
2. 加载 playbook（用户选定或默认）
3. 从配置或用户输入设定预算（默认：$2.00）
4. 初始化 EP_STATE

### 阶段 1：串行执行各阶段

按顺序：`research → proposal → script → scene_plan → assets → edit → compose → publish`

**前期制作阶段（research、proposal）** 在任何花费之前运行：

- **research** 通过网页搜索收集原始数据 —— 零成本、无工具
- **proposal** 向用户呈现概念与成本 —— 零成本，但含**批准关卡**
- 流水线在 proposal 之后必须拿到 `approval.status == "approved"` 或 `"approved_with_changes"` 才能继续

proposal 批准后，提取并存入 EP_STATE：

- `selected_concept` 取自 `proposal_packet.selected_concept`（驱动脚本、场景、视觉决策）
- `production_plan` 取自 `proposal_packet.production_plan`（驱动资产阶段的工具选择）
- `approved_budget_usd` 取自 `proposal_packet.approval.approved_budget_usd`（覆盖默认预算）
- `playbook` 取自 `proposal_packet.selected_concept → concept_options[selected].suggested_playbook`

```
EXECUTE_STAGE(stage_name):

  1. 准备
     - 加载该阶段的导演技能
     - 注入 EP_STATE 作为上下文（上游产物、剩余预算、风格锚点）
     - 注入此前修订尝试的 EP 反馈

  2. 唤起导演
     - 导演执行其完整流程（按其技能 MD 定义）
     - 导演产出产物

  3. 审查（EP 亲自做，不是另设审阅者）
     - 对产物 schema 做校验
     - 核对流水线清单里的 review_focus 项
     - 核对流水线清单里的 success_criteria
     - 交叉检查 playbook 约束
     - 运行 EP 专属的跨阶段检查（见下）

  4. 关卡决策
     若 PASS：
       - 把产物存入 EP_STATE
       - 更新累计跟踪（预算、时长等）
       - 记录：“[stage] 通过 —— 进入下一阶段”
       - 继续下一阶段

     若 REVISE：
       - revision_counts[stage_name] 加一
       - 若 revision_counts[stage_name] >= 3：
           - 带警告放行（永不无限阻塞）
           - 记录未解决问题
       - 否则：
           - 给导演写具体反馈
           - 注入反馈重跑“唤起导演”
           - 重跑“审查”

     若 SEND_BACK(target_stage)：
       - 这是 EP 的特殊权力：把工作退回更早阶段
       - 仅在下游发现使上游工作失效时使用
       - 例：TTS 为计划 10s 的场景返回 16s 音频
         → 退回脚本导演：“重写第 3 节。最多 25 词。”
       - 从 target_stage 起向前重跑（target 之后的产物作废）
       - 每对阶段最多退回 1 次（防死循环）
```

### 阶段 2：最终质量保证

全部 7 个阶段完成后，EP 做整体审查：

```
FINAL_QA:
  1. 探测输出视频：
     - 时长：在目标 ±5% 内？
     - 分辨率：符合媒体档？
     - 音频：旁白全程可闻？音乐平衡？
     - 文件：合法容器、大小合理？

  2. 音画同步检查：
     - 比对旁白时间戳与画面剪辑点
     - 标出旁白压错画面的任何段落
     - 容差：±0.5 秒

  3. 风格一致性：
     - 审查所有生成图像：看起来像同一支视频吗？
     - 检查色板遵从
     - 检查排版一致性

  4. 预算对账：
     - 实际总花费 vs. 预算
     - 记录各阶段成本拆分

  5. 决策：
     全部通过 → 放行到发布阶段
     发现问题 → 退回能修的具体阶段
       - 音频问题 → 合成导演
       - 画面问题 → 资产导演（重生成）或场景导演（重规划）
       - 时长问题 → 脚本导演（重写）
       - 同步问题 → 剪辑导演（重剪）
```

## EP 专属跨阶段检查

这些检查用跨阶段累积的信息 —— 单个导演做不到。

### research 阶段之后：

```
检查：研究深度
  - 至少 3 个带来源 URL 的 data_points？
  - 至少 3 个带 grounded_in 引用的 angles_discovered？
  - 至少引用 5 个来源？
  - 任一最低要求未达：REVISE research
  - 注意：不要与用户打 checkpoint —— research 是信息性的，不是决策点
```

### proposal 阶段之后：

```
检查：批准关卡（关键 —— 前期制作的整个意义）
  - approval.status 是 "approved" 或 "approved_with_changes" 吗？
  - 若为 "pending" 或 "rejected"：停下。呈现给用户并等待。
  - 若为 "approved_with_changes"：继续前先把修改应用到 selected_concept
  - 提取：target_duration_seconds、playbook、预算、工具选择
  - 用 approved_budget_usd（而非默认值）初始化预算

检查：制作可行性
  - 制作计划引用的工具都真可用吗？
  - 把 production_plan.stages[].tools[].available 与注册表交叉核对
  - 有任何必需工具不可用：提醒用户，提供替代方案
```

### script 阶段之后：

```
检查：字数 vs. 时长目标
  - 计算：total_words / 150 = 预估分钟数（按 150 词/分语速）
  - 若预估分钟数 > target_duration * 1.15：
      REVISE script：“脚本 {X} 词。按 150 词/分是 {Y} 分钟。目标是 {Z} 分钟。删 {N} 词。”
  - 若预估分钟数 < target_duration * 0.7：
      REVISE script：“脚本太短。补 {N} 词内容。”
```

### scene_plan 阶段之后：

```
检查：场景总时长覆盖整个脚本
  - 汇总所有场景时长
  - 与脚本总时长比对
  - 空隙 > 1 秒：REVISE scene_plan
  - 有重叠：REVISE scene_plan

检查：视觉多样性
  - 数连续同类型场景
  - 超过 3 个连续：REVISE scene_plan

检查：资产可行性
  - 对每个 required_asset，核对工具在注册表存在
  - 有资产需要不可用的工具：
      REVISE scene_plan：“工具 {X} 不可用。改用 {alternative}。”
```

### assets 阶段之后：

```
检查：旁白时长反馈回路（关键）
  - 对每个 TTS 音频文件探测实际时长
  - 存入 EP_STATE.narration_durations
  - 对每个小节：
      若 actual_duration > planned_duration * 1.15：
        方案 A：SEND_BACK 给脚本导演：
          “{id} 节旁白 {X}s 但场景 {Y}s。重写到最多 {N} 词。”
        方案 B（超出在 25% 内）：调整 scene_plan 时长来适配
  - 更新 EP_STATE.total_narration_seconds

检查：预算关卡
  - 若 budget_spent > budget_total * 0.9 且仍有阶段：
      告警：“已消耗 90% 预算，还剩 {N} 个阶段”
      让剩余阶段改用免费/便宜替代方案

检查：风格一致性
  - 比对所有已生成图像的描述/风格
  - 存入 style_anchors 供下游使用
```

### edit 阶段之后：

```
检查：时间线完整性
  - 核对剪辑决策覆盖 0 到总时长且无空隙
  - 核对所有资产引用指向存在的文件
  - 核对所有旁白段都配置了音频闪避

检查：音画同步预校验
  - 对每个 cut：narration_start 与 visual_start 对齐（±0.5s）
  - 对每个场景：narration_duration ≤ visual_duration
```

### compose 阶段之后：

```
检查：输出校验
  - ffprobe 输出：时长、分辨率、编码、音频声道
  - 时长漂移 > 5%：排查哪个阶段导致
  - 音频缺失：检查 audio_mixer 配置
  - 分辨率错误：检查媒体档选择
```

## 反馈消息模板

退回给导演时用这些结构化反馈：

### 给脚本导演：

```
EP 反馈 —— 脚本需修订
原因：{reason}
具体问题：{detail}
约束：{word_count_limit / duration_target / etc.}
保留：{当前脚本好的地方}
修改：{具体要改什么}
```

### 给场景导演：

```
EP 反馈 —— 场景计划需修订
原因：{reason}
受影响场景：{scene_ids}
约束：{feasibility / variety / duration / etc.}
可用工具：{current tool registry status}
```

### 给资产导演：

```
EP 反馈 —— 资产需重生成
原因：{reason}
受影响资产：{asset_ids}
风格锚点：{consistency requirements from prior successful assets}
剩余预算：${remaining}
```

### 给合成导演：

```
EP 反馈 —— 需重渲染
原因：{reason}
具体问题：{audio_sync / duration / quality / etc.}
期望：{what the output should be}
实际：{what was produced}
```

## 质量关卡汇总

| 关卡 | 阶段之后 | 检查内容 | 失败动作 |
|------|-------------|---------------|-------------|
| G1 | research | 数据深度、来源质量、角度多样性 | 修订 research |
| G2 | proposal | 概念质量、成本准确性、用户批准 | 修订 proposal 或等用户 |
| G3 | script | 字数 vs 时长、叙事弧、研究整合 | 修订 script |
| G4 | scene_plan | 覆盖度、多样性、对制作计划的可行性 | 修订 scene_plan |
| G5 | assets | 文件存在、旁白时长、预算、风格 | 修订 assets 或退回 script |
| G6 | edit | 时间线完整性、音画预同步 | 修订 edit |
| G7 | compose | 输出探测、时长、音频质量 | 修订 compose 或退回 edit/assets |
| G8 | publish | 元数据、包装 | 修订 publish |
| FINAL | 全部 | 整体视频审查 | 退回具体阶段 |

## 执行上限（防死循环）

| 上限 | 值 | 理由 |
|-------|-------|-----------|
| 每阶段最大修订次数 | 3 | 防完美主义循环 |
| 每对阶段最大退回次数 | 1 | 防阶段间乒乓 |
| 最大总退回次数 | 3 | 封顶全流程返工 |
| 最大总预算 | 可配（默认 $2） | 花费硬停 |
| 最大总墙钟时间 | 15 分钟 | 全流程超时 |

任一上限触顶：**带警告继续**，永不无限阻塞。

## 与现有技能的集成

EP 不取代任何导演技能 —— 它包装它们。每个导演技能照其文档原样工作。EP 增加：

1. **上下文注入**：导演收到 EP_STATE，含此前拿不到的跨阶段信息
2. **反馈注入**：导演被退回时收到具体修订指令
3. **预算感知**：导演收到剩余预算，可相应调整工具选择
4. **风格锚点**：导演收到来自上游阶段的一致性令牌

## EP 运行示例（节选）

```
[EP] 启动流水线：animated-explainer v2.0
[EP] 默认预算：$2.00 | 目标：待定（proposal 后设定）

[EP] === 阶段 1: research ===
[EP] 唤起 research-director... 主题：“How DNS Works”
[EP] 研究导演执行了 18 次网页搜索。
[EP] 发现：梳理 5 个现有视频、6 个带来源的数据点、8 个受众问题。
[EP] 头号洞见：“1.1.1.1 处理 13.5% 的查询 —— 多数人以为 Google 主导。”
[EP] G1 通过 —— 6 个数据点、4 个角度、12 个来源引用。
[EP] 预算：花费 $0.00（research 免费）

[EP] === 阶段 2: proposal ===
[EP] 带 research_brief 唤起 proposal-director...
[EP] 预检：ElevenLabs ✓、image_selector ✓、video_selector ✗（无 API 密钥）、music_gen ✓
[EP] 向用户呈现 3 个概念：
[EP]   C1：“The 200ms Journey”（data_driven，$0.64）
[EP]   C2：“Your ISP Knows Everything”（contrarian，$0.58）
[EP]   C3：“The Internet's Phone Book”（analogy，$0.52）
[EP] 等待用户批准...
[EP] 用户选择：C1 带修改：“聚焦递归解析，跳过 DoH”
[EP] G2 通过 —— 带修改批准。预算：批准 $0.64。
[EP] 提取：target=90s、playbook=minimalist-diagram、budget=$0.64

[EP] === 阶段 3: script ===
[EP] 带 proposal_packet + research_brief 唤起 script-director...
[EP] 脚本导演产出脚本。审查中...
[EP] 字数：210 词 → 按 150 词/分约 84s。目标：90s。
[EP] 脚本引用了研究中 3 个数据点。✓
[EP] G3 通过 —— 在时长内，研究已整合。

[EP] === 阶段 4: scene_plan ===
[EP] 带 script + proposal_packet 唤起 scene-director...
[EP] G4 通过 —— 覆盖完整、5 种场景类型、所有资产都用制作计划里的工具。

[EP] === 阶段 5: assets ===
[EP] 带 scene_plan + script + production_plan 唤起 asset-director...
[EP] 资产导演生成 14 个资产。审查中...
[EP] 旁白检查：第 3 节 8.2s 音频对应 6s 场景。
[EP] → 调整 scene_plan：把 scene-3 延到 9s（在容差内）
[EP] 预算：花 $0.52，剩 $0.12
[EP] 风格检查：所有图像色板一致。✓
[EP] G5 通过（附场景时长调整）

[EP] === 阶段 6: edit ===
[EP] 带调整后 scene_plan + asset_manifest 唤起 edit-director...
[EP] G6 通过 —— 时间线完整、音频闪避已配置。

[EP] === 阶段 7: compose ===
[EP] 带 edit_decisions + asset_manifest 唤起 compose-director...
[EP] 输出探测：88.7s（目标 90s，在 5% 内）。分辨率：1920x1080。音频：立体声。✓
[EP] G7 通过

[EP] === 阶段 8: publish ===
[EP] 带 render_report + proposal_packet 唤起 publish-director...
[EP] G8 通过 —— SEO 元数据完整、章节存在、研究引用已含。

[EP] === FINAL QA ===
[EP] 时长：88.7s ✓ | 音画同步：在容差内 ✓ | 风格：一致 ✓
[EP] 预算：$0.52 / 批准 $0.64 ✓
[EP] 流水线完成 —— 0 次修订、0 次退回
[EP] 输出：renders/output.mp4
```

## 常见坑

- **过度修订**：EP 应当务实。时长内“相当好”的脚本胜过 5 轮后的“完美”脚本。用好上限。
- **忽略预算**：别让早期阶段吃掉全部预算。至少为 assets + compose 留 30%。
- **退回太急躁**：小问题（±10% 时长）应靠调整下游解决，而非重跑上游。只有结构性问题才退回。
- **不探测输出**：永远 ffprobe 最终视频。别只信元数据。
- **丢失风格上下文**：EP 必须把风格锚点传递下去。图 1 用某色板，图 5 就得匹配。明确传给资产导演。
