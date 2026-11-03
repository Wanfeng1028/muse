# MiniMax H3 原生终极视频编译器 (MiniMax H3 Native Compiler)

当分镜、表演、打戏动作与视效已经过上游严格解算，需要将其最终编译为符合 **MiniMax H3 (Video-01)** 官方最高规范的生产级提示词包时读取本文件。
本编译器全面支持 MiniMax H3 的 5 大生成模式、**官方标准 6 大模块结构 (Ref2VA / I2VA)**、16 宫格分镜 Panel 逐格绑定、双轨声场（含 Hz 低频参数与拟音分离）、`<d>[Chinese] 台词</d>` 官方语音标签、与外部支路 Skill `h3-prompt-writing` 的智能调度联动、以及 7 步 Preflight 安全审计。

---

## 1. MiniMax H3 官方工业级六大块架构 (The 6-Block H3 Specification)

针对高阶影视级生成（尤其是多角色、长镜头与 16 宫格分镜图参考模式），MiniMax H3 官方最强提示词必须按以下 6 大模块严格构建：

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. subject_definitions (实体与参考图定义)                    │
│    <Subject 1> is [角色身份/外观/服饰/微观特征]             │
│    <Subject 2> is [核心道具/武器/装甲]                      │
│    <Picture 1> is the 16-panel storyboard contact sheet...  │
├─────────────────────────────────────────────────────────────┤
│ 2. summary (全局概括)                                        │
│    [reference generation] The target video is a XX.00-sec...│
├─────────────────────────────────────────────────────────────┤
│ 3. retention_analysis (实体继承度分析)                       │
│    <Subject 1> (appears in [Shot 1]): fully_preserved - ... │
│    <Picture 1> (storyboard reference): fully_preserved ...  │
├─────────────────────────────────────────────────────────────┤
│ 4. detailed_description (逐镜头毫秒级动态视听描述)           │
│    [Shot 1] (00:00.000 - 00:03.500) 景别+运镜+Panel对应...  │
│    台词格式：<d>[Chinese] 具体的台词内容 </d>                │
├─────────────────────────────────────────────────────────────┤
│ 5. overall_soundscape (现场环境音、拟音 Foley 与低频震颤)     │
│    带精确声学物理描述 (如 35Hz sub-bass gravitational rumble)│
├─────────────────────────────────────────────────────────────┤
│ 6. non_diegetic_music (非叙事背景音乐)                       │
│    N/A 或 好莱坞管弦交响/重金属音律描述                     │
├─────────────────────────────────────────────────────────────┤
│ 7. Negative constraints (官方标准负向约束行)                 │
│    No blurry faces, no distorted features, no text...       │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 16 宫格分镜表逐格映射语法 (16-Grid Panel Binding)

当使用 Midjourney / FLUX / ComfyUI 制作的 16 宫格分镜接触表 (`16-panel storyboard contact sheet`) 作为 `<Picture 1>` 参考图输入时，必须遵循以下逐格映射规则：

1. **逐格锚定绝对真理**：
   - 每段切片必须在 `detailed_description` 中标明对应的格号：`(<Picture 1> Panel 01)` 至 `(<Picture 1> Panel 16)`。
   - 明确指示该格所定义的景别（大远景/全景/中景/特写/微距）、机位运镜（仰拍/俯拍/推镜头/追踪）与人物肢体动作。
2. **多镜头分段切片**：
   - 10-15 秒视频切片通常分配给 3-5 个 Shot，例如：
     - `[Shot 1] (00:00.000 - 00:03.500)` 对应 `Panel 01 - 04`
     - `[Shot 2] (00:03.500 - 00:07.000)` 对应 `Panel 05 - 08`
     - `[Shot 3] (00:07.000 - 00:10.500)` 对应 `Panel 09 - 12`
     - `[Shot 4] (00:10.500 - 00:14.000)` 对应 `Panel 13 - 16`
3. **防止宫格被误识别为画面**：
   - 必须在 Negative constraints 中加入：`no split-screen, no 16-grid layouts, no collage borders`，确保输出为全屏单一连续画面，而不是多宫格拼贴。

---

## 3. 官方台词与多模态声音标签语法 (`<d>` Tag Syntax)

在 MiniMax H3 中，角色对白必须严格使用官方 XML 标签注入：

```text
林远转头看向雷诺，下颌紧绷，用低沉克制的声线说道：<d>[Chinese] 别碰那个闸刀，那是反物质冷却回路！</d>
```
- **语言声明**：`[Chinese]` 或 `[English]`；
- **同步要求**：标签前必须写清发音角色的声线、语调与说话时的面部/喉部生理微动作，确保唇形与音频完美对齐。

---

## 4. 原生双轨声场与声学物理规格

必须将【现场音效】与【背景音乐】严格拆分为独立字段：

### overall_soundscape (现场环境音、对白与拟音音效)
- **次声波低频震颤**：明确标注低频 Hz 参数，例如 `A 35Hz sub-bass gravitational rumble vibrates under whistling gale winds`（35Hz 次声波引力震颤在呼啸烈风下轰鸣）。
- **同步拟音 (Foley)**：重型军靴踏碎玻璃的脆响、钛合金装甲铰链高压伺服尖锐蜂鸣、刀锋切开空气的破风呼啸。
- **声学空间特性**：空旷机库金属混响延时、密闭走廊吸音特性。

### non_diegetic_music (非叙事背景配乐)
- 若作品追求战场纪实或写实硬核，填写 `N/A` 或 `(无背景音乐，纯粹写实战场自然沉寂)`；
- 若需要电影配乐，详细描述器乐（如：汉斯·季默式重低音铜管 Braam、低沉大提琴长音渐强）。

---

## 5. MiniMax H3 负向提示词卫生守则与四维靶向防御块 (Negative Hygiene & Targeted Block)

传统 AI 影视的一大痛点是“把负向词当垃圾桶”，无脑堆砌冗长杂乱词汇（如 `worst quality, bad anatomy, ugly`），这会导致文本编码器注意力稀释，甚至引发**“负向反向显影（Negative Summoning）”**——模型反而被诱发生成奇怪的伪影。
本系统严格执行红猴子（hong hou zi）**负向提示词卫生法则**，仅保留经过严格数学与显存验证的**四维高精度靶向防御块**：

```text
Negative constraints: [Anatomy] no floating limbs, no extra fingers, no distorted facial features, no warped bone structure, [Layout] no split-screen, no 16-grid layouts, no collage borders, no comic panels, [Material] no plastic doll skin, no greasy oil glaze, no flat cell-shaded rendering, no dirty AO halos, [Screen] no subtitles, no captions, no on-screen text, no watermarks, no logos, no UI overlays, no low-bitrate compression artifacts.
```

*   **16 宫格防泄漏铁律**：在使用 Ref2VA 并以 16 宫格分镜接触表为参考图时，`no split-screen, no 16-grid layouts, no collage borders` 具有最高优先级，确保 H3 绝不把整张接触表切片渲染进单个视频镜头中。
*   **抗塑料去油腻铁律**：`no plastic doll skin, no greasy oil glaze` 配合上游 PBR 次表面散射描述，彻底锁死写实电影质感。

---

## 6. 与支路 Skill `h3-prompt-writing` 协同调度协议

在总导演引擎 (`cinematic-director-engine`) 编译输出时，根据镜头特性智能协同专业支路 Skill `h3-prompt-writing`：

```text
【总导演分镜与解算数据包】
          │
          ├── 判定生成模式 (T2VA / I2VA / FL2VA / L2VA / Ref2VA)
          │
          ▼
【支路 Skill: h3-prompt-writing 编译中枢】
  ├── 基础模式 (T2VA/I2VA/FL2VA/L2VA): 编译三轨流 (integrated_multimodal_description + 双声场)
  └── 全参考模式 (Ref2VA): 编译官方 6 大模块 (subject_definitions ~ Negative constraints)
          │
          ▼
【产出 MiniMax H3 终极工业交付卡片】
```

### 调度指令与数据载荷契约 (H3 Compilation Payload Contract)
```yaml
h3_compilation_request:
  caller: "cinematic-director-engine"
  target_skill: "h3-prompt-writing"
  generation_mode: "Ref2VA" # T2VA | I2VA | FL2VA | L2VA | Ref2VA
  segment_id: "EP01-S01-SEG01"
  segment_duration_seconds: 14.0
  subjects:
    - id: "<Subject 1>"
      name: "Lin Yuan"
      spec_anchor: "templates/character-bible.yaml"
    - id: "<Subject 2>"
      name: "Renaud"
  references:
    - id: "<Picture 1>"
      type: "16_panel_storyboard_contact_sheet"
      panels_used: "Panel 01 - Panel 16"
  shots:
    - shot_id: "EP01-S01-SH001"
      time_range: "00:00.000 - 00:03.500"
      panels: "Panel 01 - Panel 04"
      action_prompt: "..."
      dialogue: null
    - shot_id: "EP01-S01-SH002"
      time_range: "00:03.500 - 00:07.000"
      panels: "Panel 05 - Panel 08"
      dialogue: "<d>[Chinese] 别碰那个阀门！那是反物质冷却回路！</d>"
  acoustics:
    sub_bass_hz: "35Hz"
    foley_cues: ["boot_crunch_concrete", "hydraulic_whine", "cable_crackle"]
    music: "N/A"
```

---

## 7. 终极交付卡片标准范例 (Standard Production Card)

```text
subject_definitions:
<Subject 1> is Lin Yuan, a battle-hardened 32-year-old soldier with broad shoulders, chiseled square jaw, a faint diagonal scar on his right cheek, wearing scratched titanium-alloy modular exoskeleton armor with visible hydraulic lines, holding a tactical plasma carbine.
<Subject 2> is Renaud, an imposing cybernetic mercenary in blackened composite armor, featuring an exposed hydraulic right arm with glowing red conduits and a sneering scarred face.
<Picture 1> is the 16-panel storyboard contact sheet for this sequence.

summary:
[reference generation] The target video is a 14.00-second sequence meticulously following <Picture 1>: Lin Yuan entering the hangar (Panels 01-04), noticing the hydraulic sabotage (Panels 05-08), Renaud's ambush from the catwalk (Panels 09-12), and the standoff with weapons raised (Panels 13-16).

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot 2], [Shot 4]): fully_preserved - Lin Yuan's facial scar, scratched titanium exoskeleton, and cold focused gaze are retained.
<Subject 2> (appears in [Shot 3], [Shot 4]): fully_preserved - Renaud's red-conduit hydraulic arm and arrogant smirk are retained.
<Picture 1> (storyboard reference): fully_preserved - all 16 panels are strictly followed in sequential order.

detailed_description:
The target video is in Hollywood cinematic photorealistic style (2.39:1 anamorphic), meticulously unfolding the 16 panels of <Picture 1> across sequential shots in a single continuous full-screen view.
[Shot 1] (00:00.000 - 00:03.500) The camera begins with an extreme low-angle tracking shot through the hangar entrance, moving forward past puddles of oil reflecting the cool overhead floodlight (<Picture 1> Panel 01). The camera tilts up to frame <Subject 1> (Lin Yuan) walking forward in a grounded tactical stance, his boots crushing concrete grit (<Picture 1> Panel 02). A close-up tracks his tactical plasma carbine in low-ready position, horizontal blue anamorphic lens flare cutting across the receiver (<Picture 1> Panel 03). A medium close-up locks on his face as his eyes scan the dark gantry overhead (<Picture 1> Panel 04).
[Shot 2] (00:03.500 - 00:07.000) The shot cuts to an over-the-shoulder medium shot behind Lin Yuan looking toward the damaged central reactor gantry (<Picture 1> Panel 05). The camera pushes in as sparks rain down from severed power conduits (<Picture 1> Panel 06). A tight macro close-up captures Lin Yuan's jaw clenching, masseter muscle twitching as his breath hitches in realization (<Picture 1> Panel 07). He speaks in a low, urgent warning tone: <d>[Chinese] 别碰那个阀门！那是反物质冷却回路！</d> (<Picture 1> Panel 08).
[Shot 3] (00:07.000 - 00:10.500) The shot cuts to a high-angle medium shot on the upper industrial catwalk where <Subject 2> (Renaud) emerges from volumetric steam (<Picture 1> Panel 09). An extreme low-angle heroic rotation orbits Renaud as his right hydraulic arm pressurizes with an audible hiss (<Picture 1> Panel 10). Renaud steps heavily onto the rusted metal grating, his boot sending flakes of rust fluttering down (<Picture 1> Panel 11). A close-up frames his sneering face as he barks mockingly: <d>[Chinese] 太迟了！整座城市的能源，现在归我调度！</d> (<Picture 1> Panel 12).
[Shot 4] (00:10.500 - 00:14.000) The shot cuts to a dynamic two-shot establishing the 180-degree vertical combat axis: Lin Yuan below near the rails, Renaud above on the catwalk (<Picture 1> Panel 13). The camera crash-zooms into Lin Yuan's eye catching the keylight highlight, pupil contracting (<Picture 1> Panel 14). Renaud drops his hand onto the emergency release lever (<Picture 1> Panel 15). The sequence culminates in a balanced wide shot as both raise their weapons simultaneously, locked in an electric standoff (<Picture 1> Panel 16).

overall_soundscape:
A 35Hz sub-bass gravitational rumble vibrates beneath whistling wind leaking through the broken hangar roof. Heavy tactical boot crunches on wet gravel, followed by high-pressure hydraulic solenoid hissing and the electric crackle of severed cables. Distant emergency sirens wail through thick concrete walls.

non_diegetic_music:
N/A

Negative constraints: No blurry faces, no distorted facial features, no low resolution, no subtitles, no captions, no on-screen text, no watermarks, no logos, no UI elements, no split-screen, no 16-grid layouts, no collage borders, no unnatural skin, no cartoonish rendering, no floating limbs.
```
