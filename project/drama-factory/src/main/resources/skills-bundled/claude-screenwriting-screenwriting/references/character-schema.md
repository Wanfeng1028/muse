# 角色卡数据模型（Character Schema）

角色卡分为 3 个层次（Tab），基于 Vogler/McKee/Save the Cat 综合设计。

---

## Tab 1: 人物塑像（Character Image）— 外在可见

你能"看见"和"听见"的一切。

| 字段 | 类型 | 枚举值/说明 |
|------|------|------------|
| `gender` | 选择 | 男 / 女 / 其他 / 未指定 |
| `age_group` | 选择 | 儿童 / 青少年 / 青年 / 中年 / 老年 |
| `height` | 选择 | 矮 / 中等 / 高 |
| `build` | 选择 | 瘦削 / 匀称 / 健壮 / 肥胖 |
| `physical_tags` | 标签列表 | 自由标签，如：疤痕、纹身、眼镜、跛脚 |
| `voice_pitch` | 选择 | 低沉 / 中等 / 高亢 |
| `speech_speed` | 选择 | 缓慢 / 正常 / 急促 |
| `voice_volume` | 选择 | 轻声 / 正常 / 洪亮 |
| `behavior_tags` | 标签列表 | 如：习惯性搓手、说话不看人、走路很快 |
| `social_identity` | 标签列表 | 如：律师、单亲妈妈、退伍军人、学生 |

**理论依据**: 外在是"面具"（McKee 的 Surface），是观众第一印象；通过后续揭示与内在的反差创造维度。

---

## Tab 2: 人物真相（Character Truth）— 内在驱动

Save the Cat "四大支柱" + McKee "矛盾/压力" 的融合。

| 字段 | 类型 | 理论来源 | 说明 |
|------|------|----------|------|
| `wants` | 文本 | Save the Cat 四大支柱 | 有意识的外在目标 |
| `needs` | 文本 | Save the Cat + McKee | 无意识的内在需求（常与 Wants 冲突） |
| `motivation` | 文本 | 桥接层 | 连接 Wants/Needs 和碎玻璃的行为驱动力 |
| `shard_of_glass` | 文本 | Save the Cat | 过去创伤，解释"为什么这个人是这样" |
| `opinions` | 文本 | Save the Cat 四大支柱 | 角色对世界的看法（世界观） |
| `attitudes` | 文本 | Save the Cat 四大支柱 | 面对困难时的默认姿态 |
| `contradiction` | 结构 | McKee | `{surface: "...", truth: "..."}` |
| `pressure_choice` | 结构 | McKee | 7 维度中标记该角色的核心 2-3 个及倾向 |
| `arc_type` | 选择 | 综合 | positive / negative / flat / circular |
| `changes` | 文本 | Save the Cat 四大支柱 | 故事结束时角色发生了什么可观察变化 |
| `character_arc` | 文本 | 综合 | 一段话描述完整弧光轨迹 |

---

## Tab 3: 人物维度（Character Dimensions）— 结构性指标

| 字段 | 类型 | 说明 |
|------|------|------|
| `big_five` | 结构 | `{openness: 1-5, conscientiousness: 1-5, extraversion: 1-5, agreeableness: 1-5, neuroticism: 1-5}` |
| `virtues` | 标签列表 | 核心美德（如：勇气、诚实、同理心） |
| `six_flaws` | 标签列表 | Save the Cat "Six Things That Need Fixing" |
| `backstory` | 文本 | 人物小传（碎玻璃事件 + 关键经历） |
| `relationships` | 文本 | 与其他角色的关系网络描述 |

---

## 头部字段（Header）

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | 文本 | 角色名 |
| `archetype` | 选择 | hero / mentor / ally / shadow / shapeshifter / guardian / herald / trickster / other |
| `description` | 文本 | 基于原型的一句话角色定位 |

---

## Frontmatter 映射（Obsidian 模板）

在 `_templates/character-card.md` 中，以上字段映射为 YAML frontmatter + Markdown 正文混合：

- Frontmatter: `type`, `name`, `archetype`, `arc_type`, `created`
- 正文按三个 `##` 区块组织
- 结构化字段（contradiction, pressure_choice, big_five）用缩进列表表达

---

## 完整性检查规则（供 /lint 使用）

| 检查项 | 严重度 | 说明 |
|--------|--------|------|
| 无 `wants` | Error | 角色没有目标=无法推动情节 |
| 无 `needs` | Error | 角色没有内在需求=无弧光 |
| `wants` == `needs` | Warning | 无张力 |
| 无 `shard_of_glass` | Warning | 行为动机缺乏深度 |
| 无 `contradiction` | Warning | 角色可能是 1D |
| 无 `arc_type` | Info | 可后续补充 |
| `archetype` == 'hero' 但无 `six_flaws` | Warning | 英雄缺乏 Setup 所需缺陷 |
