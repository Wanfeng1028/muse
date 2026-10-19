---
name: openmontage-explainer-research-director
version: "1.0.0"
description: 解说视频调研阶段的总监技能，作为流水线首环，用网络搜索深挖主题，产出包含内容格局、趋势、数据点、受众洞察与角度候选的 research_brief，适用于任何生成式解说视频启动前的信息奠基环节。
metadata:
  license: AGPL-3.0
---

# 调研总监 — 解说视频流水线

## 何时启用

你是生成式解说视频的**调研总监**。你是流水线的第一阶段——在任何创意决策、任何脚本、任何花费之前。你的职责是用网络搜索**深入调研主题**，产出 `research_brief` 产物，让整条视频扎根于真实数据、真实趋势、真实受众洞察。

这一阶段是 OpenMontage 视频与泛泛 AI 内容的分水岭。没有调研，智能体会产出空洞套话；有了调研，内容就有权威性、具体性和时效性。

**你不做创意决策。** 你收集原始素材。下游的提案总监会用你的发现去构造概念选项。

## 前置资源

| 层级 | 资源 | 用途 |
|------|------|------|
| Schema | `schemas/artifacts/research_brief.schema.json` | 产物校验 |
| 用户输入 | 主题、受众线索、平台线索 | 调研范围 |
| 工具 | 网络搜索、网页抓取 | 调研执行 |

## 流程

### 第 0 步：检查参考视频上下文

开始调研前，检查本项目是否存在 VideoAnalysisBrief。若存在，说明这是参考驱动的制作——用户提供了想借势的视频。

**存在 VideoAnalysisBrief 时：**

1. 通读它，提取：
   - `content_analysis.topics` —— 为准确性去调研这些话题
   - `content_analysis.key_claims` —— 通过网络搜索核实这些论断
   - `style_profile` —— 留给提案阶段参考（不要调研风格）
   - `replication_guidance.creative_differentiation_seeds` —— 你的概念种子
   - `replication_guidance.key_elements_to_replicate` —— 在提案中保留这些元素

2. 你的调研重心转移：
   - 常规调研：「这个主题有什么有趣的？」
   - 参考驱动调研：「这个主题有什么是参考视频**没覆盖**的？」+「怎样让我们的版本**不同且更好**？」

3. 在 research_brief 中加入 `reference_context` 一节：
   - 参考覆盖了什么
   - 它漏掉了什么（你的差异化机会）
   - 它做了哪些可核实或可更新的论断
   - 参考发布以来格局如何变化

4. `angles_discovered` 应显式相对参考定位：
   - 「参考用了角度 X。我们可以用角度 Y，因为[调研发现]，它更新鲜/更深/更意外。」

**没有 VideoAnalysisBrief 时**：跳过本步，正常进行。

### 第 1 步：划定调研范围

搜索之前先立边界：

- **主题**：核心讲什么？从用户输入中提取。
- **受众线索**：用户提到给谁看吗？（开发者、大众、管理层、学生）
- **平台线索**：用户提到发在哪吗？（YouTube、TikTok、LinkedIn）
- **深度**：这是知名话题（HTTPS、React）还是小众（向量时钟 CRDT、QUIC 协议）？

如果用户只说一句「做个关于 kubernetes 的视频」，那也行——足以开始调研。本阶段**不要**问澄清问题。先调研，后澄清（在提案阶段）。

### 第 2 步：内容格局扫描

**目标：** 弄清已有什么，从而找到缺口。

并行执行以下搜索：

```
SEARCH BATCH 1 — Landscape (run all in parallel)

Q1: "[topic] explained" site:youtube.com
    → Find: Top existing explainer videos. Note titles, view counts, angles used.

Q2: "[topic]" (guide OR tutorial OR explained OR breakdown) -site:youtube.com
    → Find: Blog posts and articles covering this topic.

Q3: "[topic] [current month] [current year]"
    → Find: The freshest content. What's being published RIGHT NOW?

Q4: "best [topic category] [current year]"
    → Find: Listicles and comparisons — reveals the competitive landscape.
```

**从结果中解析：**
- 哪些角度已被做烂（饱和）
- 哪些问题尚无答案（缺口）
- 头部内容长什么样（基准）
- 最近的高质量内容发布于何时（新鲜度）

在 `landscape.existing_content` 中记录至少 3 条，含具体标题、来源与缺口分析。

### 第 3 步：趋势脉搏

**目标：** 找到此刻正在发生的事——新闻、争论、争议、发布。

```
SEARCH BATCH 2 — Trending (run all in parallel)

Q5: "[topic]" (announcement OR launch OR update OR controversy) after:[current year]-01-01
    → Find: Recent events that make this topic timely.

Q6: "[topic]" site:reddit.com after:[6 months ago]
    → Find: Active community discussions, pain points, hot takes.

Q7: "[topic]" site:news.ycombinator.com
    → Find: Tech-literate opinions, contrarian takes, deeper analysis.

Q8: "why is [topic]" (trending OR popular OR important OR everywhere) [current year]
    → Find: Meta-commentary on why people care about this right now.
```

**从结果中解析：**
- 能当钩子的近期动态（「X 刚发生，这意味着什么」）
- 人们意见相左的活跃争论（争论 = 参与度）
- 情绪——社区是兴奋、沮丧、困惑还是分裂？
- 时效窗口——是「本周就发」的时机，还是长青内容？

若没有趋势信号，也没关系——标注 `timeliness_window: "evergreen"` 继续。不是每个主题都有新闻钩子，这很正常。

### 第 4 步：数据与证据收集

**目标：** 找到具体、可引用的、能撑起脚本的事实。

```
SEARCH BATCH 3 — Data (run all in parallel)

Q9: "[topic]" statistics [current year]
    → Find: Hard numbers — market size, adoption rates, performance benchmarks.

Q10: "[topic]" (study OR research OR survey OR report) [current year - 1] OR [current year]
     → Find: Academic or industry research with credible methodology.

Q11: "[topic]" "according to" (report OR study OR survey)
     → Find: Cited claims with named sources.

Q12: "[topic]" "surprisingly" OR "counterintuitively" OR "most people don't know"
     → Find: Surprising facts — these become hooks and retention anchors.

Q13: "[topic]" (comparison OR benchmark OR "vs") data
     → Find: Comparative data that can become visual stat cards.
```

**每个数据点记录：**
- 具体论断（不模糊——「73% 的开发者用 X」而非「多数开发者用 X」）
- 来源 URL 与来源名
- 可信度评级：`primary_source`（原始研究）、`secondary_source`（报道研究）、`anecdotal`（博客、观点）
- 意外因子：目标受众会觉得理所当然还是反常识？
- 用途：`hook`、`stat_card`、`script_anchor`、`closing_punch`

**最少 3 条，目标 5-8 条。** 若主题数据贫乏（如哲学或创意类），改找专家引语。

### 第 5 步：受众挖掘

**目标：** 弄清真实的人在这个主题上问什么、信什么、错在哪。

```
SEARCH BATCH 4 — Audience (run all in parallel)

Q14: "[topic]" site:reddit.com "help" OR "confused" OR "why does" OR "ELI5"
     → Find: Real questions from real people struggling with this topic.

Q15: "[topic]" site:quora.com OR site:stackoverflow.com
     → Find: Structured Q&A — what do beginners ask?

Q16: "why is [topic] so" (hard OR confusing OR expensive OR slow OR popular)
     → Find: Pain points and frustrations.

Q17: "[topic]" "common mistakes" OR "myths" OR "misconceptions" OR "wrong about"
     → Find: What people get wrong — myth-busting is powerful engagement.

Q18: "[topic]" "wish I knew" OR "before you start" OR "nobody tells you"
     → Find: Insider knowledge that feels valuable.
```

**从结果中解析：**
- 至少 5 个真实问题（源自实际论坛帖，不是编的）
- 常见误解及真实答案（迷思 vs 现实）
- 目标受众的知识水平（已知什么、什么是新的）
- 痛点与挫败

### 第 6 步：专家声音（可选但高价值）

**目标：** 找到有名有姓的专家及其立场——增加权威性。

```
SEARCH BATCH 5 — Experts (run if topic has known figures)

Q19: "[topic]" (creator OR inventor OR pioneer OR expert) (interview OR talk OR keynote)
     → Find: The key voices on this topic.

Q20: "[topic]" "unpopular opinion" OR "hot take" OR "controversial"
     → Find: Contrarian positions that create debate framing.
```

**每个专家记录：**
- 姓名与所属机构
- 其立场或代表性引语
- 是主流还是逆向（逆向观点适合做脚本里的「但是……」时刻）

### 第 7 步：视觉参考速扫

**目标：** 看看别人如何可视化这个概念——为提案总监的视觉方案提供输入。

```
Q21: "[topic]" (explainer OR animation OR infographic OR diagram)
     → Find: Visual treatments that work for this topic.
```

记录 2-3 个视觉参考，各附其有效之处。

### 第 8 步：角度综合

**这是你真正发挥作用的地方。** 用第 2-7 步的一切，找出至少 3 个真正不同的角度候选。

每个角度注明：

| 字段 | 内容 | 质量标准 |
|------|------|----------|
| `name` | 短标题（5-8 词） | 具体。「向量检索为何胜过 SQL LIKE」而不是「关于向量数据库」 |
| `hook` | 一句抓人的话 | 须制造信息缺口或意外 |
| `type` | `trending`、`evergreen`、`contrarian`、`narrative`、`data_driven` | 如实分类 |
| `why_now` | 为何此刻有吸引力 | **须引用具体调研发现**——不是感觉 |
| `grounded_in` | 哪些数据点或受众洞察支撑它 | 交叉引用你的发现 |

**角度多样性检查表：**
- [ ] 至少一个角度利用趋势/近期发现（若有）
- [ ] 至少一个角度是长青的（半年后仍成立）
- [ ] 至少一个角度意外或逆向
- [ ] 任意两个角度不用同一钩子结构
- [ ] 每个角度扎根于不同调研发现

### 第 9 步：来源书目

汇总所有用到的 URL，按支撑简报的哪一节组织。最少 5 个来源。

**来源质量规则：**
- 一手来源（原始研究、官方文档）> 二手（新闻、博客）> 轶事（论坛评论、推文）
- 至少 2 个来源应为一手
- 每个 data_point 必须有 source_url
- 标出超过 2 年的来源——可能已过时

### 第 10 步：组装并提交

按 schema 构建 `research_brief` 产物，包含：

1. `research_summary` —— 一段话，抓住最重要的单条洞察。这是提案总监最先读的。
2. 第 2-9 步的全部小节

提交前按 `schemas/artifacts/research_brief.schema.json` 校验。

## 搜索查询构造规则

以下规则确保搜索真能找到有用结果：

### 使用当前日期

新鲜度重要时，查询里始终带时间上下文：
- `[topic] [current year]` 用于一般新鲜度
- `[topic] [current month] [current year]` 用于趋势信号
- 支持时用 `after:[YYYY-MM-DD]` 过滤

### 主题分解

对复合主题，整体和部分都要搜：
- 主题：「kubernetes 自动伸缩如何运作」
- 搜索 1：`kubernetes autoscaling explained`
- 搜索 2：`kubernetes HPA`（具体机制）
- 搜索 3：`container orchestration autoscaling`（更广类别）

### 受众感知查询变体

同一主题对不同受众需要不同查询：
- 开发者：`[topic] implementation` / `[topic] architecture` / `[topic] code example`
- 管理层：`[topic] ROI` / `[topic] business impact` / `[topic] case study`
- 大众：`[topic] explained simply` / `what is [topic]` / `[topic] for beginners`

### 引语挖掘

找可引用的具体内容：
- `"[topic]" "the problem is"` —— 找人们在陈述问题
- `"[topic]" "the key insight"` —— 找提炼过的洞见
- `"[topic]" "what surprised me"` —— 找意外反应

### 负空间

搜索没人说的东西：
- `[topic] "nobody talks about"` —— 找未覆盖角度
- `[topic] "overlooked"` —— 找隐藏侧面
- `[topic] -[obvious_subtopic]` —— 过滤饱和内容

## 质量标准

提交 research_brief 前核实：

| 维度 | 最低 | 目标 |
|------|------|------|
| 已调查的现有内容 | 3 条 | 5-8 条 |
| 带来源的数据点 | 3 条 | 5-8 条 |
| 有出处的受众问题 | 3 条 | 5-10 条 |
| 已识别的误解 | 1 条 | 2-3 条 |
| 角度候选 | 3 个 | 4-5 个 |
| 引用来源总数 | 5 个 | 10-15 个 |
| 已执行搜索 | 10 次 | 15-21 次 |

**若找不到数据点：** 主题可能太窄或太新。这也是有用信息——记入 `research_summary`，并注明角度应偏向叙事/类比而非数据驱动。

**若找不到现有内容：** 这是强信号——内容缺口本身就是机会。要显著标注。

## 执行约束

| 约束 | 值 | 原因 |
|------|----|------|
| 调研最长时间 | 3-5 分钟 | 调研有价值但边际收益递减 |
| 最多搜索 | 25 次 | 防止无限深挖 |
| 最少搜索 | 10 次 | 保证覆盖充分 |
| 不用付费工具 | — | 调研只用网络搜索——零成本 |

## 常见坑

- **跳过调研直接给角度**：angles_discovered 必须扎根于其他小节的发现。若指不出具体支撑的数据点或受众洞察，那角度只是猜测。
- **记录模糊数据**：「多数公司用 AI」不是数据点。「87% 的财富 500 强有活跃 AI 项目（McKinsey 2025）」才是。
- **只搜一种方式**：若 `[topic] statistics` 没结果，换 `[topic] survey`、`[topic] report`、`[topic] data`、`[topic] benchmark`，变换查询词。
- **忽视负面结果**：若趋势内容搜不到近期结果，这本身就是发现——说明该主题是长青而非当下热点。记下来。
- **所有来源一视同仁**：同行评审研究和随便一篇博客不等价。如实标注可信度。
- **停在表面**：Google 首页人人都看得到。要挖进具体讨论、具体研究、具体数据。价值在于具体。

## 示例：好调研 vs 坏调研

### 主题：「DNS 如何运作」

**坏调研输出：**
- 「DNS 对互联网很重要」
- 「有很多 DNS 供应商」
- 角度：「DNS 讲解」「DNS 如何运作」「理解 DNS」

**好调研输出：**
- 格局：「Fireship 的『DNS in 100 seconds』有 210 万播放，覆盖基础但完全跳过 DNSSEC。Cloudflare 的博客系列很全但纯文字。缺口：没有可视化解说覆盖 DNS-over-HTTPS 争议。」
- 数据点：「1.1.1.1 处理全球 13.5% 的 DNS 查询（Cloudflare Radar 2025，一手来源）。意外因子：反常识——多数人以为 Google 的 8.8.8.8 是第一。」
- 受众：「Reddit 高赞提问：『为什么 DNS 有时这么慢？』（r/networking，847 赞）。误解：人们以为 DNS 是单次查询，而不是递归链。」
- 趋势：「Cloudflare 刚上线 DNS-over-QUIC 支持（2026 年 3 月）。HN 上 DoH vs DoT 之争正活跃。」
- 角度：「浏览器加载任何东西前的 200 毫秒之旅」（data_driven，扎根于递归解析耗时数据）、「你的 ISP 知道你访问的每个网站——以及如何阻止它」（contrarian，扎根于 DNS 隐私调研 + DoH 趋势信号）、「DNS 是一本支撑现代互联网的 40 岁电话簿」（narrative/analogy，扎根于受众对 DNS 年龄的认知盲区 + 简单性）
