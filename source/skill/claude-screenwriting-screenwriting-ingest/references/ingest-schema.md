# Ingest 输出 Schema

LLM 在 ingest 时按此 schema 输出结构化 JSON，随后转化为 wiki 页面。

---

## 顶层结构

```json
{
  "source": {
    "filename": "string",
    "type": "outline | character | feedback | mixed",
    "summary": "string (一句话摘要)",
    "word_count": "number"
  },
  "beats": [...],
  "characters": [...],
  "meta": {...}
}
```

---

## beats 数组

```json
{
  "beat_number": "number | null (1-15, null if uncertain)",
  "beat_name": "string (中文 beat 名)",
  "content": "string (该 beat 的具体事件/情节)",
  "emotion": "string (情绪走向)",
  "conflict": "string (冲突描述)",
  "value_shift": "string (价值从X到Y)",
  "characters_involved": ["string (角色名)"],
  "confidence": "high | medium | low",
  "evidence": "string (原文支撑片段，用于溯源)"
}
```

### Beat 编号映射

| # | beat_name |
|---|-----------|
| 1 | 开场画面 |
| 2 | 主题陈述 |
| 3 | 铺垫 |
| 4 | 催化剂 |
| 5 | 犹豫 |
| 6 | 进入第二幕 |
| 7 | B故事 |
| 8 | 游戏时间 |
| 9 | 中点 |
| 10 | 反派逼近 |
| 11 | 一无所有 |
| 12 | 灵魂黑夜 |
| 13 | 进入第三幕 |
| 14 | 终局 |
| 15 | 终场画面 |

---

## characters 数组

```json
{
  "name": "string",
  "archetype": "hero | mentor | ally | shadow | shapeshifter | guardian | herald | trickster | other",
  "description": "string (一句话定位)",
  "tab1_image": {
    "gender": "string | null",
    "age_group": "string | null",
    "physical_tags": ["string"],
    "behavior_tags": ["string"],
    "social_identity": ["string"]
  },
  "tab2_truth": {
    "wants": "string | null",
    "needs": "string | null",
    "motivation": "string | null",
    "shard_of_glass": "string | null",
    "opinions": "string | null",
    "attitudes": "string | null",
    "contradiction": {
      "surface": "string | null",
      "truth": "string | null"
    },
    "arc_type": "positive | negative | flat | circular | null",
    "changes": "string | null"
  },
  "tab3_dimensions": {
    "big_five": {
      "openness": "number 1-5 | null",
      "conscientiousness": "number 1-5 | null",
      "extraversion": "number 1-5 | null",
      "agreeableness": "number 1-5 | null",
      "neuroticism": "number 1-5 | null"
    },
    "virtues": ["string"],
    "six_flaws": ["string"],
    "backstory": "string | null",
    "relationships": "string | null"
  },
  "confidence": "high | medium | low",
  "evidence": "string"
}
```

---

## meta 对象

```json
{
  "logline": "string | null",
  "genre": "string | null (必须从 Save the Cat 10 大类型中选一个)",
  "theme": ["string (题材标签，1-3个)"],
  "tone": "string | null",
  "target_audience": "string | null",
  "comparable_works": ["string (2-3部对标作品名)"]
}
```

### meta 各字段生成规范

#### genre — Save the Cat 10 大故事类型（必选其一）

这是故事的**结构引擎**，决定了角色配置和 beat 承诺。

| 类型 | 英文 | 核心引擎 |
|------|------|---------|
| 屋里有怪物 | Monster in the House | 封闭空间 + 怪物 + 角色的罪 |
| 金羊毛 | Golden Fleece | 公路/追寻 + 沿途遭遇改变主角 |
| 如愿以偿 | Out of the Bottle | 许愿/魔法 + 代价 + 学到教训 |
| 麻烦家伙 | Dude with a Problem | 普通人 + 突发极端困境 |
| 成长仪式 | Rites of Passage | 人生转折 + 痛苦 + 接受 |
| 伙伴情 | Buddy Love | 两人关系 + 缺彼此的一半 + 合一 |
| 推理侦探 | Whydunit | 黑暗秘密 + 侦探 + 揭露的代价 |
| 傻瓜成功 | The Fool Triumphant | 弱者 + 强大体制 + 以弱胜强 |
| 被制度化 | Institutionalized | 群体/组织 + 选择留下或离开 |
| 超级英雄 | Superhero | 特殊能力 + 诅咒/代价 + 宿敌 |

生成规范:
- **只能选上述 10 种之一**，不要自创类型
- 如果故事有混合特征，选最主要的那一个，可在备注说明副类型
- 输出格式: `"genre": "屋里有怪物"` （用中文名）

#### logline — 一句话故事

**核心原则**: "如果你的故事不能用一句话讲清楚并让人感兴趣，那它很可能还没准备好。"

格式公式: `一个[有缺陷的主角]，在[催化事件]后，必须[行动目标]，否则[赌注]。`

规范:
- **必须是一句话**（最多 50 字），不要写成段落
- 必须包含讽刺性（irony）— 概念本身有内在张力
- 必须让人能从这句话想象出整部电影
- 不要写主角全名，用身份特征（如"天才黑客"而非"翟星星"）
- 不要堆砌信息，抓住最核心的一个冲突

坏例子: "被神秘组织派来潜伏科技公司的天才黑客，在见证理想主义CEO的挣扎、爱上女主播的过程中，逐渐怀疑自己执行的剧本——他必须在揭露雇主真面目和保住被精心构造的人生之间做出抉择。"（太长、太多信息）

好例子: "一个被养父训练成间谍的天才黑客，潜伏进目标公司后发现——自己才是那颗被操控的棋子。"

#### theme — 题材类型标签

从以下标准标签中选 1-3 个（第一个为主标签）:

`剧情` `喜剧` `动作` `爱情` `惊悚` `犯罪` `悬疑` `战争` `科幻` `动画` `恐怖` `家庭` `传记` `冒险` `奇幻` `武侠` `历史` `运动` `歌舞` `音乐` `纪录` `伦理` `西部`

生成规范:
- 选 1-3 个，第一个为主标签
- 这是面向观众/市场的分类（视频平台上的频道归类）
- 区别于 genre（genre 是结构引擎，theme 是题材标签）

---

## 抽取规则

1. **Evidence 必填**: 每个抽取元素的 `evidence` 字段必须包含原文中的支撑片段
2. **Confidence 标注**: 
   - `high` = 原文明确提到
   - `medium` = 可以合理推断
   - `low` = 弱线索，需用户确认
3. **Null 优于猜测**: 无法从素材判断的字段设为 null，不要填充通用内容
4. **角色识别阈值**: 至少有名字+一个行为/描述才创建角色条目；纯提及不算
5. **Beat 映射宽容度**: 如果一段情节不能确定对应哪个 beat，设 `beat_number: null` 并在 content 中描述

---

## 从 Schema 到 Wiki 页面的转换

| Schema 字段 | Wiki 页面位置 | 模板 |
|-------------|---------------|------|
| `beats[i]` | `wiki/beats/beat-{XX}-{beat_name}.md` | `_templates/beat-card.md` |
| `characters[i]` | `wiki/characters/{name}.md` | `_templates/character-card.md` |
| `meta.logline` | `wiki/meta/logline.md` | `_templates/logline.md` |
| `meta.genre` + `meta.tone` + `meta.comparable_works` | `wiki/meta/genre.md` | `_templates/genre.md` |
| `meta.theme` | `wiki/meta/theme.md` | `_templates/theme.md` |
| `source` | `wiki/sources/source-{filename}.md` | — |
