---
name: openmontage-documentary-montage-edit-director
version: "1.0.0"
description: 把已选片段编排成纪录片蒙太奇的剪辑决策产物，确定入出点、转场、配乐同步与片段顺序，适用于素材齐备后的时间线构建阶段。
metadata:
  license: AGPL-3.0
---

# 剪辑总监 · 纪录片蒙太奇流水线

## 适用时机

每个槽位都有片段了。现在要把一堆片段变成一部作品。本阶段决定入点、出点、转场、配乐同步，以及片段实际的播放顺序。产出是一份带具体时间线的 `edit_decisions` 产物。

纪录片技法就活在这里。素材总监把活干好，你就有原始材料。剪辑才是思考。

## 前置依赖

| 层 | 资源 | 用途 |
|----|------|------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | 产物校验 |
| 前置产物 | `state.artifacts["assets"]["asset_manifest"]` | 已选片段 + 配乐床 |
| 前置产物 | `state.artifacts["scene_plan"]["scene_plan"]` | 槽位顺序、hero 标记、目标保持时长 |
| 前置产物 | `state.artifacts["idea"]["brief"]` | 调性、时长、结构 |
| 工具（可选） | `video_analyzer` | 需要复核某片段运动时使用 |

## 心智模型

纪录片蒙太奇活在四个需要平衡的维度上：

1. **节奏**——每个镜头保持多久，以及这些保持如何互相呼应。
2. **并置**——哪个画面接哪个画面，意味着什么。
3. **配乐同步**——切点落在节拍上，留白挣得重量。
4. **调性连续性**——颗粒、色彩与年代不剧烈跳变，除非跳变本身就是意图。

敌人是"幻灯片"——一串保持时长相同、没有声音设计的背靠背片段。如果看起来像幻灯片，剪辑就失败了，无论片段本身多好。

本阶段同时锁定渲染语法。纪录片蒙太奇要把 `renderer_family` 设为 `documentary-montage`，让合成阶段留在已批准的 Remotion 优先路径上。

## 流程

### 0. 护栏——不许静默重大变更

动时间线之前重读 brief。以下任一为真，立刻停下并上报用户（按决策沟通契约）：

- brief 批准了"无旁白"，但剪辑感觉需要画外音。旁白是重大变更。
- brief 批准了一条配乐，剪辑总监现在想换掉。换音乐是重大变更。
- brief 批准 90 秒时长，但自然剪出来的成片想要 2 分 30 秒。拉长时长是重大变更。

修正剪辑，不要粉饰。如果剪辑确实需要其中之一，去问。

### 1. 设定节奏网格

读 `brief.tone` 与 `brief.duration_seconds`，按分镜导演的调性表计算保持时长：

| 调性 | 基础保持 | 最短保持 | 最长保持 |
|------|----------|----------|----------|
| elegiac | 4.0s | 2.5s | 7.0s |
| reverent | 3.5s | 2.0s | 6.0s |
| dreamlike | 3.0s | 1.5s | 5.5s |
| wry | 2.0s | 1.0s | 4.0s |
| urgent | 1.2s | 0.5s | 2.5s |

**hero 槽位给最长保持。** 段落中部的插入镜头用基础值。快速过渡用最短值。

总保持时长之和必须落在 `brief.duration_seconds` 的 ±10% 以内。超出就先压缩非 hero 的保持——绝不要为凑时长把 hero 剪短。

### 2. 按叙事节拍排布，不按分数

分镜导演给的槽位顺序就是意图。不要按 CLIP 分数、运动分数或分辨率重排。

以下情况**可以**重排：

- 配乐床在已知时间戳有重拍，重排两个槽位能让一个 hero 落在拍上（见第 4 步）。
- 相邻两个槽位视觉上完全一致，换掉一个打破单调（但见第 7 步——diversify 本应已经处理）。
- 收尾画面立不住。最后 5-10 秒承载着不成比例的重量；若分镜导演的选择失效，把一个更强的候选移到尾部。

任何重排都要在 `edit_decisions.metadata.reorder_notes` 里记录原因。

### 3. 把每条片段剪到它的节拍

为每条被选片段确定 `in_seconds` 与 `out_seconds`。三条规则：

- **找最佳子窗口，不是整条片段。** 一条 12 秒的 Pexels 片段里通常只有一个 3 秒的瞬间配得上那个保持，其余 9 秒是铺垫与收束。找到那个瞬间。
- **在动作自然结束之前切。** 切在一个眼神上，不是切在转身离开上。切点会显得是有意为之，而不是力竭。
- **两端各留余量。** 前后各留 4-6 帧，让合成阶段能施加淡入淡出或叠化而不切掉那个瞬间。

片段太短填不满目标保持时，三选一：

- 放慢（速度 0.5-0.75，静态类画面尚可，任何有同步运动或人物说话的画面都不行），
- 让它提前切走，把剩余时长借给下一槽位的保持，
- 或换到 rejected-picks 日志中的第二顺位候选。

**不要停在最后一帧的冻结画面上。** 纪录片蒙太奇里的定格会被读成技术失误。

### 4. 与配乐床同步

从 `asset_manifest` 读音乐 asset 并载入其时长。纪录片蒙太奇的情绪重量来自切点落在音乐事件上。三个同步动作：

- **重拍切点。** 若有小节与节拍元数据（来自用户提供的音轨）或能听出来，把 hero 切点放在重拍上。若没有，对 60bpm 的配乐床按 4 秒间隔均匀切点是安全的默认做法。
- **一次留白。** 在作品的情绪中心让音乐退出约 2 秒。静默是工具。用一次。用得狠。
- **尾部淡出。** 最后 3-5 秒音乐淡出，让收尾画面能呼吸，不被音乐解决音顶着。

在 `edit_decisions.audio.music` 中记录音乐配置：

```json
{
  "asset_id": "asset_music_bed",
  "volume": 0.7,
  "fade_in_seconds": 1.0,
  "fade_out_seconds": 4.0,
  "ducking": false
}
```
上例设定配乐床的音量、淡入淡出时长与是否闪避。

`ducking: false` 是本流水线的默认值——没有旁白需要闪避。若用户批准了旁白轨，把 ducking 设为 true，让音乐在旁白段落下压。

### 5. 从一个小词表里选转场

纪录片蒙太奇全片大概只用四种转场：

| 转场 | 用途 |
|------|------|
| `cut`（硬切） | 默认。多数切点都是硬切。 |
| `dissolve`（0.5-1.0s） | 情绪上互为兄弟的片段、时间流逝 |
| `fade_to_black`（0.5s，再回） | 三幕结构中的幕间，或临近结尾用一次 |
| `fade_in`（首镜）/ `fade_out`（末镜） | 0.5-1.0s 首尾包裹 |

**不要使用：**

- 划像，
- 推/滑转场，
- 变焦模糊，
- RGB 分离，
- 漏光，
- 故障特效。

这些会被读成社交媒体剪辑语言，破坏纪录片调性。如果作品开始无聊，改片段选择或节奏，不要加转场花活。

按 schema 记录每个切点的 `transition_in` / `transition_out`。多数切点默认 `transition_in: "cut"`。

### 6. 施加调性连续性

年代混杂的语料库看起来天差地别。Pexels 2023 干净、锐利、已调色。Prelinger 1962 颗粒感强、偏暖、方形画幅。NASA 档案常是低分辨率还带文字叠加。直接混在一起，作品看起来像维基百科词条。

有两件工具可以平滑：

1. **裁到统一画幅。** 选一个：电影感 16:9（上下加 `2.35:1` 黑边）用于主打作品，社交平台用 9:16。在每个切点的 `transform.crop` 字段里强制执行。
2. **标记作品在合成阶段统一调色。** 在 `edit_decisions.metadata` 里放 `grade_profile` 提示。合成总监会对整条时间线施加 LUT。

不要在这里逐条调色。那是合成阶段的事。你的工作是标记需求。

### 7. 最后再强制一遍相邻多样性

按对遍历时间线。对每对相邻的 (cut_n, cut_n+1)：

- 是同一主体同一景别吗？是的话就出现了幻灯片时刻。把其中一个换成不同景别的片段（远景换近景）。
- 是同一色调吗（两个夜蓝色片段挨着）？是的话至少每 4 个切点打破一次。
- 是同一运动方向吗（两个从左到右的摇镜）？是的话翻转第二个的水平轴或重排。

把任何替换记入 `metadata.diversity_swaps`。

### 8. L-cut 手法（可选但强力）

对于两个片段之间的转场，若出场片段有强环境音（雨声、脚步、车流），把该音频延续到入场片段之下 0.5-1.5 秒。这就是 L-cut，它比任何视觉转场都能更紧密地焊接两个镜头。

在 schema 里实现的方式是使用一个短 `dissolve` 转场，或把出场片段的音频作为 SFX 条目层叠进 `edit_decisions.audio.sfx` 并延迟其结束。

带 L-cut 的纪录片蒙太奇比不带的连贯感高约 50%。在全片最难的三到四个转场上使用。

### 8b. 放置片尾卡叠加

若 `brief.metadata.end_tag_plan.mode == "overlay"`（默认），片尾卡会在合成阶段叠到主体素材的末尾画面上。剪辑总监的工作是决定它**何时**出现。

计算偏移：`offset_seconds = body_duration - tag_duration`。这样片尾卡的淡出就与主体的收尾淡出对齐（最后一个切点的 `transition_out: fade_out`）。若最后一个切点的保持短于片尾卡时长，就把片尾卡提前，让它同时覆盖倒数第二个切点——这没问题，而且往往更好看。

在 `edit_decisions.end_tag` 中记录：

```json
{
  "end_tag": {
    "offset_seconds": 84.5,
    "notes": "Tag starts at body_duration - tag_duration. Aligns tag fade-out with final cut fade-out."
  }
}
```
上例给出片尾卡起始偏移与说明，使片尾卡淡出与末切点淡出对齐。

若 `mode == "concat"`，省略此节——合成总监会在主体之后追加片尾卡，不需要时间偏移。

### 9. 输出剪辑决策

本流水线的规范形态：

```json
{
  "version": "1.0",
  "renderer_family": "documentary-montage",
  "cuts": [
    {
      "id": "cut_01",
      "source": "asset_slot_01",
      "in_seconds": 1.2,
      "out_seconds": 5.2,
      "layer": "primary",
      "transform": { "scale": 1.0, "position": "center" },
      "transition_in": "fade_in",
      "transition_out": "cut",
      "transition_duration": 0.8,
      "reason": "opening hero — raindrop on asphalt, 4s hold, slow-motion streetlamp glow"
    },
    {
      "id": "cut_02",
      "source": "asset_slot_02",
      "in_seconds": 2.0,
      "out_seconds": 5.5,
      "layer": "primary",
      "transition_in": "cut",
      "transition_out": "cut",
      "reason": "umbrella opening in doorway, hard cut from raindrop → street"
    }
  ],
  "audio": {
    "music": {
      "asset_id": "asset_music_bed",
      "volume": 0.7,
      "fade_in_seconds": 1.0,
      "fade_out_seconds": 4.0,
      "ducking": false
    }
  },
  "end_tag": {
    "offset_seconds": 84.5,
    "notes": "Tag starts at body_duration - tag_duration. Aligns tag fade-out with final cut fade-out."
  },
  "metadata": {
    "pipeline": "documentary-montage",
    "tone": "elegiac",
    "shape": "list",
    "total_duration_seconds": 90.0,
    "hold_table_used": { "base": 4.0, "min": 2.5, "max": 7.0 },
    "grade_profile": "warm_film_100",
    "reorder_notes": [],
    "diversity_swaps": [
      { "at": "cut_07-cut_08", "reason": "two wide rooftops-in-rain adjacent, swapped 08 for #2 pick" }
    ],
    "silence_window": { "start_seconds": 54.0, "end_seconds": 56.0 },
    "l_cuts": [
      { "from_cut": "cut_05", "to_cut": "cut_06", "carry_seconds": 1.2, "channel": "ambient_rain" }
    ]
  }
}
```
上例给出完整剪辑决策：每个切点的源、入出点、层、变换、转场与理由，外加音乐配置、片尾卡偏移，以及调性、结构、保持表、调色档位、重排备注、多样性替换、静音窗与 L-cut 记录。

### 10. 质量门

- `sum(out - in for cut in cuts)` 落在 `brief.duration_seconds` 的 ±10% 内。
- `renderer_family = "documentary-montage"` 存在且未被改动。
- hero 槽位拥有最长的保持。
- 没有两个相邻切点共享主体与景别。
- 转场词表最多 4 个不同值。
- 音乐配置存在（或 brief 明确说了无音乐）。
- 60 秒以上的作品至少有一条 `silence_window`。
- 每个切点都有一行 `reason`——写不出来说明这个切点是随意的，应该重新考虑。
- `metadata.total_duration_seconds` 与切点时长之和对得上。

## 常见坑

- **按信息密度而非节奏剪辑。** 纪录片蒙太奇不是维基百科词条。"但我需要展示这个"不是理由——如果画面撑不住一个保持，它就不该出现。
- **过度使用叠化。** 每个切点都叠化等于说"我不敢决断"。决断。
- **直到最后才考虑配乐床。** 音乐不是合成阶段才加的调味品，是你剪进去的时间网格。
- **让收尾画面是弱画面。** 最后一帧被记住的比例不成比例。它弱就换掉——分镜导演的槽位顺序是强烈建议，不是契约。
- **定格收尾。** 会被读成技术失误。用淡出黑场收尾。
- **因为剪辑单薄就悄悄加旁白。** 重大变更。去问。
- **在切点里隐藏片段提供方。** 每个 `cut.source` 必须是 `asset_manifest` 的 asset_id，溯源才能存活。
- **前 15 秒用了三种不同转场。** 观众会感觉到剪辑在使劲。克制才是风格。

## 节奏设计范例——"雨中的一分钟"

90 秒，elegiac，清单结构，15 个 hero 标记槽位。

- 基础保持 4.0s × 15 = 60s，还差 30s。
- 在 3 个 hero 槽位（1、11、15）各加 10s：hero_1 = 5.5s，hero_11 = 6.0s，hero_15 = 7.0s。
- 把 4、7、13 三个槽位收紧到各 3.0s（小型插入镜头）。
- 在 54.0-56.0s 插入 `silence_window`（正好在 hero_11 之前）。
- 对 slot_10（水坑里的靴子）→ slot_11（街对面亮灯的窗）做 L-cut，延续雨打玻璃环境声 1.2s。
- 首切 `fade_in` 1.0s，末切 `fade_out` 1.5s。
- 其余切点全部硬切。
- 音乐 1.0s 淡入，在 hero_15 + 黑场之下 4.0s 淡出。

由此得到 90 秒作品，含 3 个呼吸点（淡入、静默、淡出），一条清晰的 hero 弧线（槽位 1 → 11 → 15），且无相邻景别冲突。

---

## 门禁提醒（强制）

本阶段以人工批准为门（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 面板会渲染产物），然后**结束本轮**。不要在同一响应里启动下一阶段。批准按门生效——先前的"继续"不覆盖本门。
