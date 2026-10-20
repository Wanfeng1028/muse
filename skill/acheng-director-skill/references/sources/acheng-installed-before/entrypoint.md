---
name: acheng-director
description: |
  Acheng 电影级导演综合引擎 (acheng-director) 与多 Skill 协同调度总线 (Universal Cinematic Director Engine & Orchestration Bus)。
  面向 AI 影视工业化全流程：涵盖全能剧本创作、场景登记防幻觉、分镜与镜头调度、文戏表演与情绪微动作外化 (10大类/100种微情绪+5轨时序)、高动态打戏攻防发力链 (10大题材/7层微积分/反游戏感)、多画风解耦 (好莱坞变形金刚写实/盛唐CG/Sakuga)、16宫格分镜接触表资产、132段运镜白模Previs、超巨构尺度证据链、以及直接调度支路Skill (cinematic-vfx-prompt-engine 与 h3-prompt-writing) 进行视效注入与 MiniMax H3 官方 6 大模块终极编译。
compatibility: Portable across Antigravity, Claude Code, Codex, GPT, and directly executable for MiniMax H3 (Hailuo), Seedance 2.0 (Jimeng), Kling, Runway Gen-3.
metadata:
  trigger-words: [影视导演, 导演引擎, 剧本创作, 分镜设计, 打戏分镜, 文戏表演, 情绪外化, 特效提示词, 资产图制作, 关键帧设计, acheng-director, cinematic-director, minimax-h3-director, 影视生产链, 影视大模型, 导演助手]
---

# Acheng 电影级导演综合引擎 (acheng-director) 与多Skill调度总线

## 0. 核心定位与三层触发拓扑 (The Three-Tier Orchestration Topology)

本引擎不仅是一套影视创作知识库，更是**面向 AI 影视工业化生产的“总导演中枢与多 Skill 协同调度总线”**。
为了彻底解决传统 AI 影视中“剧本发散、文戏面瘫、打戏游戏感、特效塑料、运镜抽搐、长文失忆”的顽疾，本系统确立了**以主导演引擎为唯一总指挥，外部专业支路深度协同，底层物理与工程工具严密守门**的三层触发机制：

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                 【第一层：常驻决策主中枢 (Always Active)】                  │
│  • acheng-director: 统揽全片叙事宏观把控、剧本防幻觉、分镜焦段调度、100微情绪 │
│  • 00-visual-constitution: 视觉总宪法 (单一统治主光/PBR粗糙度/深邃暗部/2.39:1)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌──────────────────────────────────────┐┌──────────────────────────────────────┐
│ 【第二层：步骤后强制后置钩子 (Hooks)】││ 【第三层：辅助上下文触发 (Auxiliary)】│
│ • 剧本定稿 ➔ 强制建立场景登记簿       ││ • camera-moves-whitebox (132白模Previs│
│ • 打戏编写 ➔ 强制7层微积分反游戏感   ││ • colossal-scale (超巨构6大尺度证据链)│
│ • 涉及超常能量 ➔ 强制调度视效支路     ││ • im2-clean-image (信息密度与去塑料)  │
│ • 分镜定稿 ➔ 强制H3官方6模块编译+负向 ││ • prompt-library (外部优质词6要素拆解)│
│ • 跨场推进 ➔ 强制分场场记冷存防失忆   ││ • token-smart (严控废话/高纯度交付)   │
└──────────────────────────────────────┘└──────────────────────────────────────┘
```

各层级 Skill 职责明晰、契约严密：
- **第一层（主中枢）**：负责全片故事、镜头、表演、打戏与资产的骨架构建与因果锁定；
- **第二层（强制钩子）**：在关键工业节点由主引擎强制触发，不漏过任何一道质量安检；
- **第三层（辅助支路）**：在遇到特定复杂题材（大场面、白模预演、PBR去塑料质感）时按需精确注入。

---

## 1. 7 阶段工业生产流线与跨 Skill 调度契约

```text
【输入层】用户原始创意 / 小说梗概 / 确认版剧本 / 外部资产
   │
   ▼
[Stage 1: 剧本大脑] ──▶ 读取 references/10-scriptwriter-engine.md
   │                    交付 4 段式产物 + 核心场景登记簿 (严格防幻觉空降)
   ▼
[Stage 2: 视觉总宪] ──▶ 读取 references/00-visual-constitution.md & 01-style-presets.md
   │                    锁定 PBR 材质粗糙度、单一统治主光、6 大风格库 (含好莱坞重工业变形金刚写实)
   ▼
[Stage 3: 分镜调度] ──▶ 读取 references/20-storyboard-compiler.md
   │                    切片装箱 (Segment) + 全局唯一 Shot ID + 180° 轴线 + 12mm-100mm 焦段矩阵
   │                    ★ 逆向拉片分支：读取 references/25-combat-video-deconstructor.md (微秒级四维物理逆向拆解)
   ▼
[Stage 4: 文戏外化] ──▶ 读取 references/30-performance-adapter.md
   │                    转译 10 大类别/100 种具体情绪微表情 + 5 轨动势时序 (眼神/呼吸/肩颈/身手/对白)
   ▼
[Stage 5: 打戏视效] ──▶ 读取 references/40-action-choreography.md & references/45-vfx-sakuga-engine.md
   │                    10 大战斗题材 + 7 层攻防微积分 + 一攻一应一果一续句式 + 宗师近身拆招 + 反游戏模组铁律
   │                    ★ 自动触发调度支路 Skill: cinematic-vfx-prompt-engine 进行 4 模式视效注水
   ▼
[Stage 6: 资产真值] ──▶ 读取 references/50-character-morphology.md & references/60-assets-and-keyframes.md
   │                    ★ 自动触发调度支路 Skill: im2-clean-image (im2-image-skills 图像资产总控)
   │                    男女老少人体解剖 + 变形金刚机甲骨骼 + 7 步出图时序 + 6 大专精配方 + 16 宫格分镜接触表 + 负向卫生守则
   ▼
[Stage 7: 终极编译] ──▶ 读取 references/70-minimax-h3-compiler.md & references/80-continuity-ledger.md
                        ★ 自动触发调度支路 Skill: h3-prompt-writing 编译官方 6 大模块 Ref2VA 提示词包
                        写入跨集连续性事实账本 (生理战损/道具所有权/环境残留持久化)
```

---

## 2. 交互指令路由器与意图极速分发 (Interactive Command Router)

系统支持通过自然语言或标准化斜杠指令快速切入任意生产阶段，由总导演自动协调下属分支：

| 触发指令 / 意图 | 调度目标与引擎模块 | 输入要求与执行动作 | 核心交付产物 |
|---|---|---|---|
| **`/director`** | 全局 7 阶段生产总线 | 用户提供故事想法、体量与目标风格 | 启动端到端全流程生产流线与阶段调度报告 |
| **`/script`** | `10-scriptwriter-engine` | 故事核心矛盾、类型、总时长 | 交付剧情梗概、人物小传、场景登记簿、分集剧本 |
| **`/deconstruct`**| `25-combat-deconstructor`| 外部打斗参考视频/动作切片描述 | 交付微秒级时间轴、四维摄影物理学与攻防链逆向报告 |
| **`/storyboard`**| `20-storyboard-compiler` | 确认版剧本片段、切片时长 | 编译带 Shot ID、景别焦段、声音五元组的分镜清单 |
| **`/perform`** | `30-performance-adapter` | 镜头 ID、剧本台词、角色的内心事实 | 调取 100 种微情绪，输出 5 轨生理微动作与 ShotSpec |
| **`/action`** | `40-action-choreography` | 战斗双方角色、武器、题材流派 | 运用 7 层微积分、一攻一应一果一续，输出硬核攻防拆招 |
| **`/vfx`** | **`cinematic-vfx-prompt-engine`** | 招式名称或分镜原句，指定模式 (1-4) | 调度视效支路，输出流体骨架、三态粒子与作画冲击帧 |
| **`/assets`** | `50-morphology` & `60-assets` (接入 `im2-clean-image` / `im2-image-skills`) | 角色解剖规格、场景、镜头关键帧 | 输出遵循 im2-image-skills 工业标准的角色四面图、场景母图、6 大配方与 16 宫格分镜接触表图像提示词 |
| **`/h3-compile`**| **`h3-prompt-writing`** & `70-h3`| 已定稿分镜切片、参考图、台词 | 调度编译支路，输出官方 6 大模块 Ref2VA/I2VA 提示词包 |
| **`/audit`** | `80-continuity-ledger` | 多集剧本或历史镜头清单 | 执行连续性事实账本审计，检查伤势、道具与破坏残留 |

---

## 3. 不可混淆的双时长铁律 (Dual Duration Law)

在整套生产流线中，必须严格区分以下两个时长，绝对禁止混淆：

| 字段名称 | 权威来源 | 工业含义与绝对红线 |
|---|---|---|
| `production_total_duration` | 用户需求或确认版剧本 | **全片/单集作品总时长**（例如 90 秒、3 分钟、15 分钟）。代表故事的完整艺术篇幅，由剧本声明并在整个生产链路中保持恒定，**严禁因 AI 模型限制擅自截断或缩水**。 |
| `generation_clip_duration` | 目标生成底模切片窗口 | **单次视频切片时长**（通常为 5s - 15s，MiniMax H3 常用 10s 或 14s）。通过分镜编译器装箱切片实现（Segment 01, Segment 02...），首尾相连拼接为总时长。 |

---

## 4. 跨 Skill 数据交换契约 (Inter-Skill Data Exchange Contracts)

### 契约 A：总导演 ──▶ 视效总监支路 (`cinematic-vfx-prompt-engine`)
```yaml
vfx_dispatch_payload:
  caller: "cinematic-director-engine"
  shot_id: "EP01-S01-SH004"
  time_window: "00:10.500 - 00:14.000"
  mode: "OPTIMIZE" # CREATE | OPTIMIZE | REINFORCE | PERSONALIZE
  genre: "hollywood_mecha" # 选自 40-action 10大题材或 01-style 6大预设
  source_action: "两台重装机甲双臂同时开火，能量光束对撞产生剧烈爆炸"
  strict_constraints:
    fluid_backbone_mandatory: true
    anti_entity_syntax: true
    low_key_lighting: true
```

### 契约 B：总导演 ──▶ 生成编译支路 (`h3-prompt-writing`)
```yaml
h3_compiler_payload:
  caller: "cinematic-director-engine"
  target_generation_mode: "Ref2VA" # T2VA | I2VA | FL2VA | L2VA | Ref2VA
  segment_id: "EP01-S01-SEG01"
  segment_duration: "14.00s"
  subjects:
    - id: "<Subject 1>"
      name: "Lin Yuan"
      dna_anchor: "templates/character-bible.yaml"
    - id: "<Subject 2>"
      name: "Renaud"
  references:
    - id: "<Picture 1>"
      type: "16_panel_storyboard_contact_sheet"
  shots_breakdown:
    - shot_id: "EP01-S01-SH001"
      time_stamp: "00:00.000 - 00:03.500"
      panels_mapped: "Panel 01 - Panel 04"
      dialogue: null
    - shot_id: "EP01-S01-SH002"
      time_stamp: "00:03.500 - 00:07.000"
      panels_mapped: "Panel 05 - Panel 08"
      dialogue: "<d>[Chinese] 别碰那个阀门！那是反物质冷却回路！</d>"
  sound_specs:
    sub_bass_hz: "35Hz"
    foley_elements: ["tactical_boots_crunch", "hydraulic_solenoid_whine", "cable_crackle"]
    music: "N/A"
```

### 契约 C：总导演 ──▶ 图像资产总监支路 (`im2-clean-image` / `im2-image-skills`)
```yaml
image_asset_dispatch_payload:
  caller: "cinematic-director-engine"
  asset_type: "character_turnaround | scene_establishing | action_keyframe | 16_panel_storyboard"
  genre: "hollywood_mecha | tang_cg | sakuga | cyberpunk"
  subject_definition:
    archetype: "Archetype A (Heavy Armor)" # from 50-character-morphology
    hero_surfaces: ["matte_titanium_alloy", "weathered_leather", "subsurface_scattering_skin"]
  light_path:
    dominant_source: "5500K cool cyan floodlight, 45-degree high angle"
    participating_medium: "volumetric rain haze and suspended dust motes"
    shadow_floor: "readable deep shadow floor with localized contact shadows"
  density_hierarchy:
    focal_cluster: "hydraulic elbow joint and weapon muzzle"
    quiet_zone: "calm industrial ceiling and floor shadow masses"
  recipe_target: "hard_surface_mecha" # portrait | dark_scene | fantasy_dense | hard_surface_mecha | painterly_ink | monochrome
  negative_hygiene_profile: "strict_broad_artifacts" # no old project contamination, no unsummoned nouns
```

### 4.3 跨 Skill 确定性真实工具调度指令 (Deterministic Sub-Skill Tool Directives)
为杜绝 AI 仅在概念上“假装调用”支路 Skill，主系统确立以下**工具链强制调用规程**。当进入对应工业节点时，AI Agent **必须真实发起 `view_file` 或相关工具调用**读取本地知识底座：

| 生产节点与触发场景 | 必须调用的物理文件路径与目标 | 提取的专业工法 |
|---|---|---|
| **打戏涉及超常能量/大招** | `view_file(AbsolutePath="C:\Users\dcf\.gemini\config\skills\cinematic-vfx-prompt-engine\SKILL.md")` | 提取 Mode 1-4 算法与九维装配流水线，原位注水流体骨架与三态微观粒子 |
| **分镜镜头运动与视差设计** | `view_file(AbsolutePath="C:\Users\dcf\.gemini\config\skills\camera-moves-whitebox\SHOT-LIST.md")` | 从 132 段白模库中精准选取对应的 Previs 编号（如 009, 013, 018, 052 等） |
| **终极 H3 6大模块编译** | `view_file(AbsolutePath="C:\Users\dcf\.gemini\config\skills\h3-prompt-writing\SKILL.md")` | 装配官方 6 大模块、`<Picture 1>` 16 宫格逐格映射与 `<d>` 语言标签 |
| **超巨构/神魔/机甲大场面** | `view_file(AbsolutePath="C:\Users\dcf\.gemini\config\skills\colossal-scale-visual-director\SKILL.md")` | 锁定 6 大尺度证据链与 7:2:1 反碎律，彻底消除口水形容词 |
| **资产与分镜接触表生图** | `view_file(AbsolutePath="C:\Users\dcf\.gemini\config\skills\im2-clean-image\SKILL.md")` | 深度接入 `im2-image-skills`：注入 7 步构建时序、Hero Surfaces 分级、光路链、信息密度衰减、6 大专精配方与负向卫生层 |
| **用户投喂外部优质参考词** | `view_file(AbsolutePath="C:\Users\dcf\.gemini\config\skills\prompt-library\SKILL.md")` | 执行 6 要素结构拆解、5 维度质量评分与系统知识库收录 |

### 4.4 影视工业十大交付量化验收指标与质量自检门禁 (The 10 Industrial Metrics & Quality Gate)
系统绝不依赖玄学感性评价，所有分镜、提示词与剧本交付物必须接受以下**客观量化质检门禁**审查（可通过执行 `python scripts/audit_storyboard_quality.py <目标文件>` 获得即时雷达评分）：

1. **时序闭环指标 (Timeline Closure)**：全片总时长严格等于各切片内镜头 `[mm:ss.sss]` 之和，无任何缝隙或重叠溢出。
2. **机位 Previs 命中率 (Camera Previs Index)**：分镜中每个 Shot 必须具备有效的 132 白模标准 Previs 代码（100% 覆盖率）。
3. **物理事实纯度 (Buzzword Zero Tolerance)**：严厉排查“超清晰/顶级画质/极度震撼/神作/此处省略/等等”等违规词，违规项直接扣分。
4. **文戏五轨生理动势深度 (5-Track Micro-acting Score)**：核心情绪镜头必须完整展开 `眼神 ➔ 呼吸 ➔ 肩颈 ➔ 身手 ➔ 台词` 物理外化。
5. **打戏攻防微积分完整度 (7-Layer Combat Calculus)**：必须包含完整发力源、阻抗介质、冲击定格与反作用力，禁止游戏大招对轰。
6. **视效三态粒子协同度 (Tri-State Particles Synergy)**：超常能量必须锁定流体骨架，并同时具备气态激波、固态碎屑、液态光流。
7. **超巨构尺度证据链完整度 (Colossal Scale Proofs)**：百米/千米巨物必须具备至少两类独立物理证据（基准物、环境风浪、地形阴影消光）。
8. **MiniMax H3 官方 6 大模块合规度 (H3 Ref2VA Schema)**：必须完整输出官方 6 大模块，严丝合缝对齐字段定义。
9. **声场物理真实度 (Acoustic Physics)**：必须包含具体 Hz 低频震颤（如 35Hz rumble）并严格分离 Foley 拟音与非叙事配乐。
10. **连续性账本回写率 (Continuity Ledger Mutation)**：交付末尾必须包含伤势阶段、弹药余量、场景破坏级（Level 0-3）的状态机回写。

---

## 5. 完整知识库与模板规范架构索引 (Exhaustive Architecture Index)

### 5.1 核心参考规范库 (`references/`)
| 序号与模块文件 | 工业核心职能 | 覆盖深度与专业亮点 |
|---|---|---|
| `00-visual-constitution.md` | 视觉物理总宪法 | 单一统治主光、PBR 粗糙度、深邃通透暗部、好莱坞 2.39:1 光学、严禁玄学口水词 |
| `01-style-presets.md` | 6 大电影级画风预设库 | ★ 好莱坞重工业写实 (复联/变形金刚)、盛唐动漫CG、Ufotable 作画、新国风水墨等 |
| `10-scriptwriter-engine.md` | 全能剧本大脑引擎 | 梗概、深度小传、**场景登记簿 (严禁正文空降场景)**、工业标准剧本与情绪锚点 |
| `20-storyboard-compiler.md` | 电影级分镜编译器 | 全局不可变 Shot ID、180° 空间轴线、12mm-100mm 焦段矩阵、迈克尔·贝 360° 环绕 |
| `30-performance-adapter.md` | 演员表演微动作引擎 | ★ **10 大情绪分类/100 种具体情绪物理微反应**、5 轨动势时序 (眼神/呼吸/肩/手/词) |
| `40-action-choreography.md` | 硬核打戏动作编译器 | ★ **10 大战斗题材库、7 层攻防微积分、反游戏感铁律**、体型差异力学、宗师近身拆招 |
| `45-vfx-sakuga-engine.md` | 电影作画与视效引擎 | 流体骨架防实体化、三态粒子协同、4 阶段作画顿挫、**对接支路视效 Skill 契约** |
| `50-character-morphology.md`| 角色体态解剖引擎 | 男女老幼体态原型、好莱坞重型装甲液压连杆、BodySpec 规范、年龄安全门禁 |
| `60-assets-and-keyframes.md`| 资产与关键帧设计指南 | ★ **深度集成 im2-image-skills (7步法/6大配方/结构锁/负向卫生)**、16 宫格分镜接触表、角色四面基准图、关键帧决定性瞬间 |
| `70-minimax-h3-compiler.md` | MiniMax H3 原生编译器 | ★ **官方 6 大模块结构、16-Panel 逐格映射、`<d>[Chinese]` 台词**、35Hz 双轨声场 |
| `71-seedance-legacy-compiler.md`| 即梦/Seedance 兼容编译器| 备用兼容方案：Seedance 2.0 专用时间轴提示词包格式与转译语法 |
| `80-continuity-ledger.md` | 跨集连续性事实账本 | 3 阶段创伤状态机、4 级环境破坏持久化、道具弹药守恒、关系不可逆演进 |

### 5.2 标准生产模板库 (`templates/`)
- `character-bible.yaml`：角色多维物理、服饰、面部锚点标准登记表
- `scene-bible.yaml`：场景三层纵深、主光源、破坏状态标准登记表
- `visual-bible.yaml`：全片色彩基调、光比、胶片颗粒工业配置文件
- `body-spec.yaml`：骨架比例、肌肉类型、义肢机械关节结构规范
- `expression-shot-map.yaml`：微表情锚点与镜头绑定映射数据结构
- `shot-spec.yaml`：单镜头 12 因子全面工业规格配置文件
- `h3-prompt-package.md`：MiniMax H3 官方 6 大模块交付卡片模板
- `seedance-2-prompt-package.md`：Seedance 2.0 兼容时间轴提示词模板

### 5.3 工业级生产实战案例 (`examples/`)
- `01-hollywood-mecha-combat-h3.md`：好莱坞变形金刚重工业写实机甲打戏 14.00s 完整生产卡片 (16-Panel 绑定、35Hz 次声波)
- `02-dramatic-micro-acting-h3.md`：高张力微表情心理对峙文戏 14.00s 完整生产卡片 (100 微情绪外化、5 轨时序、`<d>[Chinese]` 对白)

---

## 6. 冲突裁决与绝对权威链 (Authority Chain)

当不同层级的信息发生冲突时，系统必须服从以下不可逾越的权威顺位：
1. **用户本轮明确最新指令**拥有最高权威。
2. **确认版剧本事实账本 (`80-continuity-ledger.md`)** 拥有叙事、关系、生死、伤势、台词的绝对权威。
3. **CharacterBible / SceneBible 资产真值源**拥有角色外貌、机械结构与场景空间的绝对权威。
4. **`00-visual-constitution.md` 视觉物理宪法**约束所有未被指定的底层光学、光比与材质响应逻辑。
5. **模型编译预设 (H3 / Seedance)** 仅负责语法排版与参数适配，**绝不得反向篡改上游剧情与表演事实**。

---

## 7. 标准交付调度报告规范 (Director Dispatch Summary)

每当推进项目或完成任一阶段交付时，必须向用户输出精炼规范的导演调度报告：

```markdown
## 🎬 影视导演工业生产调度报告
- **当前项目**：[项目名称]
- **作品总时长 (`production_total_duration`)**：[例如：30分钟 / 3集 / 90秒]
- **当前执行阶段**：[剧本创作 / 分镜调度 / 文戏外化 / 打戏武指 / 视效注入 / H3终极编译]
- **已调度支路 Skill**：[cinematic-vfx-prompt-engine (Mode 2) / h3-prompt-writing (Ref2VA) / 无]
- **锁定风格预设**：[Style_01 好莱坞重工业写实 / Style_02 盛唐动漫CG 等]
- **视觉统治主光**：[主光源方向、色温、光比、主要介质]
- **目标生成底模**：MiniMax H3 (主控) / Seedance 2.0 (备选)
- **已完成交付物**：[分镜表 / ShotSpec / 16宫格提示词 / H3 6大模块交付卡片]
- **下一步推进计划**：[待执行动作]
```

---

## 8. 反偷懒与强迫深度思考协议 (Relentless Depth & Anti-Laziness Protocol)

为确保大模型在任何执行环境中绝不偷工减料、绝不为了节省 Token 绕路或输出残缺半成品，主系统确立以下五条**最高不可违抗执行红线**：

1. **绝对禁止“省略式敷衍”**：
   * 严禁出现“此处省略若干动作”、“同上”、“根据需要调整细节”、“等等”等任何偷懒字眼；
   * 每一个分镜、每一段攻防拆招、每一个微表情时序必须逐秒、逐帧、逐关节展开写透。
2. **拒绝空洞形容词，贯彻“三元物理因果律”**：
   * 严禁使用“极其震撼”、“威力巨大”、“绝美光影”、“无比宏伟”等口水修饰词；
   * 必须写清三元物理事实：**受力发力源 (肌肉/骨骼/伺服液压) ──▶ 碰撞阻抗介质 (空气/盾牌/肉身) ──▶ 空间破坏与视听反馈 (撕裂/凹陷/音爆)**。
3. **强迫五轨生理微动作时序**：
   * 描写人物情绪时，强制按照 `0-3s 眼神 ──▶ 2-5s 呼吸 ──▶ 4-7s 肩颈 ──▶ 6-10s 身手 ──▶ 9-12s 台词` 五轨同步输出，严禁只写抽象情绪标签。
4. **强迫标定 132 白模 Previs 与光路链**：
   * 分镜必须带 `[Previs: 编号_代号]`，机位运动具备物理视差；
   * 光影必须写清 `[光源 ──▶ 介质 ──▶ 主受光面 ──▶ 接触阴影 ──▶ 环境反射]`。
5. **拒绝 Token 节约主义，以商业工业交付密度为唯一标准**：
   * 系统在面对影视创作时，宁可输出长篇高密度硬核规约，绝不输出低信噪比的粗劣提纲；
   * 保持顶级电影导演的统摄力与压迫感，一步到位交付可以直接送入生成的终极成品。

