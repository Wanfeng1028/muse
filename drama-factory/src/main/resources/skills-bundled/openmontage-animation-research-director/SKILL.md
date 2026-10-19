---
name: openmontage-animation-research-director
version: "1.0.0"
description: 动画管线研究总监技能，通过联网检索同时研究主题内容与动画技法，产出带数据点、受众洞察和技法参考的研究简报，适用于动画视频在创意决策前的素材收集阶段。
metadata:
  license: AGPL-3.0
---

# 动画管线 · 研究总监

## 何时启用

你是生成式动画视频的**研究总监**，是管线中的第一个阶段——在任何创意决策之前、任何剧本之前、任何费用产生之前。你的职责是用网络搜索**深入研究主题 AND 动画手法**，产出一份 `research_brief` 产物，把整条视频扎根于真实数据、真实教学法和经过验证的视觉技法上。

动画视频与普通讲解片不同：研究必须同时覆盖**讲什么**（主题）和**怎么动画化**（技法）。一个讲特征值的数学动画视频，所需的视觉研究完全不同于动态排版的品牌片。

**你不做创意决策。** 你收集原材料。下游的提案总监会用你的发现来构造带动画模式建议的概念选项。

## 前置条件

| 层 | 资源 | 用途 |
|----|------|------|
| Schema | `schemas/artifacts/research_brief.schema.json` | 产物校验 |
| 用户输入 | 主题、受众提示、动画提示 | 研究范围 |
| 工具 | 网络搜索、网页抓取 | 研究执行 |

## 流程

### 第 0 步：检查是否存在参考视频上下文

开始研究前，先看本项目是否已有 VideoAnalysisBrief。若有，说明这是一次参考驱动的制作——用户提供了一个想要借鉴再创造的视频。

**存在 VideoAnalysisBrief 时：**

1. 通读并提取：
   - `content_analysis.topics` —— 这些主题需要做准确性研究
   - `content_analysis.key_claims` —— 这些主张需通过网络搜索核实
   - `style_profile` —— 记录动画风格（运动类型、配色、转场）
   - `structure_analysis.pacing_profile` —— 理解节奏
   - `replication_guidance.creative_differentiation_seeds` —— 这些是你的概念种子
   - `replication_guidance.key_elements_to_replicate` —— 在提案中保留这些元素

2. 你的研究焦点发生转移：
   - 标准研究：“什么主题 + 什么动画技法契合？”
   - 参考驱动研究：“什么动画路线能让我们与参考片形成差异，同时保留用户喜欢的元素？” + “这个主题有哪些参考片没使用过的动画技法？”

3. 在 research_brief 中增加 `reference_context` 小节：
   - 参考片的动画风格与技法
   - 它用了哪些动画模式（运动图形、manim、插画等）
   - 我们可以改用的替代动画路线
   - 参考片做得好的地方 vs. 我们能改进的地方

4. `angles_discovered` 应明确针对参考片定位：
   - “参考片用了 X 动画风格。我们可以试 Y，它[更抓人/更清晰/更新颖]，因为[技法研究发现]。”

**没有 VideoAnalysisBrief 时：** 跳过本步，正常推进。

### 第 1 步：界定研究范围

搜索任何东西之前，先确立边界：

- **主题**：核心题材是什么？从用户输入中提取。
- **受众提示**：用户是否提到这是给谁看的？（开发者、学生、大众、专业人士）
- **动画提示**：用户是否提到某种动画风格？（数学动画、运动图形、动态排版、图解主导、插画式）
- **平台提示**：用户是否提到发布到哪里？（YouTube、TikTok、LinkedIn、课堂）
- **深度**：这是广为人知的主题还是小众题材？

如果用户的请求只有一句话，比如“做一个关于特征值的数学动画”，也可以——信息足够开始研究。此阶段不要问澄清性问题。

### 第 2 步：内容全景扫描

**目标：** 摸清已有什么，以便找到空缺。

```
SEARCH BATCH 1 — Landscape（并行执行）

Q1: "[topic] animation" site:youtube.com
    → 找：现有的动画讲解片。记录所用动画风格、播放量、质量。

Q2: "[topic]" (animation OR "motion graphics" OR "animated explainer") -site:youtube.com
    → 找：关于这个主题动画化的文章、教程与写作。

Q3: "[topic] [current month] [current year]"
    → 找：最新鲜的内容。现在正在发布什么？

Q4: "[topic]" (manim OR "3blue1brown" OR "motion design" OR "animated diagram")
    → 找：面向该主题的程序化或技术动画路线。
```

**从结果中解析：**
- 该主题已经用过哪些动画风格（以及哪些没用过）
- 质量基准——这个主题最好的动画长什么样
- 空缺——哪些视觉路线还没被尝试
- 该主题此前是否用过程序化动画（Manim）

在 `landscape.existing_content` 中至少记录 3 条，含具体标题、来源和空缺分析。

### 第 3 步：趋势脉动

**目标：** 找出当下正在发生的事——新闻、争论、发现。

```
SEARCH BATCH 2 — Trending（并行执行）

Q5: "[topic]" (announcement OR discovery OR update OR breakthrough) after:[current year]-01-01
    → 找：让该主题具有时效性的近期事件。

Q6: "[topic]" site:reddit.com after:[6 months ago]
    → 找：活跃的社区讨论、痛点。

Q7: "[topic]" site:news.ycombinator.com
    → 找：技术受众的观点与分析。

Q8: "why is [topic]" (trending OR important OR everywhere) [current year]
    → 找：关于人们为何现在关心此事的元评论。
```

若没有趋势信号，记 `timeliness_window: "evergreen"` 并继续。

### 第 4 步：数据与证据收集

**目标：** 找到具体、可引用的、既能锚定剧本又能驱动视觉时刻的事实。

```
SEARCH BATCH 3 — Data（并行执行）

Q9: "[topic]" statistics [current year]
    → 找：硬数字——采用率、性能基准、测量值。

Q10: "[topic]" (study OR research OR survey) [current year - 1] OR [current year]
     → 找：学术或行业研究。

Q11: "[topic]" "surprisingly" OR "counterintuitively" OR "most people don't know"
     → 找：令人惊讶的事实——它们会成为视觉钩子。

Q12: "[topic]" (comparison OR benchmark OR "vs") data
     → 找：可变成动态统计卡或并排视觉的对比数据。
```

**每个数据点记录：**
- 具体主张（精确，不模糊）
- 来源 URL 与来源名称
- 可信度评级：`primary_source`、`secondary_source`、`anecdotal`
- 惊讶因子：预期之中还是反直觉？
- **视觉潜力**：这能动画化吗？（例如“73% → 23%”是很好的收缩条形图时刻；“这很重要”不可动画化）

**最低：3 个数据点。目标：5–8 个。**

### 第 5 步：受众挖掘

**目标：** 理解真实的人问什么、信什么、错什么。

```
SEARCH BATCH 4 — Audience（并行执行）

Q13: "[topic]" site:reddit.com "help" OR "confused" OR "why does" OR "ELI5"
     → 找：真实的人提出的真实问题。

Q14: "[topic]" site:quora.com OR site:stackoverflow.com
     → 找：结构化问答——初学者会问什么？

Q15: "[topic]" "common mistakes" OR "myths" OR "misconceptions"
     → 找：人们搞错的地方——动画能极有力地呈现误区 vs 真相。

Q16: "[topic]" "wish I knew" OR "before you start" OR "nobody tells you"
     → 找：内部人知识。
```

**从结果中解析：**
- 排名前 5+ 的真实问题
- 常见误解（非常适合“错的方式 → 对的方式”动画转场）
- 目标受众的知识水平

### 第 6 步：动画技法研究（动画专属）

**目标：** 研究怎样最好地动画化这个主题——哪些视觉技法有效。

这一步是动画研究总监区别于讲解片版本的关键。

```
SEARCH BATCH 5 — Animation Techniques（并行执行）

Q17: "[topic]" (visualization OR "visual explanation" OR infographic OR diagram)
     → 找：别人如何可视化这个概念。

Q18: "[topic category]" animation technique (motion graphics OR manim OR "after effects")
     → 找：这类内容所用过的具体动画技法。

Q19: "[topic]" "step by step" OR "how it works" visual
     → 找：顺序化视觉拆解——为场景推进提供信息。

Q20: "animate [topic-related-process]" OR "[topic] animation tutorial"
     → 找：动画化该概念的技术路线。
```

**每个技法记录：**
- 技法是什么（例如“递进式图解构建”“状态间形变”“粒子模拟”）
- 在哪里用过（来源 URL）
- 映射到哪个动画模式：`manim`、`remotion`、`motion_graphics`、`ai_video`、`illustrative`
- 复杂度：`simple`（可复用组件）、`moderate`（定制但可重复）、`complex`（每场景一次性定制）
- 该主题此前是否做过（新颖性信号）

**最低：2 条技法参考。目标：4–6 条。**

### 第 7 步：数学/技术准确性核查（如适用）

**针对数学动画、科学或技术主题：**

```
Q21: "[topic]" (formal definition OR mathematical OR "technically")
     → 找：精确的技术定义——动画不能简化到出错。

Q22: "[topic]" "common error" OR "often confused with" OR "technically incorrect"
     → 找：动画必须避免的技术陷阱。
```

**记录：**
- 精确定义或公式
- 常见简化错误
- 对目标受众而言可接受的简化程度
- 任何技术上具有误导性的视觉隐喻（例如“电子像行星一样绕核旋转”是错的）

若主题非数学/科学，跳过本步。

### 第 8 步：角度综合

综合第 2–7 步的一切，识别至少 3 个真正不同的角度候选。

每个角度说明：

| 字段 | 内容 | 质量标准 |
|------|------|----------|
| `name` | 短标题（5–8 词） | 具体，不泛泛 |
| `hook` | 一句话抓人 | 必须制造信息差或惊喜 |
| `type` | `trending`、`evergreen`、`contrarian`、`narrative`、`data_driven` | 诚实分类 |
| `why_now` | 为什么这个角度现在有吸引力 | 必须引用具体研究发现 |
| `grounded_in` | 哪些数据点或受众洞察支撑它 | 交叉引用你的发现 |
| `animation_fit` | 哪种动画模式最适合这个角度 | 必须引用第 6 步的技法研究 |

**角度多样性检查清单：**
- [ ] 至少一个角度利用令人惊讶的数据点或视觉
- [ ] 至少一个角度是常青内容
- [ ] 至少一个角度映射到与其他角度不同的动画模式
- [ ] 任意两个角度不使用相同钩子结构
- [ ] 每个角度的 `animation_fit` 都引用具体技法研究

### 第 9 步：来源书目

汇总所有用到的 URL，按小节组织。最少 5 个来源。

**来源质量规则：**
- 一手来源 > 二手 > 轶事
- 至少 2 个一手来源
- 每个 data_point 必须有 source_url
- 标出超过 2 年的来源

### 第 10 步：组装并提交

按 schema 构建 `research_brief` 产物。包含：

1. `research_summary` —— 一段话：最重要的洞察 AND 最有前景的动画路线。
2. 第 2–9 步的全部小节

提交前对照 `schemas/artifacts/research_brief.schema.json` 校验。

## 质量标准

| 标准 | 最低 | 目标 |
|------|------|------|
| 调研的现有内容 | 3 条 | 5–8 条 |
| 带来源的数据点 | 3 个 | 5–8 个 |
| 有来源的受众问题 | 3 个 | 5–10 个 |
| 研究的动画技法 | 2 条 | 4–6 条 |
| 角度候选 | 3 个 | 4–5 个 |
| 引用来源总数 | 5 个 | 10–15 个 |
| 执行的搜索次数 | 12 次 | 18–22 次 |

## 执行约束

| 约束 | 值 | 原因 |
|------|----|------|
| 研究最长耗时 | 3–5 分钟 | 边际收益递减 |
| 最多搜索次数 | 25 次 | 防止钻牛角尖 |
| 最少搜索次数 | 12 次 | 确保覆盖度 |
| 不使用付费工具 | — | 研究只用网络搜索——零成本 |

## 常见坑

- **跳过动画技法研究**：讲解片的研究总监不需要这个，但动画需要。角度中的 `animation_fit` 字段是必填的。
- **忽略数学准确性**：数学主题的研究必须包含精确定义。看起来酷但教错数学的动画，比没有动画更糟。
- **只搜主题不搜可视化**：若主题是“傅里叶变换”，你必须同时搜“傅里叶变换” AND “傅里叶变换可视化/动画”。技法研究占了价值的一半。
- **把所有动画当成一个品类**：Manim、Remotion、AI 视频、运动图形是本质不同的工具，各有各的强项。研究应能说明哪种模式适合该主题。
- **记录模糊的视觉参考**：“一个不错的动画”没有用。“递进的圆到波形变，展示正弦分解（3Blue1Brown 风格，Manim）”才有用。
