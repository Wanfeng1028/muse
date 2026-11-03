# Reimagine Rules — 3 阶段流水线约束

Reimagine 是**创造性再构想**，按 3 阶段流水线生成，每阶段有独立的约束规则。

---

## 流水线 Hard Rules（不可违反）

### HR-1: 阶段依赖性

- Stage 2 必须基于 Stage 1 的 genre 来确定角色原型配置
- Stage 3 必须基于 Stage 1 的 genre 来确定 beat 结构约束
- Stage 3 必须基于 Stage 2 的角色表来分配 characters_involved
- 不允许跳过 Stage 1 直接生成 Stage 2/3

### HR-2: 输出 Schema 兼容性

- 输出 JSON 必须严格遵循 `ingest-schema.md` 的字段定义
- 确保 reimagine 产出可以被同一套下游工具消费
- 不允许自创字段或修改字段类型

### HR-3: 不覆盖原版

- 新版本必须写入 `wiki/versions/reimagine-v{N}-{YYYYMMDD}/` 子目录
- 原版内容完全不修改

---

## Stage 1 Hard Rules

### S1-HR-1: Genre 必须从 10 种中选 1

- 只能选 Save the Cat 10 大类型之一
- 不允许自创类型或写混合类型名称
- 如有混合特征，选主引擎那个，可在 genre.md 备注说明副类型

### S1-HR-2: Logline 必须是一句话

- 最多 50 字
- 必须包含讽刺性（irony）
- 不写主角全名，用身份特征
- 不允许写成段落

### S1-HR-3: Theme 为题材标签

- 从标准标签中选 1-3 个（剧情/喜剧/动作/爱情/惊悚/犯罪/悬疑/科幻 等）
- 第一个为主标签
- 必须与 genre 匹配（如"推理侦探"→ 悬疑/犯罪）

---

## Stage 2 Hard Rules

### S2-HR-1: 类型角色约束

- 必须满足 `references/genre-constraints.md` 中对应 genre 的"必须有"角色要求
- 不满足时必须提醒用户并建议补充

### S2-HR-2: 主角内在张力

- 主角的 Wants ≠ Needs（这是故事成立的基本条件）
- 如果用户方向导致 Wants = Needs，必须指出并建议调整

### S2-HR-3: 角色完整度

- 所有主要角色必须完成 Tab 2 核心字段（wants/needs/shard_of_glass/contradiction/arc_type）
- 原型必须从标准 9 种中选择
- Big Five 5 项全部填写

### S2-HR-4: 级联一致性

- 角色增删改后，人物关系 canvas 必须同步更新
- 如 Stage 3 已存在，受影响的 beats 必须标记并提供更新提案

---

## Stage 3 Hard Rules

### S3-HR-1: 15-Beat 完整填写

- 15 个 beat 全部生成，beat_number 为 1-15
- content/emotion/conflict/value_shift 不允许为空
- characters_involved 必须引用 Stage 2 中存在的角色名

### S3-HR-2: 类型承诺兑现

- 必须满足 `references/genre-constraints.md` 中对应 genre 的 beat 约束
- 特别是 Beat 8（游戏时间）必须兑现类型承诺
- 不满足时必须标记并建议调整

### S3-HR-3: 弧光对比

- Opening Image (Beat 1) 和 Final Image (Beat 15) 必须形成对比
- 对比应证明主角弧光（before vs after）

### S3-HR-4: Genre 引擎贯穿

- genre 的核心引擎在 beats 中至少 3 处兑现
- Beat 2（主题陈述）必须有人说出与故事核心矛盾相关的台词
- Beat 8（游戏时间）必须充分展现类型承诺

---

## Soft Rules（建议遵守）

### SR-1: 催化剂外力性

- Beat 4 建议为外力事件
- 如果创作方向需要主角自发，可以打破但需说明理由

### SR-2: 三幕比例

- 建议 25% / 50% / 25%
- 可适当调整但需有理由

### SR-3: B Story 主题承载

- 建议 B Story 承载或映射 theme
- 用户未指定 B Story 方向时可自由创作

### SR-4: 角色网络平衡

- 建议至少: 1 Hero + 1 Shadow + 1 Ally/Mentor
- 纯单人叙事可例外

---

## 级联更新规则

当 Stage 2 中角色发生增删改时：

### 增加角色

1. 确定原型和功能
2. 添加到人物关系 canvas
3. 识别该角色应参与哪些 beats（基于原型功能）
4. 更新相关 beats 的 characters_involved 和 content
5. 更新故事线 canvas

### 删除角色

1. 识别所有涉及该角色的 beats
2. 确定功能转移方案（转给谁/或调整情节）
3. 移除角色卡和 canvas 节点
4. 重写受影响 beats
5. 校验类型约束是否仍满足

### 修改角色

1. 分析修改项的影响面
2. 原型改变 → canvas 位置/边类型更新
3. wants/needs 改变 → arc 相关 beats 调整
4. relationships 改变 → canvas 边更新
5. 展示 diff 提案，用户确认后执行

---

## 版本编号规则

- 第一次 reimagine: v1
- 基于 v1 继续调整: v2
- 基于原版的另一个方向: 重新 v1（日期区分）
- 格式: `reimagine-v{N}-{YYYYMMDD}`

---

## Evidence 溯源格式

```
改编自原版 beat {X}: {变化说明}
全新创作，回应创作方向: {方向关键词}
保留自原版 beat {X}（用户要求保留）
改编自原版角色 [{原名}]: {变化说明}
全新角色，功能: {功能说明}
保留自原版（用户要求保留）
```
