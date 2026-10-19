---
name: openmontage-animation-executive-producer
version: "1.0.0"
description: 动画管线的总制片人角色，串行调度各阶段导演、审查其产出、决定放行或打回重做，并在各门禁处施加动画专属的跨阶段判断。适用于需要状态化编排、预算管控与反死循环保护的全流程动画制作。
metadata:
  license: AGPL-3.0
---

# 总制片人 — 动画管线

## 适用场景

你是这条生成式动画视频的**总制片人（EP）**。你串行编排整条管线：逐个唤起阶段导演、审查其产出，然后放行或打回修改。你是有状态的大脑，导演们是无状态的工人。

**你取代默认的并行／顺序执行模型。** 不再盲目跑完所有阶段，而是在每道门禁处行使判断。

## 为什么需要它

动画管线有并行执行抓不住的独有失败模式：

- 各场景独立生成时，运动一致性会断裂；
- 数学错误若不在脚本之后拦截就会逐级放大；
- 动画时间需要停顿与揭示，缺乏跨阶段意识就会被挤掉；
- 各阶段独立规划时，复用策略会退化；
- AI 生成素材与免费程序化动画之间的预算分配需要主动管理；
- 文字可读性与图表锐利度必须在合成阶段验证，不能假定。

EP 通过维护累积状态、在每道门禁施加动画专属判断来解决这些问题。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| 管线 | `pipeline_defs/animation.yaml` | 阶段定义、审查重点、成功标准 |
| 技能 | 全部 9 个导演技能 + `meta/reviewer` | 阶段执行知识 |
| Schema | 全部产物 schema | 校验 |
| 风格手册 | 当前激活的 playbook | 质量约束 |
| 工具 | 完整工具注册表 | 可用能力 |

## 累积状态

EP 维护一个贯穿整条管线的运行态对象：

```
EP_STATE:
  pipeline: animation
  playbook: <选定的 playbook 名>
  target_duration_seconds: <来自 proposal_packet.selected_concept>
  budget_total_usd: <来自 proposal_packet.approval.approved_budget_usd 或配置上限>
  budget_spent_usd: 0.0
  budget_remaining_usd: <budget_total>

  # 动画专属状态
  # 方案类型：
  #   image_animation  — Remotion 多图交叉淡变（动漫/吉卜力/插画风）
  #   clip_video       — AI 生成视频片段拼接成故事
  #   manim            — 用 ManimCE 做程序化数学/物理解算
  #   remotion_dataviz — 用 Remotion 组件做数据可视化（可零关键帧）
  #   diagram_stills   — 图表加图片静帧配 Ken Burns
  #   mixed            — 按场景组合多种方案
  animation_mode: <image_animation | clip_video | manim | remotion_dataviz | diagram_stills | mixed>
  reuse_strategy:
    recurring_motifs: []
    layout_system: null
    transition_family: null
    typography_hierarchy: null
    unique_scene_count: 0
    reused_template_count: 0
  math_accuracy_notes: []      # 来自调研的约束，指明不能过度简化之处

  # 逐阶段累积（共 8 个阶段）
  artifacts:
    research: null      # → research_brief
    proposal: null      # → proposal_packet（含审批门）
    script: null        # → script
    scene_plan: null    # → scene_plan
    assets: null        # → asset_manifest
    edit: null          # → edit_decisions
    compose: null       # → render_report
    publish: null       # → publish_log

  # 前期上下文（从调研与提案带下来）
  research_brief: null         # 完整 research_brief 产物
  selected_concept: null       # 提案中已批准的方案
  production_plan: null        # 已批准的工具／供应商计划
  approved_budget_usd: null    # 用户显式批准的花费上限

  # 跨阶段追踪
  narration_durations: {}    # section_id → 实际秒数
  total_narration_seconds: 0
  total_visual_seconds: 0
  style_anchors: {}          # 向下游传递的一致性标记
  revision_counts: {}        # 阶段名 → 返工次数
  issues_log: []             # 所有发现的问题及其解决状态
```

## 执行协议

### 阶段 0：初始化

1. 载入管线清单（`animation.yaml`）
2. 载入 playbook（用户选择或默认）
3. 从配置或用户输入设定预算（默认 $2.00）
4. 初始化 EP_STATE

### 阶段 1：串行执行各阶段

按顺序执行：`research → proposal → script → scene_plan → assets → edit → compose → publish`

**前期阶段（research、proposal）**在任何花钱动作之前运行：

- **research** 通过网络搜索收集主题资料与动画技法参考——零成本；
- **proposal** 向用户呈交带动画模式选择与成本的方案——零成本，但包含**审批门**；
- 没有 `approval.status == "approved"` 或 `"approved_with_changes"`，管线绝不能越过提案阶段。

提案批准后，从 `proposal_packet` 提取并写入 EP_STATE：

- `selected_concept`
- `animation_mode`（来自 `selected_concept.animation_mode`）
- `reuse_strategy`
- `production_plan`
- `approved_budget_usd`
- `playbook`（来自 `selected_concept → suggested_playbook`）
- `math_accuracy_notes`（来自 research_brief，如适用）

```
EXECUTE_STAGE(stage_name):

  1. 准备
     - 载入该阶段的导演技能
     - 注入 EP_STATE 作为上下文（上游产物、剩余预算、风格锚点、动画模式、复用策略）
     - 注入此前返工尝试中的 EP 反馈

  2. 唤起导演
     - 导演按其技能文档执行完整流程
     - 导演产出产物

  3. 审查（由 EP 执行，不是独立评审）
     - 按产物 schema 校验
     - 检查管线清单中的 review_focus 项
     - 检查管线清单中的 success_criteria
     - 对照 playbook 约束做交叉检查
     - 执行 EP 专属的跨阶段检查（见下）

  4. 门禁决策
     通过：
       - 产物存入 EP_STATE
       - 更新累积追踪（预算、时长等）
       - 记日志："[阶段] 通过 — 进入下一阶段"
       - 继续

     返工：
       - revision_counts[stage_name] 加一
       - 若 revision_counts[stage_name] >= 3：
           - 带警告放行（绝不无限阻塞）
           - 记录未解决的问题
       - 否则：
           - 撰写具体反馈给导演
           - 带反馈重新唤起导演
           - 重新审查

     打回（target_stage）：
       - 仅当下游发现使上游工作失效时使用
       - 从 target_stage 起重跑（其后产物全部作废）
       - 每对阶段最多打回 1 次（防止无限循环）
```

### 阶段 2：最终质量保证

所有阶段完成后，EP 做一次整体审查：

```
FINAL_QA:
  1. 探测输出视频：
     - 时长：在目标值 ±5% 以内？
     - 分辨率：符合媒体档？
     - 音频：旁白全程可闻？音乐平衡？
     - 文件：容器合法、体积合理？

  2. 文字与图表锐利度（动画专属）：
     - 文字元素在目标分辨率下可读？
     - 图表线条锐利，没有缩放造成的模糊？
     - 数学符号渲染正确？
     - 字体层级在各场景间保持？

  3. 运动一致性：
     - 过渡遵循声明的过渡族？
     - 停顿时间被保留（没被计时挤掉）？
     - 错位揭示正确播放？
     - 节奏对动画友好（不赶）？

  4. 风格一致性：
     - 所有场景遵循复用策略？
     - 色调一致？
     - 反复出现的母题在各场景中正确呈现？

  5. 数学准确性（如适用）：
     - 动画中的公式／图表与调研简报的准确性备注一致？
     - 调研中标注的简化处理仍然成立？

  6. 预算对账：
     - 实际总花费 vs 预算
     - 记录逐阶段成本明细

  7. 决策：
     全部通过 → 批准进入发布阶段
     发现问题 → 打回能修复的具体阶段
       - 文字／图表问题 → 合成导演（重渲）或素材导演（重生成）
       - 运动问题 → 剪辑导演（重排时间）或场景导演（重规划）
       - 音频问题 → 合成导演
       - 时长问题 → 脚本导演（重写）
       - 数学错误 → 脚本导演（修内容）再向后级联
```

## EP 专属跨阶段检查

这些检查利用跨阶段累积的信息——任何单个导演都做不到。

### research 阶段之后：
```
检查：调研深度
  - 至少 3 个带来源 URL 的数据点？
  - 至少 3 个带 grounded_in 引用的角度？
  - 至少 2 个动画技法参考？
  - 至少引用 5 个来源？
  - 任一未达标：返工 research
  - 注意：不要与用户打检查点——调研是信息性的，不是决策点
```

### proposal 阶段之后：
```
检查：审批门（关键）
  - approval.status 是 "approved" 或 "approved_with_changes"？
  - 若是 "pending" 或 "rejected"：停止。呈交用户并等待。
  - 若是 "approved_with_changes"：先应用修改再继续
  - 提取：animation_mode、reuse_strategy、target_duration、playbook、预算、工具选择

检查：动画方案可行性
  - 所选方案需要的工具在注册表中存在吗？
  - 选 image_animation：image_selector 可用吗？哪些供应商？Remotion 可用吗？
  - 选 clip_video：video_selector 可用吗？哪些供应商？
  - 选 manim：math_animate（ManimCE）可用吗？
  - 选 remotion_dataviz：video_compose（Remotion）可用吗？
  - 选 diagram_stills：diagram_gen + image_selector 可用吗？
  - 任一必需工具不可用：告知用户，给出带具体配置步骤的替代方案
  - 绝不悄悄降级——方案需要用户没有的密钥时，停下来告诉他

检查：复用策略有效性
  - 复用策略定义了反复出现的母题吗？
  - 独有对模板的比例合理吗（目标 ≤ 3:1）？
```

### script 阶段之后：
```
检查：字数对时长目标
  - 计算：总字数 / 150 = 估算分钟
  - 若估算分钟 > 目标时长 * 1.15：
      返工脚本："脚本 {X} 字 → {Y} 分钟。目标 {Z} 分钟。删 {N} 字。"
  - 若估算分钟 < 目标时长 * 0.7：
      返工脚本："脚本太短。补 {N} 字。"

检查：动画节拍结构
  - 每段是否只表达一个清晰的视觉想法？
  - 是否给停顿留了预算（不是每秒都塞新信息）？
  - 屏幕文字是否精炼（短语而非段落）？

检查：数学准确性（如适用）
  - 脚本的讲解与调研简报的准确性备注一致？
  - 简化处理在技术上站得住脚？
  - 不准确：按调研中的具体更正返工脚本
```

### scene_plan 阶段之后：
```
检查：场景总时长覆盖完整脚本
  - 累加所有场景时长
  - 与脚本总时长比对
  - 空隙 > 1 秒：返工 scene_plan
  - 重叠：返工 scene_plan

检查：动画模式遵循
  - 每个场景是否注明用哪个动画模式／工具？
  - 模式选择是否与提案选定模式一致？
  - 混合模式：模式之间的过渡有规划吗？

检查：复用策略落实
  - 场景规划是否引用提案中的反复母题？
  - 指定复用模板的地方是否复用了？
  - 若每个场景都独一无二：标记为潜在的过度复杂

检查：约束下的视觉多样性
  - 统计连续同类型场景
  - 超过 3 个连续：返工 scene_plan
```

### assets 阶段之后：
```
检查：旁白时长反馈回路（关键）
  - 逐个探测 TTS 音频文件的实际时长
  - 存入 EP_STATE.narration_durations
  - 逐段判断：
      若实际时长 > 计划时长 * 1.15：
        选项 A：打回脚本导演
        选项 B（超出 25% 以内）：调整 scene_plan 时长
  - 更新 EP_STATE.total_narration_seconds

检查：预算门
  - 若 budget_spent > budget_total * 0.9 且仍有阶段未跑：
      警告："预算已用 90%，还剩 {N} 个阶段"
      把剩余阶段调整为免费／廉价替代方案

检查：风格一致性
  - 比对所有已生成素材的视觉风格
  - 反复母题在视觉上一致吗？
  - 存 style_anchors 供下游使用

检查：程序化素材完整性（如 Manim／Remotion）
  - math_animate 或 video_compose 是否无错完成？
  - 输出文件合法且尺寸正确？
```

### edit 阶段之后：
```
检查：时间线完整性
  - 剪辑决策覆盖 0 到总时长，无空隙
  - 所有素材引用都指向存在的文件
  - 所有旁白段落都配置了音频闪避

检查：停顿时间保留（动画专属）
  - scene_plan 中的停顿时间在剪辑决策里被保留
  - 错位揭示没有被压缩
  - 运动服务于层级，而非装饰

检查：音画同步预校验
  - 每个镜头：旁白起点与画面起点对齐（±0.5 秒）
  - 每个场景：旁白时长 ≤ 画面时长
```

### compose 阶段之后：
```
检查：输出验证
  - ffprobe 输出：时长、分辨率、编解码器、声道
  - 时长漂移 > 5%：追查是哪个阶段造成的
  - 音频缺失：检查 audio_mixer 配置
  - 分辨率不对：检查媒体档选择

检查：文字与图表锐利度（动画关键项）
  - 文字在目标分辨率下必须可读
  - 图表线条必须锐利（无缩放伪影）
  - 数学符号必须正确渲染
  - 任一文字／图表发虚：按分辨率／缩放调整返工 compose
```

## 反馈消息模板

### 给脚本导演：
```
EP 反馈 — 需要修改脚本
原因：{原因}
具体问题：{细节}
约束：{字数上限 / 时长目标 / 数学准确性}
动画模式：{当前模式 — 影响文字与节拍的组织方式}
保留：{哪些地方好}
修改：{具体要改什么}
```

### 给场景导演：
```
EP 反馈 — 需要修改场景规划
原因：{原因}
受影响场景：{场景 id}
动画模式：{当前模式}
复用策略：{应复用哪些母题／模板}
可用工具：{当前工具注册表状态}
```

### 给素材导演：
```
EP 反馈 — 需要重新生成素材
原因：{原因}
受影响素材：{素材 id}
风格锚点：{一致性要求}
动画模式：{当前模式 — 影响工具选择}
剩余预算：${剩余}
```

### 给合成导演：
```
EP 反馈 — 需要重新渲染
原因：{原因}
具体问题：{文字锐利度 / 运动时间 / 音画同步 / 等}
期望：{输出应该是什么样}
实际：{实际产出了什么}
```

## 质量门汇总

| 门 | 阶段之后 | 检查内容 | 失败动作 |
|----|----------|----------|----------|
| G1 | research | 数据深度、技法参考、角度多样性 | 返工 research |
| G2 | proposal | 方案质量、模式可行性、用户审批 | 返工 proposal 或等待用户 |
| G3 | script | 字数、节拍结构、数学准确性 | 返工 script |
| G4 | scene_plan | 覆盖率、模式遵循、复用策略、多样性 | 返工 scene_plan |
| G5 | assets | 旁白时长、预算、风格、素材完整性 | 返工 assets 或打回 script |
| G6 | edit | 时间线完整性、停顿时间、音画预同步 | 返工 edit |
| G7 | compose | 输出探测、文字锐利度、运动时间 | 返工 compose 或打回 |
| G8 | publish | 元数据、打包、动画模式标签 | 返工 publish |
| FINAL | 全部 | 整体审查：锐利度、运动、准确性、风格 | 打回具体阶段 |

## 执行上限（反死循环保护）

| 上限 | 值 | 理由 |
|------|-----|------|
| 每阶段最大返工次数 | 3 | 防止完美主义死循环 |
| 每对阶段最大打回次数 | 1 | 防止乒乓 |
| 总打回次数上限 | 3 | 限制总返工量 |
| 总预算上限 | 可配置（默认 $2） | 花费硬停 |
| 总墙钟时长上限 | 15 分钟 | 整条管线超时 |

任一上限触发后：**带警告继续**，绝不无限阻塞。

## 与现有技能的集成

EP 不取代任何导演技能——它包裹它们。每个导演技能照文档原样工作。EP 额外提供：

1. **上下文注入**：导演收到含跨阶段信息的 EP_STATE；
2. **反馈注入**：被返工时导演收到具体的修改指令；
3. **预算意识**：导演收到剩余预算并据此调整工具选择；
4. **动画模式上下文**：导演知道选定模式与复用策略；
5. **风格锚点**：导演收到上游传来的一致性标记；
6. **数学准确性备注**：导演收到关于技术准确性的约束。

## 常见坑

- **过度返工**：在正确模式下"足够好"的动画，胜过五轮之后的"完美"版本。
- **忽视文字锐利度**：动画质量的头号问题。永远在最终分辨率下验证文字可读性。
- **让复用策略侵蚀**：提案说 3 个模板，场景规划就该用 3 个模板，不是 8 个独有设计。
- **不探测输出**：永远 ffprobe 最终视频。绝不仅凭元数据下结论。
- **丢失动画模式上下文**：提案选了 Manim，每个下游阶段都该知道这是 Manim 项目。不要让各阶段在已批准程序化动画时默认回退到通用 image_selector。
- **跳过数学准确性检查**：技术主题上这没有商量余地。错误的动画比没有动画更糟。
