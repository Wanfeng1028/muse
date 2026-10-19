---
name: openmontage-explainer-edit-director
version: "1.0.0"
description: 解说视频剪辑导演技能，把资产清单、场景计划与脚本装配成完整剪辑决策清单，定义画面时序、图层关系、字幕配置与音画互动，适用于生成式视频流水线的剪辑时间线设计阶段。
metadata:
  license: AGPL-3.0
---

# 剪辑导演 — 解说流水线

## 适用时机

你负责生成式解说视频的剪辑。手上有含全部生成文件的 `asset_manifest`、含视觉结构的 `scene_plan`、含时序的 `script`。任务是把剪辑决策清单（EDL）装配出来：什么何时播放、元素如何叠层、字幕放哪、音乐与旁白如何互动。

这是原始素材变成连贯视频的地方。好的剪辑让平庸素材发光，坏的剪辑浪费出色素材。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | 产物校验 |
| 上游产物 | `state.artifacts["assets"]["asset_manifest"]`、`state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]` | 素材、视觉计划、时序 |
| Playbook | 当前生效的风格 playbook | 转场、节奏规则、叠层样式 |

## 流程

### 第 1 步：把素材映射到时间线

对场景计划里每个场景：

1. 按 `scene_id` 从资产清单找到匹配素材
2. 按脚本小节找到匹配的旁白音频
3. 记录场景时序（`start_seconds`、`end_seconds`）

建立时间线映射：

```
0s-10s: scene-1 (talking_head) | narration-s1 | img-intro.png
10s-18s: scene-2 (diagram) | narration-s2 | diagram-flow.svg
18s-22s: scene-3 (text_card) | narration-s3 | [text overlay]
...
```

### 第 2 步：定义剪辑点

每个 cut 定义何时显示什么画面：

```json
{
  "id": "cut-1",
  "source": "img-scene-1",
  "in_seconds": 0,
  "out_seconds": 10,
  "layer": "primary",
  "transform": {
    "scale": 1.0,
    "position": "center",
    "animation": "ken-burns-slow-zoom"
  },
  "transition_in": "fade",
  "transition_out": "dissolve",
  "transition_duration": 0.4
}
```

**叠层规则：**

- `primary` —— 主画面（同一时刻只一个）
- `overlay` —— 文字卡、数据卡、关键术语（叠在主画面之上）
- `background` —— 所有东西之后的纯色或纹理

### 第 3 步：配置字幕

所有解说内容都必须有字幕：

```json
{
  "subtitles": {
    "enabled": true,
    "style": "word-by-word",
    "font": "Inter",
    "font_size": 48,
    "color": "#FFFFFF",
    "background": "#00000088",
    "position": "bottom-center",
    "max_words_per_line": 8
  }
}
```

**字幕时序**：从旁白音频时间戳推导。逐词样式时每个词随念出而高亮，短语样式时按短语块显示。

字体选择用 playbook 的排版规范。

### 第 4 步：配置音频层

```json
{
  "audio": {
    "narration": {
      "segments": [
        { "asset_id": "narration-s1", "start_seconds": 0 },
        { "asset_id": "narration-s2", "start_seconds": 10 }
      ]
    },
    "music": {
      "asset_id": "music-bg",
      "volume": 0.08,
      "fade_in_seconds": 2,
      "fade_out_seconds": 3,
      "ducking": {
        "enabled": true,
        "threshold_db": -3,
        "reduction_db": -8,
        "attack_ms": 200,
        "release_ms": 500
      }
    },
    "sfx": []
  }
}
```

**音乐闪避**：旁白播放时音乐音量下沉，停顿处回升。用 playbook 的 `audio.ducking_threshold_db`。

### 第 5 步：应用节奏规则

检查 playbook 的 `motion.pacing_rules`：

- 无剪辑短于 `min_scene_hold_seconds`
- 无剪辑长于 `max_scene_hold_seconds`
- 文字卡停留 `text_card_hold_seconds`
- 转场用 `transition_duration_seconds`

有任何违规就调整剪辑时序。

### 第 6 步：核对剪辑完整性

**时间线覆盖：**

- [ ] 剪辑铺满全片时长（无黑帧）
- [ ] 无重叠的 primary 剪辑
- [ ] scene_plan 里每个场景都至少有一个对应剪辑

**素材引用：**

- [ ] 每个 cut 的 `source` 引用清单里的合法 asset_id
- [ ] 每个旁白段引用合法音频资产
- [ ] 音乐资产存在

**音画同步：**

- [ ] 旁白段有序且不重叠
- [ ] 旁白时序与对应画面剪辑对齐
- [ ] 音乐闪避已配置

**字幕：**

- [ ] 字幕已启用
- [ ] 字幕样式使用 playbook 兼容的字体与颜色

### 第 7 步：自评

打分（1-5）：

| 维度 | 问题 |
|-----------|----------|
| **连贯性** | 视频每一秒都有画面吗？ |
| **节奏** | 剪辑遵循 playbook 的时序规则吗？ |
| **音画同步** | 每个时刻所见与所闻匹配吗？ |
| **字幕质量** | 字幕可读且时序正确吗？ |
| **转场连贯性** | 转场在 playbook 允许集内吗？ |

任一项低于 3 分，修订。

### 第 8 步：提交

对 edit_decisions 产物做 schema 校验，并通过 checkpoint 持久化。

## 常见坑

- **忘了空隙**：scene-1 在 10s 结束而 scene-2 从 10.5s 开始，就有 0.5s 黑帧。检查空隙。
- **音频漂移**：旁白音频可能比计划略长/略短。按实际旁白时长调整画面剪辑，不要按计划时长。
- **无闪避**：旁白下音乐全音量播放会让视频没法看。永远配置闪避。
- **千篇一律的转场**：转场有变化才有节奏。用 playbook 允许集，但别每个剪辑都用同一个。
- **字幕字体不匹配**：字幕该用 playbook 的正文字体，不是随便的默认字体。
