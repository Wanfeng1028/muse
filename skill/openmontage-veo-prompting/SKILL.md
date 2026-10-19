---
name: openmontage-veo-prompting
version: "1.0.0"
description: 介绍 VEO 3.1 / VEO 3 提示词写法，覆盖十四要素结构、镜头运动分类与光学效果，适用于需要原生对白与精确运镜的写实或艺术风格短片。
metadata:
  license: AGPL-3.0
---

# VEO 3.1 / VEO 3 提示词指南

**词数：** VEO 3.1 的甜区在 100–250 词，再长收益递减。

## VEO 专用十四要素结构

VEO 响应的提示结构是所有模型中最全面的：

1. **主体** — 动作围绕的人或物
2. **动作** — 运动、交互、表情
3. **场景 / 语境** — 地点、时间、天气、年代
4. **机位角度** — 景别与视角
5. **镜头运动** — 动态位移
6. **镜头 / 光学效果** — 相机"看"的方式
7. **光照** — 光源、方向、质感
8. **基调 / 情绪** — 情感调性
9. **艺术风格** — 写实、电影感、动画、艺术流派
10. **氛围** — 色彩、气效、质感
11. **时间要素** — 节奏、时间流、韵律
12. **音频** — 音效、环境声、对白（VEO 3 可生成对白）
13. **电影术语** — 剪辑手法（match cut、montage、split diopter）
14. **负向提示** — 需要排除的内容

## VEO 的专长

- **对白生成**：VEO 3 原生生成角色台词，按自然语言书写即可。
- **音频整合**：环境声、音乐与语音随视频一并生成。
- **负向提示**：显式支持，如 "no text overlays, no watermarks, no lens flare"。
- **剪辑词汇**：能理解 "match cut"、"jump cut"、"montage"、"split diopter" 作为提示词。

### VEO 会字面遵循的运镜词汇

VEO 3.1 区分三个运镜族，并把各自的 token 当作独立原语。混淆它们（例如想要 dolly 却写了 zoom）会得到错误的运动。

- **位移（机架物理移动）：** `dolly`（沿光轴进出）、`truck`（左右横移）、`pedestal`（上下升降）
- **旋转（机架不动，机身转动）：** `pan`（偏航，左右）、`tilt`（俯仰，上下）、`roll`（荷兰角 / Z 轴）
- **纯镜头（机架与机身都不动）：** `zoom`（焦段变化）、`rack focus` / `pull focus` / `focus tracking`（焦平面变化）

dolly ≠ zoom，pan ≠ truck。VEO 只按领头 token 执行。

## VEO 的镜头效果（独有）

VEO 尤其响应多数模型忽略的光学效果：

| 效果 | 提示语言 |
|--------|----------------|
| **Rack focus** | "snap focus from the blossom up front to the person behind"（瞬间切换） |
| **Pull focus** | "slow focus drift from the lamp in front to the hallway behind"（渐变，比 rack 慢） |
| **Focus tracking** | "keep the cyclist sharp as he rides past, background melting away"（焦点追随移动主体） |
| **Dolly zoom（眩晕）** | "background stretches away while the heroine stands frozen in shock" |
| **Fisheye** | "bulging fisheye warp, shot from a low board-level angle" |
| **Anamorphic lens flare** | "long horizontal light streaks blooming off the low sun" |

这三种对焦模式（rack、pull、tracking）各不相同，VEO 3.1 按论文所述严格区分。

## VEO 的艺术流派引用

VEO 对具体艺术流派作为风格锚点响应良好：
- "旋涡星空风的油彩笔触"（后印象派笔法参考）
- "融化轮廓的超现实主义场景"
- "建筑立面上的几何装饰花纹"
- "包豪斯式的冲线条与三原色"
- "做旧粗粒的图文小说风格"
- "水墨洗练的中国风动画"

## 防止字幕

VEO 有对白时可能默认加字幕，避免方式：
- 在负向提示中加入："no subtitles, no captions, no text overlays"

## 示例

```
Subject: A lone astronaut in a weathered white spacesuit
Action: Slowly turns to face the camera, visor reflecting a dying star
Scene: Surface of a barren moon, cracked grey terrain, massive ringed
       planet filling the horizon
Camera: Low-angle medium shot, slow arc around subject
Lens: Wide-angle, deep focus keeping both astronaut and planet sharp
Lighting: Harsh rim light from the star behind, cool blue fill from
          planet reflection, no atmosphere diffusion
Mood: Awe, isolation, quiet grandeur
Style: Photorealistic sci-fi cinematography, IMAX-scale
Audio: Breathing inside helmet, faint radio static, low rumble
Negative: No text, no HUD overlay, no lens flare
```
