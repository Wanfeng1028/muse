---
name: openmontage-sora-prompting
version: "1.0.0"
description: 讲解 Sora 2 提示词写法，包含散文加摄影块模板、进阶电影参数与调色技巧，适用于追求镜头规格精确控制的短片与广告创作。
metadata:
  license: AGPL-3.0
---

# Sora 2 提示词指南

**词数：** Sora 2 在 100–250 词左右趋于饱和，超过 250 词后追加细节很少带来提升。

## Sora 专用提示模板

Sora 最适应"散文 + 摄影块 + 动作节拍"的结构化格式：

```
[散文式场景描述 —— 角色、服装、景致、天气、细节。
 尽量描述充分，以贴合你的设想。]

Cinematography:
Camera shot: [景别与角度]
Lens: [焦段、类型]
Lighting: [主光、辅光、轮廓光、实用光源及色温]
Mood: [整体基调]

Actions:
- [节拍 1：具体手势或动作]
- [节拍 2：另一独立节拍]
- [节拍 3：反应或对白]

Dialogue:
[简短自然的台词，按片段长度控制]
```

## 进阶可选字段

Sora 独有地响应这些多数模型忽略的制作级细节：

| 字段 | 示例 |
|-------|---------|
| **镜头规格** | "40mm spherical"、"85mm"、"Anamorphic 2.0x" |
| **滤镜** | "Black Pro-Mist 1/4"、"slight CPL rotation" |
| **调色 / 色板** | "Warm Kodak-inspired grade"、"teal-and-orange LUT" |
| **胶片模拟** | "16mm black-and-white"、"35mm photochemical contrast" |
| **画内声** | "faint rail screech, rain patters window, clock ticks" |
| **服装** | "navy coat, sleeves rolled, suspenders loose" |
| **后期质感** | "fine-grain overlay, mild halation, gate weave, soft vignette" |
| **快门** | "180° shutter angle" |
| **播放速度** | "speed ramp from 1x to 0.25x mid-shot"、"stop-motion staccato"、"time-reversed exhale" |
| **镜头畸变** | "edges bend outward like a fisheye lens"、"straight lines bow gently near the frame border" |
| **对焦模式** | "focus pulls from the bottle up front to the person behind"、"deep focus, everything from near to far stays sharp" |

## Sora 的与众不同

- **散文优先**：先写一段丰富描述，再加技术块。不要一上来就堆镜头规格。
- **角色参考**：API 可锁定最多 2 个上传的角色 ID。
- **对白同步**：短句有效，复杂的多角色对白不行。
- **编辑指令**："Same shot, switch to 85mm" 或 "Same lighting, new palette: teal, sand, rust"，Sora 支持在既有生成上做迭代精修。
- **创作自由度**：提示越短自由度越大，越长控制越强。

## 色板技巧

列出 3–5 个锚定色，而非笼统的"暖色调"：
- "Amber, cream, walnut brown"（复古暖意）
- "Teal, sand, rust"（海岸荒漠）
- "Cool blues with warm tungsten accents"（黑色电影）

## Sora API 参数（无法在提示中设定）

- `model`：`sora-2` 或 `sora-2-pro`
- `size`：720x1280、1280x720、1080x1920、1920x1080、1024x1792、1792x1024
- `seconds`：4、8、12、16、20

## 示例

```
Style: Hand-painted 2D/3D hybrid animation with soft brush textures,
warm tungsten lighting, tactile stop-motion feel. Subtle watercolor wash;
warm-cool balance; filmic motion blur.

Inside a cluttered workshop, shelves overflow with gears and yellowing
blueprints. Small round robot sits on wooden bench, dented body patched
with mismatched plates. Large glowing blue eyes flicker as it fiddles
with a humming light bulb.

Cinematography:
Camera: medium close-up, slow push-in with gentle parallax from hanging tools
Lens: 35mm virtual; shallow depth of field
Lighting: warm key from overhead practical; cool spill from window
Mood: gentle, whimsical, touch of suspense

Actions:
- Robot taps bulb; sparks crackle
- Flinches, dropping bulb, eyes widening
- Bulb tumbles in slow motion; catches it just in time
- Puff of steam escapes chest — relief and pride

Background Sound:
Rain, ticking clock, soft mechanical hum, faint bulb sizzle
```
