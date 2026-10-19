---
name: openmontage-seedance-prompting
version: "1.0.0"
description: 介绍 Seedance 2.0 提示词写法，覆盖八要素结构、多镜头模式、口型同步与参数配置，适用于电影感预告、混剪与运动主导片段创作。
metadata:
  license: AGPL-3.0
---

# Seedance 2.0 提示词指南

## 何时选用 Seedance 2.0

Seedance 2.0 由字节跳动 Seed 团队于 2026 年 2 月发布，是 OpenMontage 在配置了付费网关（`FAL_KEY` 走 `seedance_video`，或 HeyGen Video Agent / Avatar Shots）时，用于电影感、预告、先导、燃向混剪及运动主导片段的**首选高端默认模型**。它同时具备以下全部能力：

- 单次生成即带原生同步音频（对白、音效、环境声一体，而非后期对齐）
- 在单条提示内实现多镜头生成
- 导演级镜头控制
- 依据引号内对白实现口型同步
- 参考条件生成，最多支持 9 张图 + 3 段视频 + 3 段音频
- 跨镜头角色身份保持一致

发布时 Artificial Analysis 的 Elo 为 1269，领先 Veo 3、Sora 2、Runway Gen-4.5。

仅在确有理由时才切换其他模型：预算受限（改用 `fast` 变体或 LTX）、用户明确指定（VEO / Sora / Kling），或某模型在特定风格上更合适（VEO 适合写实风景，Kling 适合动漫）。

## 八要素提示结构

Seedance 对镜头语言、多镜头剪辑与引号对白极为忠实。按下列结构组织，按需取用：

1. **景别 / 构图** — 广角定场、中景、特写、荷兰角等
2. **镜头运动** — 固定、缓慢推近、航拍、手持、环绕、滑动变焦
3. **主体描述** — 必须在跨镜头间延续的物理细节（身份锚点）
4. **动作节拍** — 一句一拍，多镜头用 `→` 或显式 `Shot 1 / Shot 2`
5. **场景 / 环境** — 地点、年代、天气、时段
6. **光照 / 色调** — 只用一个光照概念，选定即贯彻
7. **风格 / 调色 / 质感** — 例如"变形镜头、青橙调色、35mm 胶片颗粒"
8. **音频** — 环境声、画内声、音乐方向（仅质感层面）、用于口型同步的引号对白

## Seedance 的专长

| 能力 | 调用方式 |
|---|---|
| **原生同步音频** | 在提示里描写声景，`generate_audio=true` 保持开启 |
| **单次多镜头** | 用 `Shot 1 (...)`、`Shot 2 (...)` 分块，主体描述在各镜头保持一致 |
| **导演级运镜** | 用无歧义术语：`slow dolly-in`、`arc shot`、`Dutch tilt`、`aerial push-in`、`handheld with micro-shake` |
| **引号对白口型同步** | `Character says: "line."`，快剪镜头每句不超过约 6 词 |
| **参考转视频** | 使用 `reference-to-video` 端点，在提示中为每个素材命名（`Reference 1: 主角 — ...`） |
| **角色身份一致** | 每个镜头都重复相同的物理细节，Seedance 以此作为身份锚点 |

## 多镜头写法

> **每个镜头都要逐字重复身份描述。** "the same character"、代词、"Aang again" 都无效。在每个镜头块中原样重复那 3–6 个具区分度的视觉特征。Seedance 会把每个镜头当作你从头描述来处理。

Seedance 会遵循显式镜头列表：

```
Shot 1 (wide aerial establishing, slow push-in):
Snow-covered Air Temple at dawn, spires catching first orange light.
Wind lifting prayer flags.

Shot 2 (medium, low angle, handheld):
Aang — bald, blue arrow tattoo, orange robes — plants his staff on stone.
He squints into the rising sun.

Shot 3 (extreme close-up, rack focus):
Rack focus from the glowing arrow tattoo on his forehead to the distant peaks.
Aang says: "It's time."

Style: anamorphic lens, teal-orange cinematic grade, 35mm film grain.
Audio: rising orchestral swell with low taiko pulse, wind, distant wingbeats.
```

### 多镜头中的主体转换原语

Seedance 支持主体进出镜头的四种不同方式，显式命名原语有助于模型构建正确的镜头间过渡。

- **主体揭示**（靠运镜或主体移动）—— 主体在镜头中途显现。
  示例：`Shot 2 (slow truck right): empty corridor at first; the camera trucks right to reveal Aang — bald, blue arrow tattoo, orange robes — pressed flat against the wall.`

- **主体消失** —— 主体因运动或被遮挡而离开画面。
  示例：`Shot 4 (static wide): Aang — bald, blue arrow tattoo, orange robes — sprints into the temple doorway and is swallowed by shadow; camera holds on the empty threshold.`

- **主体切换**（移焦或运镜）—— 焦点或构图从一个主体转移到另一个。
  示例：`Shot 5 (close-up, rack focus): rack focus from Aang's glowing arrow tattoo in foreground to Sokka — dark hair, blue tunic, boomerang on back — emerging from the mist behind.`

- **复杂交替对焦** —— 单个镜头内焦点在两个主体间往复。
  示例：`Shot 7 (medium two-shot, alternating rack focus): focus on Aang — bald, blue arrow tattoo, orange robes — as he speaks, then pulls to Katara — long brown hair, blue water-tribe parka — as she answers, then back to Aang on the final beat.`

## 口型同步写法

```
Aang says: "I won't run anymore."
Sokka, half a step behind, replies: "Then we fight."
```

- 严格使用 `Character says: "..."` / `Character replies: "..."`，口型依引号内字符串驱动。
- 快剪镜头对白保持简短（不超过 6 词），避免口型漂移。
- 单人独白时，镜头保持贴近且固定于说话者。

## 参数速查

| 参数 | 建议 |
|---|---|
| `duration` | 主角镜头 `5`–`8` 秒，多镜头场景 `10`–`12` 秒，插入镜头 `4` 秒。不确定时用 `auto`。 |
| `aspect_ratio` | 预告片 `21:9`，广播 `16:9`，Reels / Shorts / TikTok `9:16` |
| `resolution` | 默认 `720p`，仅成本受限预览用 `480p`。 |
| `generate_audio` | 保持 `true` —— 同步音频是核心优势。合成阶段若不用再剥离。 |
| `model_variant` | 主角镜头、多镜头、重运镜用 `standard`；B-roll、预览、延迟受限任务用 `fast`。 |
| `seed` | 一旦构图稳定即锁定，用同一 seed 迭代变体。 |
| `prompt length` | 主角镜头 200–400 词，插入镜头 80–150 词。Seedance 是少数偏好长结构化五要素提示的模型之一。 |

## 迭代策略

1. **打样形状** —— `duration=5`、`fast`、单镜头，确认构图。
2. **锁定 seed** —— 记入单条片段的 README。
3. **升级到 `standard`** —— 同 seed，收紧运镜与光照语言。
4. **扩展或多镜头** —— 仅在单镜头版本干净后再做。
5. **提升为终版** —— 把提示、seed、变体、时长写入资产清单，便于合成阶段重渲一致的补拍。

## 需要避免

| 禁止 | 原因 |
|---|---|
| 单镜头四个以上同时动作 | 运动连贯性崩塌，应拆为多镜头 |
| 画面内可读文字 / 标志 | 文字渲染不可靠，用 Remotion 叠加处理 |
| 矛盾光照（`bright noon` 配 `neon night`） | 模型只会取其一 |
| 快剪镜头上的长对白 | 口型漂移 |
| 慢动作、多镜头或复杂运镜用 `fast` 变体 | 首轮经常失败，改用 `standard` |
| 让 Seedance 生成完整多乐器配乐 | 音频只做质感描述；真正的配乐交给 `music` / `pixabay_music` / `elevenlabs`，合成阶段混音 |
| 无理由绕过 `video_selector` | 会丢失评分、回退与成本处理 |

## 集成说明

- **电影感流程：** Seedance 2.0 为默认。21:9，混剪用多镜头，有视觉圣经的 brief 用 reference-to-video。
- **动画讲解：** 仅用 Seedance 2.0 做定场 / 氛围 / 冷开场，核心动效留在 Remotion。
- **屏幕演示 / 播客 / 片段工厂：** 不是默认选项，仅用于风格化冷开场。
- **成本核对：** fal.ai 上 `standard` 10 秒约 $3.03 / 条，`fast` 5 秒约 $1.21。在提案阶段预算。

## 示例 —— 气宗预告主角节拍（60 秒预告中的第 3 镜，共 7 镜）

```
Shot 1 (wide aerial, slow push-in, 3s):
Snow-covered Air Temple at dawn, spires catching orange light,
prayer flags lifting in wind.

Shot 2 (low angle medium, handheld, 3s):
Aang — bald, blue arrow tattoo on forehead, orange and yellow robes —
plants his staff on weathered stone, squints into the rising sun.

Shot 3 (extreme close-up, rack focus, 3s):
Rack focus from the glowing arrow on his forehead to distant peaks.
Aang says: "It's time."

Lighting: cold blue ambient with warm break on the horizon,
rim light from rising sun.
Style: anamorphic 2.39:1, teal-orange cinematic grade, 35mm film grain,
halation on speculars.
Audio: low taiko drums rising to orchestral swell on Shot 3,
wind through temple, distant wingbeats, leather staff-grip creak.
```

参数：`duration=10`、`aspect_ratio=21:9`、`resolution=720p`、`model_variant=standard`、`generate_audio=true`，第 2 镜后锁定 seed。
