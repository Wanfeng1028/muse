# 重构约束规则（Refactor Rules）

重构操作必须遵守以下规则。违反任何一条 Hard Rule 的重构提案应被拒绝。

---

## Hard Rules（不可违反）

### HR-1: 15-Beat 框架完整性

- 重构后 15 个 beat 必须全部存在
- 可以改变任何 beat 的具体内容
- 不可以删除/跳过/合并 beat（即使内容为空也要保留位置）
- 理由: 15-beat 是经过验证的叙事节奏，删除会破坏观众期待

### HR-2: Wants/Needs 张力

- 主角的 Wants 和 Needs 在重构后仍必须冲突
- 如果重构改变了 Wants，必须同时检查 Needs 是否仍构成张力
- 理由: Wants=Needs 意味着没有内在冲突 → 没有角色弧

### HR-3: Catalyst 外力性

- Beat 4（催化剂）在重构后仍必须是外力事件
- "外力"定义: 非主角主动寻求的、打破现状的、不可忽视的
- 理由: 如果主角自己决定改变，故事缺乏"不得不"的紧迫感

### HR-4: 弧光一致性

- 重构不可无理由地逆转角色弧光方向
  - positive arc → 不能突然变 negative（除非明确是类型转换且用户确认）
- 如果 arc_type 需要改变，必须同时更新 changes、character_arc 字段
- 理由: 弧光方向决定了整个故事的情感走向

### HR-5: Backlink 完整性

- 重构后不可产生新的断链（`[[引用不存在的页面]]`）
- 如果重构删除了某角色/beat 的关键内容，相关 backlink 需更新
- 新内容的 source 标注为 `refactor-{date}` 而非原素材

---

## Soft Rules（建议遵守，可例外）

### SR-1: 三幕比例

- 建议保持 25% / 50% / 25% 的三幕比例
- 如果重构大幅改变某幕的密度，给出提醒

### SR-2: Midpoint 转折力度

- 中点应该改变"游戏规则"（虚假胜利/虚假失败）
- 重构中点内容时检查是否保持了转折力度

### SR-3: B Story 主题承载

- B Story 应与主线主题形成呼应
- 如果重构改变了主题方向，检查 B Story 是否需要同步调整

### SR-4: 角色网络平衡

- 重构不应让大量角色变成孤儿（失去所有 beat 关联）
- 如果某角色在重构后不再出现在任何 beat 中，提醒用户

### SR-5: 类型契约

- 每种类型有观众期待的特定 beat 表现
  - 惊悚: Catalyst 是发现秘密, Midpoint 是发现更大秘密
  - 爱情: B Story 就是 A Story, Midpoint 是假性亲密
  - 动作: Fun and Games 是类型动作场面的集中展示
- 重构应检查是否满足目标类型的契约

---

## 重构记录格式

每次重构在 `wiki/log.md` 中记录：

```markdown
## [YYYY-MM-DD HH:mm] Refactor

- **方向**: {用户指令}
- **影响范围**: {X beats + Y characters + Z meta}
- **变更摘要**: 
  - beats: {列出变更的 beat 编号和变更类型}
  - characters: {列出变更的角色名和变更维度}
  - meta: {logline/genre 是否变更}
- **理论依据**: {一句话解释为什么这样改}
- **Hard Rule 检查**: ✅ 全部通过
```

---

## 回滚

- 重构操作依赖 Obsidian Git 插件的自动 commit
- 每次重构前建议用户确认 git 状态干净
- 如需回滚，提示用户使用 `git revert` 到上一个 commit
