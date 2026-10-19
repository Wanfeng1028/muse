---
name: openmontage-talking-head-executive-producer
version: "1.0.0"
description: 口播视频流水线的执行制片技能，串行调度七个阶段导演并在每个关卡做质量判断，适用于需要跨阶段状态管理、字幕同步校验与返工控制的说话人头视频项目。
metadata:
  license: AGPL-3.0
---

# 执行制片 — 口播流水线

## 何时使用

你负责一个口播视频项目的全局调度。流水线各阶段的导演是无状态执行者，而你是唯一持有累积状态的角色：按顺序唤醒每个阶段的导演、审阅其产物、决定放行还是打回修改。你取代了默认的盲目并行/串行执行方式，在每一道关卡上行使判断。

## 为什么需要这一层

口播流水线把一段真人讲话的原始素材加工成带字幕的成片。若缺少执行制片：

- 转写错误会静默传播到所有下游阶段
- 字幕时间轴与语音漂移后没有反馈机制去纠正
- 场景覆盖出现空洞，成片里留下无声片段
- 最终渲染前没有音画同步校验
- 无法只重跑单个阶段，必须全流程重来
- 增强决策（人脸、调色、音频）脱离整体画面上下文

执行制片通过维持累积状态、在每个关卡应用判断来解决这些问题。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| 流水线 | `pipeline_defs/talking-head.yaml` | 阶段定义、审阅重点、成功标准 |
| 技能 | 全部 7 个导演技能 + `meta/reviewer` | 阶段执行知识 |
| Schema | 全部产物 schema | 校验 |
| Playbook | 用户选择 / 从素材推导 / 安全回退 | 质量约束 |
| 工具 | 完整工具注册表 | 可用能力 |

## 与解说流水线的关键差异

口播流水线是**素材优先**，而非创意优先：

| 维度 | 解说 EP | 口播 EP |
|------|---------|---------|
| 源材料 | 无，全部生成 | 一开始就有原始素材 |
| 脚本阶段 | 从零撰写 | 从转写中提取 |
| 核心难点 | 创意生成质量 | 转写准确度 + 时间轴 |
| 预算模型 | 中等（TTS + 图像生成） | 低（以处理为主，叠加可选） |
| 时长来源 | 提案中设定目标 | 由原始素材长度决定 |
| 关键同步 | 旁白 ↔ 画面时长 | 字幕 ↔ 语音时序 |
| 前期阶段 | 调研 + 提案（2 阶段） | 创意（1 阶段），无需调研 |

## 累积状态

执行制片维护一个贯穿全流程的状态对象：

```
EP_STATE:
  pipeline: talking-head
  playbook: <所选 playbook 名称 / 自定义身份 / 安全回退>
  raw_footage_path: <源素材路径>
  raw_footage_duration_seconds: <来自 ffprobe>
  raw_footage_resolution: <来自 ffprobe>
  target_duration_seconds: <来自 brief，可短于原始素材>
  budget_total_usd: <用户指定或默认 $0.50>
  budget_spent_usd: 0.0
  budget_remaining_usd: <budget_total>

  artifacts:
    idea: null          # → brief
    script: null        # → script（基于转写）
    scene_plan: null    # → scene_plan
    assets: null        # → asset_manifest
    edit: null          # → edit_decisions
    compose: null       # → render_report
    publish: null       # → publish_log

  transcript_segments: []        # 词级时间戳片段
  transcript_confidence: null    # 平均词置信度
  transcript_language: null      # 检测到的语言
  subtitle_sync_offsets: {}      # section_id → 漂移秒数（正值 = 字幕偏晚）

  total_footage_seconds: 0
  total_edit_seconds: 0
  style_anchors: {}              # 叠加元素的风格一致性令牌
  revision_counts: {}            # stage_name → 修订次数
  issues_log: []                 # 全部问题及其解决状态

  enhancements_applied: []       # face_enhance、color_grade、audio_enhance
  audio_profile:
    has_background_noise: null
    audio_channels: null
    sample_rate: null
```

## 执行协议

### 阶段 0：初始化

1. 载入流水线清单 `talking-head.yaml`
2. 载入 playbook：优先用户选择，其次品牌体系，再次从素材推导的视觉身份；只有在没有更强身份依据时才用 `clean-professional`
3. 设定预算（默认 $0.50，口播以处理为主，开销低）
4. 用 ffprobe 探测原始素材：时长、分辨率、帧率、音轨、编码
5. 将素材元数据写入 EP_STATE
6. 初始化 EP_STATE

### 阶段 1：串行执行各阶段

按顺序执行：`idea → script → scene_plan → assets → edit → compose → publish`

```
EXECUTE_STAGE(stage_name):

  1. 准备
     - 载入该阶段的导演技能
     - 注入 EP_STATE 作为上下文（先前产物、剩余预算、风格锚点）
     - 注入上一轮修订时的反馈

  2. 唤醒导演
     - 导演按其技能文档完整执行
     - 产出一个 artifact

  3. 审阅（由 EP 本人执行，不另设审阅者）
     - 对照 schema 做校验
     - 检查流水线清单中的 review_focus 条目
     - 检查 success_criteria
     - 对照 playbook 约束
     - 运行 EP 专属的跨阶段检查（见下文）

  4. 关卡决策
     若 PASS：
       - 将 artifact 存入 EP_STATE
       - 更新累积追踪（预算、时长等）
       - 记录 "[stage] PASSED — 进入下一阶段"
       - 继续

     若 REVISE：
       - revision_counts[stage_name] += 1
       - 若 revision_counts[stage_name] >= 3：
           带警告放行（绝不无限阻塞）
           记录未解决问题
       - 否则：
           组装具体反馈注入导演
           重新唤醒导演
           重新审阅

     若 SEND_BACK(target_stage)：
       - 这是 EP 的特权：把工作退回更早的阶段
       - 仅在下游发现使上游成果失效时使用
       - 例如：字幕同步检查发现转写时间戳错误
         → 退回 script 导演："重新转写第 3 段，时间戳不对。"
       - 从 target_stage 起重跑，其后产物全部作废
       - 每对阶段最多退回 1 次，防止无限循环
```

### 阶段 2：终检

七个阶段全部完成后，EP 做整体审阅：

```
FINAL_QA:
  1. 探测输出视频：
     - 时长是否在目标（或原始素材时长）±5% 内？
     - 分辨率是否匹配目标或原始素材？
     - 语音是否全程可闻？有无削波？电平是否平衡？
     - 容器是否合法？体积是否合理？

  2. 字幕同步（口播的关键项）：
     - 逐条核对字幕时间戳与语音
     - 每条字幕是否在对应词出现后 ±0.3s 内显示？
     - 标记任何肉眼可见的不同步段落
     - 容差 ±0.3 秒（比解说更严，因为语音就是内容本身）

  3. 音频质量：
     - 素材有底噪时是否做了降噪？
     - 电平是否归一化（语音目标 -16 LUFS）？
     - 若加了背景音乐，闪避是否正确配置？

  4. 视觉质量：
     - 若启用了 face_enhance，效果是否自然？
     - 若启用了 color_grade，是否一致？
     - 若加了叠加元素，时间点是否正确？

  5. 预算对账：
     - 实际总支出 vs. 预算
     - 记录各阶段成本明细

  6. 决策：
     全部通过 → 批准进入 publish
     发现问题 → 退回能修复它的具体阶段：
       - 字幕时序 → asset 导演（重生成字幕）
       - 音频问题 → compose 导演（重混）
       - 视觉增强问题 → compose 导演（重渲染）
       - 覆盖空洞 → scene 导演（重规划）或 edit 导演（重剪）
       - 转写错误 → script 导演（重新转写）
```

## EP 专属跨阶段检查

这些检查依赖跨阶段累积的信息，单个导演无法完成。

### idea 阶段之后

```
检查：素材可用性
  - 素材是否有音轨？（无音轨 = 口播流水线无法继续）
  - 音质是否足够？（信噪比）
  - 时长对目标平台是否合理？
  - 若时长超过目标 3 倍：标记需要大幅裁剪
  - 注意：idea 阶段本身会与用户确认，这是人工批准关卡
```

### script 阶段之后

```
检查：转写质量（关键，下游全部依赖它）
  - 平均词置信度
  - 若 avg_confidence < 0.8：
      要求修订："转写置信度偏低（{X}）。若未使用 large-v3 模型请切换。
      若仍偏低，标记具体低置信段供人工复核。"
  - 抽查时间戳是否单调递增
  - 抽查是否有超过 2 秒的空白（可能漏词）
  - 将 transcript_segments 存入 EP_STATE 供下游生成字幕

检查：段落边界
  - 段落是否对齐自然的话题切换？
  - 时间戳是否落在素材时长范围内？
  - 是否有段落超过 60 秒？（可能需要切分以便场景规划）
```

### scene_plan 阶段之后

```
检查：完整覆盖
  - 累加所有场景时长
  - 与原始素材（或目标剪辑时长）比对
  - 间隙 > 1 秒：退回 scene_plan
  - 重叠：退回 scene_plan

检查：增强可行性
  - 对每个计划中的增强（人脸、调色、叠加）验证工具注册表中存在对应工具
  - 若计划了 face_enhance 但工具不可用：从计划移除并记警告
  - 若计划了叠加图片：确认图像工具可用

检查：叠加对齐
  - 若叠加元素锚定在特定时间戳，验证这些时间戳落在转写得到的真实场景边界内
```

### assets 阶段之后

```
检查：字幕同步（口播关键）
  - 将字幕条时间戳与转写词时间戳比对
  - 每条：|字幕起始 - 词起始| < 0.3s
  - 将偏移量写入 EP_STATE.subtitle_sync_offsets
  - 若偏移 > 0.5s：退回 assets："字幕条 {id} 偏移 {X}s，请依据原始转写片段重生成。"

检查：音频抽取
  - 是否从素材抽出了音频？
  - 需要时是否做了降噪？
  - 电平是否在合理范围？

检查：预算闸
  - 若 budget_spent > budget_total * 0.8 且仍有阶段待跑：
      告警："已消耗 80% 预算，还剩 {N} 个阶段"
      调整后续阶段，跳过可选增强
```

### edit 阶段之后

```
检查：时间线完整性
  - 确认剪辑决策覆盖 0 到总时长且无空洞
  - 确认所有剪切源文件都指向 asset_manifest 中真实存在的路径
  - 确认字幕配置存在且指向合法字幕文件

检查：裁剪有效性
  - 若素材被裁短：保留的是正确段落吗？
  - 保留段落是否与 scene_plan 一致？
  - 剪切间过渡是否平滑（非刻意时不应有跳切）？
```

### compose 阶段之后

```
检查：输出验证
  - ffprobe 输出：时长、分辨率、编码、声道
  - 时长漂移 > 5%：追查是哪一阶段造成
  - 无音频：检查抽取与混音
  - 分辨率错误：检查是否被 face_enhance 或 color_grade 改变
  - 字幕：若要求烧录，确认输出中可见
```

## 反馈消息模板

把工作退回导演时使用以下结构化反馈：

### 给 Script 导演

```
EP 反馈 — 需要修订脚本
原因：{reason}
具体问题：{transcript_quality / timestamp_error / section_boundary}
受影响段落：{section_ids}
操作：{re-transcribe / re-segment / re-align}
转写设置：{model / language hints if applicable}
```

### 给 Scene 导演

```
EP 反馈 — 需要修订场景规划
原因：{reason}
受影响场景：{scene_ids}
约束：{coverage / feasibility / timing}
可用工具：{current tool registry status}
```

### 给 Asset 导演

```
EP 反馈 — 需要重新生成素材
原因：{reason}
受影响素材：{asset_ids}
具体修复：{subtitle_resync / audio_renormalize / overlay_regen}
转写参照：{original transcript segments for re-alignment}
剩余预算：${remaining}
```

### 给 Edit 导演

```
EP 反馈 — 需要修订剪辑
原因：{reason}
具体问题：{gap_at_timestamp / invalid_reference / missing_subtitle_config}
素材清单：{current valid asset paths}
```

### 给 Compose 导演

```
EP 反馈 — 需要重渲染
原因：{reason}
具体问题：{subtitle_sync / audio_quality / resolution / duration}
期望：{what the output should be}
实际：{what was produced}
增强调整：{skip/add face_enhance, color_grade, etc.}
```

## 质量关卡一览

| 关卡 | 位于阶段后 | 检查内容 | 失败动作 |
|------|-----------|---------|---------|
| G1 | idea | 素材可用性、音轨存在、用户批准 | 修订 brief 或中止流水线 |
| G2 | script | 转写置信度、时间戳、段落边界 | 修订脚本（重新转写） |
| G3 | scene_plan | 完整覆盖、增强可行性、叠加对齐 | 修订 scene_plan |
| G4 | assets | 字幕同步、音频抽取、预算 | 修订 assets 或退回 script |
| G5 | edit | 时间线完整性、裁剪有效、字幕配置 | 修订 edit |
| G6 | compose | 输出探测、时长、音频、字幕烧录 | 修订 compose 或退回 edit/assets |
| G7 | publish | 元数据、打包 | 修订 publish |
| FINAL | 全部 | 字幕同步、音频质量、视觉质量 | 退回指定阶段 |

## 执行上限（防循环）

| 上限 | 值 | 理由 |
|------|----|------|
| 每阶段最大修订次数 | 3 | 防止完美主义死循环 |
| 每对阶段最大退回次数 | 1 | 防止阶段间来回踢皮球 |
| 最大总退回次数 | 3 | 封顶整体返工量 |
| 最大总预算 | 可配置（默认 $0.50） | 硬性支出上限 |
| 最大总墙钟时间 | 10 分钟 | 全流程超时（比解说短，因为生成任务少） |

任一上限触发后：**带警告继续**，绝不无限阻塞。

## 与现有技能的集成方式

执行制片不替换任何导演技能，而是把它们包裹起来。每个导演技能照旧运行，EP 额外提供：

1. **上下文注入**：导演获得含跨阶段信息的 EP_STATE
2. **反馈注入**：被退回时导演收到具体修订指令
3. **预算感知**：导演获知剩余预算，可据此选择工具
4. **转写连续性**：EP 把转写数据一路传递下去，保证字幕生成与剪辑决策使用同一份事实来源

## EP 运行示例（精简）

```
[EP] 启动流水线：talking-head v2.0
[EP] 默认预算 $0.50 | Playbook：从素材推导的身份（或安全回退）

[EP] 探测原始素材：interview_raw.mp4
[EP] → 时长 4m22s | 1920x1080 | 30fps | 立体声 AAC
[EP] 素材可用，有音轨，继续。

[EP] === 阶段 1：idea ===
[EP] 唤醒 idea-director……素材：interview_raw.mp4
[EP] Brief："与 CTO 谈 API 安全" | 目标 3m00s（从 4m22s 裁剪）
[EP] 平台：用户指定 LinkedIn（原提议 Shorts 时长不符，已纠正）
[EP] G1 通过 — brief 引用素材、时长目标现实、用户已批准。

[EP] === 阶段 2：script ===
[EP] 唤醒 script-director……
[EP] 转写：WhisperX large-v3，处理 4m22s 音频……
[EP] 结果：612 词，平均置信度 0.91，语言 en。
[EP] 识别出 8 个段落，时间戳单调递增。✓
[EP] G2 通过 — 置信度良好，段落对齐话题切换。

[EP] === 阶段 3：scene_plan ===
[EP] 唤醒 scene-director……
[EP] 规划 8 个场景，总时长 3m02s（目标 3m00s）。
[EP] 增强项：全场 face_enhance、color_grade、0:00-0:05 下三分之一叠加。
[EP] 检查 face_enhance 工具……可用 ✓
[EP] G3 通过 — 覆盖完整，增强可执行。

[EP] === 阶段 4：assets ===
[EP] 唤醒 asset-director……
[EP] 生成字幕：82 条，SRT 格式。
[EP] 同步检查：最大偏移 0.18s，全部在 0.3s 容差内。✓
[EP] 音频已抽取并归一化至 -16 LUFS。✓
[EP] 下三分之一叠加通过 recraft_image 生成，花费 $0.02。
[EP] 预算：已用 $0.02，余 $0.48。
[EP] G4 通过。

[EP] === 阶段 5：edit ===
[EP] 唤醒 edit-director……
[EP] 时间线 3m02s，7 处剪切，字幕已启用。
[EP] 裁剪：去掉 0:00-0:12（静默）与 3:45-4:22（跑题）。
[EP] G5 通过 — 时间线完整，引用有效。

[EP] === 阶段 6：compose ===
[EP] 唤醒 compose-director……
[EP] face_enhance 处理 8 个场景；color_grade 统一暖色调；audio_enhance 降噪。
[EP] video_compose 输出 → output/talking-head-final.mp4
[EP] 探测输出：3m01s、1920x1080、立体声、H.264。✓
[EP] 预算：已用 $0.18。
[EP] G6 通过。

[EP] === 阶段 7：publish ===
[EP] 唤醒 publish-director……
[EP] G7 通过 — 标题、描述、章节、缩略图已配置。

[EP] === 终检 ===
[EP] 时长 3m01s ✓ | 字幕最大漂移 0.18s ✓ | 音频 -16.2 LUFS ✓
[EP] 人脸增强自然 ✓ | 调色一致 ✓ | 叠加时序正确 ✓
[EP] 预算 $0.18 / $0.50 ✓
[EP] 流水线完成 — 0 次修订、0 次退回
[EP] 输出：output/talking-head-final.mp4
```

## 常见陷阱

- **忽视转写质量**：下游全部依赖转写。置信度低必须在 script 阶段修好，别让坏时间戳传到字幕与剪辑。
- **过度增强**：人脸增强与调色都是可选项。素材本身好看就跳过，不要为处理而处理。
- **字幕风格不匹配**：字幕样式必须来自 playbook，不能让 asset 导演用默认 SRT 样式。
- **不探测素材**：开工前必须 ffprobe。无音轨或容器损坏的视频会浪费每一个下游阶段。
- **裁剪过狠**：edit 导演可能剪掉看似跑题但有价值的上下文。EP 应结合 brief 确认被裁内容确实无用。
- **丢失转写数据**：EP 必须把 `transcript_segments` 从 script 阶段一路带到素材生成。字幕时序依赖同一份词级数据。
