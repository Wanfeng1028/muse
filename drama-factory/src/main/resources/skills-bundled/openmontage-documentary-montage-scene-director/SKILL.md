---
name: openmontage-documentary-montage-scene-director
version: "1.0.0"
description: 纪录片蒙太奇流水线的分镜导演技能，把主题 brief 拆成可检索的槽位清单并撰写描述与 query、分配来源与标记主镜，用于为素材检索层提供输入。
metadata:
  license: AGPL-3.0
---

# 分镜导演 · 纪录片蒙太奇流水线

## 适用场景

brief 已就绪。现在你要把一个主题之问变成检索层可填充的**具体槽位清单**。每个槽位是一个意图（“黄昏门口的一道剪影”）加上能在真实世界里找到它的 query（Pexels/Archive.org/NASA/Wikimedia/Unsplash）。

这是全流水线**最有创意**的阶段。检索质量完全取决于你写的槽位描述。

## 前置依赖

| 层 | 资源 | 用途 |
|----|------|------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | 产物校验 |
| 上游产物 | `state.artifacts["idea"]["brief"]` | 主题之问、调性、时长、结构 |
| 参考 | `skills/pipelines/documentary-montage/executive-producer.md` | 跨阶段规则 |
| 工具 | 暂无——本阶段纯规划 | — |

## 心智模型

分镜导演的职责**不是**“挑片段”，而是“把片段该长什么样描述得足够清楚，让 CLIP 找得到”。

把自己当**勘景师**，不是片库管理员。

- 片库管理员说：*“城市雨景蒙太奇，15 支片段”*。
- 勘景师说：*“蓝调时刻，雨斜刮过公交车窗，乘客面部柔焦，红绿灯透过玻璃晕成红绿”*。

后者才是 CLIP 能真正排序的东西。前者只是类目标签，CLIP 只会弱匹配、不加区分。

## 流程

### 1. 把结构换算成节拍数

读 brief 的 `duration_seconds` 与 `shape`，推出槽位数量。除调性另有指示，用以下默认值：

| 调性 | 平均停留 | 每 60s 槽位数 |
|------|----------|---------------|
| 挽歌式 | 4.0s | ~15 |
| 虔敬式 | 3.5s | ~17 |
| 梦幻式 | 3.0s | ~20 |
| 反讽式 | 2.0s | ~30 |
| 紧迫式 | 1.2s | ~50 |

然后按结构规划弧线：

- **清单**：N 个均质槽位，无拐点。
- **前后对照**：N/2 前段槽位 + 1 个转折槽位 + N/2 后段槽位。
- **三幕**：铺陈（30%）→ 转折（40%）→ 释放（30%）。
- **单图扩展**：1 个锚点画面 + N 个变体。

动笔写任何槽位前，先把节拍数写下来。

### 2. 把主题之问拆成具体节拍

取 brief 中那**一句**主题之问，用感官语言作答。不是主题词——是质感。

**示例——“雨让你看见城市的什么？”**

差的拆解（抽象、不可检索）：

- “建立城市情绪”
- “被困在天气里的感觉”
- “雨的普遍性”

好的拆解（具体、可检索）：

- 一滴雨落在干燥沥青上，慢动作
- 门口撑开的伞，可见一只手
- 水洼里倒映的霓虹招牌
- 雨斜刮过公交车窗，乘客柔焦
- 出租车顶灯穿破大雨，长焦
- 雨水口吞下落叶与水流，俯拍
- 摊贩给果蔬车拉上塑料布
- 湿鹅卵石巷，钨丝路灯下升起蒸汽
- 孩童的胶靴踩进水洼
- 透过雨幕看见亮灯的公寓窗

每一条都是一个**镜头**，都能被 CLIP 排序，也都是同一个念头的**不同角度**——这正是清单式蒙太奇分量的来源。

### 3. 撰写槽位描述

每个槽位都带一个 `description` 字段，这是 CLIP 要嵌入并排序的文本。写得像一条好的素材标签串——名词加形容词，不要意图动词，不要情绪词。

**模板：**

```
<主体>, <动作/姿态>, <环境>, <光线>, <年代/质感提示>
```

**好例：**

- `"a single raindrop hitting dry asphalt, close up, slow motion, warm streetlamp glow"`
- `"empty city sidewalk at night after rain, reflected neon, handheld, 1970s grain"`
- `"an umbrella opening in a doorway, hand visible, diffused afternoon light, shallow focus"`

**差例：**

- `"the feeling of arriving home"`——情绪词，无主体
- `"a warm welcoming moment"`——形容词堆砌，无画面
- `"someone going through a door in a symbolic way"`——意图，无镜头

经验法则：你若想象不出具体一张照片，CLIP 也想象不出。

### 4. 每槽写 2–3 条 query

槽位描述是给 CLIP 排序用的，query 是给 `corpus_builder` 填充候选池用的。二者职责不同，写法也要不同。

每个槽位给一个 `queries` 数组，2–3 条：

1. **字面 query**——最直接的素材检索短语，就是 Pexels 用户会敲的那种。`"raindrop on asphalt slow motion"`。
2. **侧向 query**——同一念头的不同角度或尺度。`"wet pavement close up"`。
3. **联想 query**（可选，用于主镜槽位）——可能带出字面 query 漏掉的质感片段的邻近概念。`"first rain city street"`。

对素材检索引擎来说短 query 优于长 query。每条 2–5 个词，不要填充词。

### 5. 按槽分配来源（考虑年代）

读 `brief.era_mix`。根据素材分布给每个槽位指定一到多个 `preferred_sources`：

| 来源 | 强项 | 何时用 |
|------|------|--------|
| `pexels` | 现代高清、干净镜头、人物、城市、自然 | 现代/任意年代的默认选择 |
| `pixabay_video` | 大型社区库，自然、人物、科技、生活 | Pexels 缺料时补位；通用素材广 |
| `coverr` | 精选电影感 B-roll，自然、城市、抽象背景 | 高质量建场镜头、定调镜头、现代生活 |
| `mixkit` | Envato 精选 HD/4K，自然、商业、科技 | 高级感 B-roll、干净自然素材、免署名 |
| `archive_org` | Prelinger 家庭录像、中世纪教育片、1940s–1980s 质感 | 复古、反讽、梦幻、任何怀旧向 |
| `nara` | 美国国家档案馆——二战、冷战、阿波罗、民权、总统 | 美国历史纪录片、军事、政府、太空竞赛 |
| `loc` | 国会图书馆——早期电影、新闻片、文化录音 | 1928 年前公版素材、美国史、民俗 |
| `pond5_pd` | Pond5 公版——一战/二战、早期电影、历史演讲 | 档案/复古素材、梅里爱、爱迪生、新闻片 |
| `videvo` | 9 万+免费片段，自然、航拍、城市、抽象、延时 | 大型免费库，以不同贡献者补充 Pexels |
| `nasa` | 轨道看地球、天文、飞行、尺度影像 | 虔敬向、一切关于尺度/太空/行星/飞行 |
| `esa` | 欧洲航天任务、哈勃/韦布影像、地球观测 | 欧洲太空内容，补足 NASA 的非美任务 |
| `jaxa` | 日本航天任务、隼鸟、ISS 希望号、H-IIA 火箭 | 亚洲太空内容，独特视角 |
| `noaa` | 深海 ROV 影像、海洋生物、珊瑚礁、天气、飓风 | 海洋/水下、独特深海内容、天气现象 |
| `dareful` | 精品 4K 自然——山、林、瀑、延时 | 高质量自然 B-roll、视觉风格统一、航拍 |
| `wikimedia` | Commons 图片与 CC 视频、市政/纪录/公共事件 | 公共空间、地标、抗议、城市质感、教育素材 |
| `unsplash` | 精致编辑风静帧、生活方式、类产品摄影 | 动态素材稀薄时的现代静帧补充 |

若 `era_mix = "vintage"`，槽位偏向 `archive_org`，且 query 用时代相称的词汇（“commuter”“housewife”“suburb”，而非“influencer”“wfh”“coworking”）。

若 `era_mix = "any"`，逐槽混合来源——由分镜导演按节拍含义决定哪个槽用哪个源。

#### 儿童 / 童话内容

当 brief 的 `tone` 或 `target_audience` 指向儿童内容（童话、睡前故事、儿童讲解、动画故事）时，**把视觉策略从实拍素材切换为 Pixabay 上的 AI 生成奇幻片段**。

Pixabay 社区库包含数千条 AI 生成奇幻动画（发光森林、魔法景观、奇幻生物），在儿童吸引力上远超实拍素材。

**儿童内容的 query 改写规则：**

| 槽位意图 | 实拍 query | 奇幻改写 |
|----------|------------|----------|
| 花园/自然 | `garden flowers morning` | `enchanted fairy tale garden glowing magical` |
| 昆虫/生物 | `caterpillar leaf close up` | `fairy tale caterpillar magical forest glowing` |
| 蜕变/茧 | `chrysalis butterfly cocoon` | `magical chrysalis enchanted tree glowing` |
| 蝴蝶/飞行 | `butterfly flying sky` | `fantasy butterfly glowing magical wings` |
| 日落/风景 | `sunset landscape golden` | `enchanted fantasy landscape magical sunset` |
| 雨/天气 | `rain leaves gentle` | `fairy tale rain magical forest enchanted` |
| 夜空/星辰 | `milky way timelapse` | `fantasy night sky magical stars enchanted` |
| 海洋/水 | `river water golden` | `magical underwater world fairy tale` |
| 山/航拍 | `mountain peaks golden` | `fantasy mountain castle fairy tale magical` |
| 森林/树 | `forest path morning` | `fairy tale mushroom forest glowing enchanted` |

**来源路由：** 所有槽位设 `preferred_sources: ["pixabay_video"]`。Pixabay 是唯一拥有深厚 AI 奇幻库的免费源。不要混用实拍与奇幻——风格冲突会破坏儿童的沉浸感。

**能带出 AI 奇幻内容的关键词：** `fairy tale`、`fantasy`、`enchanted`、`magical`、`glowing`、`dreamy`、`mystical`、`fairy`、`enchanted forest`、`magical world`。

### 6. 标记主镜槽位

每支蒙太奇都有 2–3 个全片所系的槽位：开场画面、转折、收尾画面。在槽位元数据里标 `hero: true`。

主镜槽位享有：

- 更长停留（2–4s，而非调性默认值）
- 素材阶段更大候选池（k=30 而非 k=10）
- 更多 query（3 条而非 2 条）

### 7. 给素材阶段留出空间

不要过度指定。素材导演的职责是把候选按你的描述排序。你若把描述和具体片段都钉死，既没做好素材导演的工作，也抢了它的创意空间。

规则：像在电话里向研究助理描述那样描述槽位——具体到能认出，宽松到能被惊喜。

### 8. 落盘分镜表

用 `scene_plan.schema.json` 产物，一个槽位对应一个 `scene`。本流水线中，把纪录片蒙太奇专属字段放进每个 scene 的 `metadata`。规范结构：

```json
{
  "version": "1.0",
  "scenes": [
    {
      "id": "slot_01",
      "type": "broll",
      "description": "a single raindrop hitting dry asphalt, close up, slow motion, warm streetlamp glow",
      "start_seconds": 0.0,
      "end_seconds": 3.5,
      "narrative_role": "establish_context",
      "hero_moment": true,
      "texture_keywords": ["wet", "slow motion", "streetlamp"],
      "required_assets": [
        { "type": "video", "description": "raindrop on asphalt", "source": "source" }
      ]
    }
  ],
  "metadata": {
    "pipeline": "documentary-montage",
    "shape": "list",
    "tone": "elegiac",
    "thematic_question": "What does rain show you about a city?",
    "slots": [
      {
        "id": "slot_01",
        "description": "a single raindrop hitting dry asphalt, close up, slow motion, warm streetlamp glow",
        "hero": true,
        "preferred_sources": ["pexels", "archive_org"],
        "queries": [
          "raindrop on asphalt slow motion",
          "wet pavement close up",
          "first rain city street"
        ],
        "min_duration": 3.0,
        "target_hold_seconds": 3.5,
        "era_hint": "any"
      }
    ]
  }
}
```

`scenes[]` 数组满足 schema。`metadata.slots[]` 才是素材导演真正读取的内容——它携带 `scene_plan.schema.json` 并不知晓的检索专属字段（`queries`、`preferred_sources`、`hero`、`era_hint`）。

### 9. 质量门

- 槽位数与第 1 步的节拍换算一致。
- 每个槽位 `description` 遵循名词加形容词模板——无情绪词，无意图动词。
- 每个槽位有 2–3 条短 query（每条 ≤5 词）。
- 至少 2 个槽位标为 `hero`。
- `target_hold_seconds` 之和在 `brief.duration_seconds` 的 ±10% 内。
- 若 `era_mix = "vintage"`，至少 60% 槽位在 `preferred_sources` 中列出 `archive_org`。
- `metadata.thematic_question` 与 brief 逐字一致（自检是否漂移）。

## 常见陷阱

- **把槽位描述写成意图而非画面。**“进门前的迟疑一刻”是剧本提示，不是 CLIP query；“女人在门廊上站定，手靠近门把”才是。
- **类目式 query。** `"home"` 和 `"family"` 什么都匹配、什么都匹配不到。要具体名词：门、垫、钥匙、门厅、鞋。
- **单 query 槽位。** 第二条 query 是便宜的保险——第一条返回垃圾时，库中仍有可用之物。
- **忘记时长换算。** 90 秒挽歌式约 15 个 6s 停留。你若写了 40 个槽位，那是不小心写成了紧迫式。
- **复古 brief 漏写 `era_hint`。** Pexels 会把 2020s 高清素材灌满库，把 Prelinger 素材埋掉。
- **让主题之问漂移。** brief 说“回家”，你的槽位表里却有三支飞机镜头，那片子就变成关于旅行而非家。起草后重读 brief。

## 实操示例——“雨中的一分钟”

- 时长：90s，挽歌式调性 → 约 15 个槽位，每个约 6s。
- 结构：清单（天气与城市的目录）。
- 主题之问：“雨让你看见城市的什么？”

槽位草图（节选）：

1. **主镜** 一滴雨落在干燥沥青上，慢动作
2. 门口撑开的伞，午后柔光
3. 水洼里倒映的霓虹招牌，手持
4. 雨斜刮过公交车窗，乘客柔焦
5. 出租车顶灯穿破大雨，长焦
6. 雨水口吞下落叶与水流，俯拍
7. 摊贩给果蔬车拉上塑料布
8. 湿鹅卵石巷，蒸汽升起，钨丝路灯
9. 灰天空下的屋顶天线，广角
10. 孩童胶靴踩进水洼，低角度
11. **主镜** 透过雨幕看见亮灯的公寓窗
12. 夜间雨刷，窗外城市彩灯
13. 停放的自行车座上雨珠，微距
14. 车站瓷砖地面上积水里的脚印
15. **主镜** 灰云中裂开的第一片蓝天

每个槽位配：

- 名词加形容词模板的 `description`
- 2–3 条短 query（例如槽位 5：`"taxi heavy rain"`、`"yellow cab wet street night"`、`"city traffic downpour"`）
- `preferred_sources`（槽位 1–6 → pexels+archive_org，槽位 8 → archive_org 取时代质感，槽位 11 → pexels）
- 槽位 1、11、15 标 `hero: true`
- `target_hold_seconds` 合计约 90

这就是素材导演将据以运行检索的产物。

---

## 门禁提醒（强制）

本阶段以人工审批为门（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 看板会渲染产物），并**结束本轮回复**。不要在同一个回复里启动下一阶段。审批按门独立——早先的“继续”不覆盖本门。
