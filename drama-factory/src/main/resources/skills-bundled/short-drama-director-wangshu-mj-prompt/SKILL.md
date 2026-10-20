---
name: wangshu-mj-prompt
description: "王叔MJ提示词：Midjourney(MJ) 高质量英文文生图提示词写作、优化与拆解专家。当用户提到 MJ / Midjourney / mj prompt、要求把中文场景概念转成 MJ 提示词、优化现有 MJ 提示词、或分析某条 MJ 提示词为什么效果好时触发。输出英文正文提示词（可直接粘贴 MJ），正文用 ```txt 代码块包裹 + 落盘 outputs/*.txt + present_files 展示，中文要点注释在代码块外。"
agent_created: true
---

# 王叔MJ提示词 — Midjourney 高质量提示词写作专家

## 核心理念（先记住这三句）

1. MJ 提示词不是"描述一张图"，而是"拍一个镜头"——服务构图与情绪，不是罗列物件。
2. 真实感来自**材质词**：名词必须挂材质形容词，模型才渲染得出可信物理表面（不塑料）。
3. 漂亮光影来自**光的动作化 + 对比**：给光"颜色+光源+形状+动作"，用冷暖对比（或主题色×环境色）逼出明暗层次。

## 一、八模块总公式（从黄金样例提炼，主链）

```txt
[时空锚点] , [环境→结构→道具 由大到小递进] , [主体/中心物件+材质定义] , [光的动作化] , [情绪定调] , [风格强化堆叠] , [负向排除句] --ar 16:9 --stylize 数值 --v 版本
```

| 模块 | 负责的效果 | 一句话规则 |
|---|---|---|
| 1 时空锚点 | 叙事重量/辨识度 | 历史锚(人物+地点+年份)或世界观锚(神话/科幻IP)，开头7-12词锁死 |
| 2 镜头递进 | 构图不乱、有纵深 | 环境→结构→道具由大到小；用"消失/坠落/延伸"动词造纵深 |
| 3 主体+材质定义 | 画面中心、真实感 | at center / solitary / surrounded by 立中心；发光体也给材质定义 |
| 4 光的动作 | 戏剧光影 | 光必须"有动作"且与地面/门缝/水互动，不止是"亮" |
| 5 情绪定调 | 氛围基调 | 2-3个情绪形容词或 Atmosphere of ... 句式 |
| 6 风格堆叠 | 质感放大 | 题材风→明暗术语→体积光→细节→photorealistic 逐层压上 |
| 7 负向排除 | 防穿帮/防跑偏 | no people / no modern elements / empty cage，句尾自然语言排除 |
| 8 参数 | 画幅/艺术化/版本 | --ar / --stylize / --v。**不写 --style raw、不写 --sref/--cref/--cw**（见输出铁律 8、9） |

## 二、模块详解与写法规则

### 模块1：时空锚点（开篇第一句）
- **历史锚**：人物+地点+年份 → `Empty prison cell of Joan of Arc, Rouen, 1431`
- **世界观锚**：神话/科幻 IP 词一次点燃想象 → `beneath a Norse underworld, beneath Yggdrasil's roots`（后文再补 `Atmosphere of Hel, Niflheim` 呼应）
- 规则：拒绝 "a medieval prison" 式泛场景，锚点越具体越不撞素材图。

### 模块2：镜头递进（环境→结构→道具）
从大到小、从环境到物件，一句话一层，逗号串联：

```txt
fortress → cell → door → window → pallet → candle
cavern → cliffs/roots/monoliths → platform → cage → runes/chains
```

纵深动词库：vanishing into darkness、disappear into darkness、descending into a bottomless abyss、extending into infinity、leading to、rising above。
技巧：同一"消失"母题重复 2 次 + 一次"无底深渊"，制造无限/未知感（北欧样例用了 vanishing into darkness ×2 + bottomless abyss）。

### 模块3：主体 + 材质定义
- 构图中心：`Frozen black water surrounds a solitary circular stone platform. At center: ...` —— 先水围平台，再 at center 点主体，视线被强制收拢。
- **非实体主体（能量/光体）三层写法兜底**：
  1) 排除错误材质：`no metal`
  2) 比喻限定质感：`flickering like supernatural fire` / `translucent crimson energy`
  3) 环境反射证实存在：`casting scarlet reflections across wet obsidian floor`
- 装置感：给主体加"功能细节"让画面活起来：`faint red runes orbit slowly; crimson energy arcs connect to surrounding standing stones`。

### 模块4：光的动作化（光影分水岭）
模板：`[颜色] + [光源] + [动作动词/比喻] + [环境互动]`

```txt
pale silver moonlight cutting across darkness like a blade
subtle amber glow beyond the closed door
faint pearlescent reflections within moonlight
casting scarlet reflections across wet obsidian floor
```

对比原则：
- 常规戏剧光 = **冷暖对比**（冷月光 × 暖烛光/门缝光）
- 主题化光 = 全片锁定一个能量色，色彩语言统一（北欧样例：crimson/scarlet/red 能量色统治全图 × obsidian/black 冷底，加 stone 下 red bioluminescence 点内光）

### 模块5：情绪定调（3个以内）
情绪词库：melancholic, ominous, dreamlike, sinister, apocalyptic, sacred, desolate, haunting, serene, triumphant, nostalgic, ethereal。
可用 `Atmosphere of ...` 句式把氛围直接写成一行（Atmosphere of Hel, Niflheim）。

### 模块6：风格强化堆叠
按"题材风 → 光影术语 → 体积/大气 → 细节 → 照片级"顺序叠 4-6 个词，题材风放最前：

```txt
dark historical fantasy realism, dramatic chiaroscuro, cinematic volumetric light, hyperdetailed textures, photorealistic
apocalyptic Norse dark fantasy, cinematic chiaroscuro, volumetric fog, hyperdetailed, photorealistic
```

跨类型混搭句式：`X fused with Y` / `X meets Y` / `blend of X and Y`（如 ancient mythology fused with pre-human technology）。

### 模块7：负向排除（句尾）
```txt
No people, no modern elements.
No people, empty cage.   ← 主体是笼子时强调"空的"，保留"曾经关过谁"的悬念
```
MJ 对句尾自然语言排除响应良好；--no 参数可作双保险。

### 模块8：参数速查（正文末尾空一格追加）
| 参数 | 作用 | 用法 |
|---|---|---|
| --ar 16:9 / 9:16 / 2:3 / 21:9 | 画幅 | 电影感 16:9 或 21:9，海报 2:3，竖屏 9:16 |
| --v 版本号 | 模型版本 | 跟随官方最新（2026 样例为 --v 8.2）|
| --stylize 0-1000（默认100） | 艺术化程度 | 高值→光影氛围更强更艺术化、略偏离字面；低值（100-150）贴近字面，适合设计图与技术参考 |
| ~~--style raw~~ | **禁止使用** | **2026-10-11 王叔确立：以后所有任务都不写 `--style raw`。** 想贴近字面改用低 `--stylize`，不要靠这个参数 |
| --no | 负向参数 | 与句尾排除句叠加双保险 |
| --chaos 0-100 | 结果变化度 | 探索高值、定稿低值 |
| ~~--sref / --cref / --cw~~ | **禁止使用** | **2026-10-13 王叔确立：`--v 8.2` 下这些参数没有功能，一律不写。**（见输出铁律 9） |

## 三、效果 → 模块归因（写提示词时按需砸权重）

| 想要 | 重点砸哪个模块 |
|---|---|
| 真实感 / 不塑料 | 模块3 材质定义 + 模块4 光的环境互动 |
| 漂亮光影 | 模块4 光的动作化 + 参数 --stylize |
| 构图不乱 | 模块2 镜头递进 + 方位词(surrounded by / at center) |
| 不撞素材图 | 模块1 时空锚点（越具体越不泛）|
| 氛围情绪 | 模块5 情绪词 + 模块6 风格堆叠 + 模块2 纵深动词 |

## 四、黄金样例（完整原文 + 模块标注，可直接当模板套）

### 样例一：贞德囚室 —— 历史锚 · 写实暗黑 · 冷暖对比
```txt
Empty prison cell of Joan of Arc, Rouen, 1431. Small oppressive late medieval stone chamber inside a massive Norman fortress. Rough cold limestone walls darkened by moisture, narrow vaulted ceiling, heavy wooden door reinforced with black iron bands. Tiny barred window set deep into the wall revealing a cold moonlit night. Simple wooden sleeping pallet with coarse linen and rough wool blanket. Heavy iron shackles and short chain fixed into the stone beside the bed. Small wooden stool, extinguished candle beside a simple wooden cross, scattered straw across uneven stone floor. Faint rainwater traces on walls. Pale silver moonlight cutting across darkness like a blade. Subtle amber glow beyond the closed door. Barely perceptible floor mist. Faint pearlescent reflections within moonlight suggesting something sacred. Melancholic, ominous, dreamlike. Dark historical fantasy realism, dramatic chiaroscuro, cinematic volumetric light, hyperdetailed textures, photorealistic. No people, no modern elements.
```
模块标注：`Joan of Arc, Rouen, 1431`=锚点｜fortress→cell→door→window→pallet→candle=递进｜每个名词挂材质(rough cold limestone / coarse linen / black iron bands)=真实感｜moonlight cutting like a blade + amber glow + pearlescent reflections=光的动作+冷暖｜melancholic, ominous, dreamlike=情绪｜dark realism→chiaroscuro→volumetric→photorealistic=风格堆叠｜No people, no modern elements=负向排除。

### 样例二：北欧神话能量牢笼 —— 世界观锚 · 主题单色光 · 无实体主体
```txt
Sinister mythological prison beneath a Norse underworld, immense subterranean cavern beneath Yggdrasil's roots. Colossal black stone cliffs vanishing into darkness, enormous twisted petrified roots crossing ceiling and walls, ancient runic monoliths half embedded in rock. Frozen black water surrounds a solitary circular stone platform. At center: an eerie cage of translucent crimson energy, tall pulsating red light bars forming a cylindrical prison, no metal, flickering like supernatural fire, casting scarlet reflections across wet obsidian floor. Faint red runes orbit slowly; crimson energy arcs connect to surrounding standing stones. Enormous broken Norse carved chains disappear into darkness. Distant waterfalls descend into a bottomless abyss. Spectral mist drifts above water, hints of gigantic serpentine carvings on walls. Red bioluminescence beneath stone. Atmosphere of Hel, Niflheim, ancient mythology fused with pre human technology. No people, empty cage. Cinematic chiaroscuro, volumetric fog, hyperdetailed, photorealistic, apocalyptic Norse dark fantasy. --ar 16:9 --stylize 900 --v 8.2
```
模块标注：`Norse underworld / Yggdrasil's roots`=世界观锚｜cavern→cliffs→roots→monoliths→platform→cage→runes=递进｜`surrounded by ... At center:`=构图收拢｜能量体三层写法(translucent crimson energy / no metal / like supernatural fire / casting reflections)=无实体材质定义｜vanishing into darkness ×2 + bottomless abyss=纵深母题｜crimson/scarlet/red 单色统治 × obsidian 冷底=主题化光｜Hel, Niflheim + fused with pre-human technology=情绪+混搭风格｜`No people, empty cage`=负向排除(强调空笼悬念)｜`--ar 16:9 --stylize 900 --v 8.2`=参数(高 stylize 强化光影氛围)。

## 五、拆解别人的 MJ 提示词（学习流程）

1. 找锚点：开头有没有历史/世界观锁死句？删掉它画面还剩什么？
2. 画递进链：环境→结构→道具顺序成立吗？纵深靠哪些动词？
3. 挑材质词：每个名词挂了什么？有没有"比喻式材质"（no metal / like fire）？
4. 看光的写法：光源？动作动词？颜色对比？光与地面/门缝/水面如何互动？
5. 读色彩语言：全图是冷暖双色，还是主题单色统治？
6. 抄风格词顺序与题材风句、情绪词。
7. 记参数：--ar / --stylize / --v 组合。
8. 交付：用同样的模块骨架重建一份新提示词给用户验证。

## 六、输出格式铁律（必须执行）

1. 提示词**正文英文**（MJ 原生语言响应最稳、材质/光影短语都是英文训练语料），创作解释与要点注释用中文。
2. 英文正文用 ` ```txt ` 代码块包裹（确保一键复制）；中文要点注释放代码块外。
3. 同时将正文落盘 `outputs/mj-prompt-YYYYMMDD-序号.txt`，并用 present_files 展示。
4. 代码块内不放任何解释性文字；不做开场白/结束语。
5. 若用户只给主题没给细节（主体/世界观/氛围/画幅），一次 AskUserQuestion 问清，不反复确认。
6. **四版本输出（铁律，2026-09-04 王叔确立）**：场景类 MJ 任务默认一次产出 **4 个不同感受的版本**。差异轴 = 时段 × 光线 × 情绪 × 色彩语言（如晨雾清冷 / 黄昏熔金 / 深夜月下 / 沙暴压迫）；**同一场景、同一套材质词、同一构图骨架**，只换光影与情绪，四版并列供挑选。每版独立 ```txt 代码块；落盘合并到同一 outputs txt，版本间用 `=== 版本名 ===` 分隔行；中文标注各版感受与用途。
7. **背景板留白（铁律，2026-09-23 王叔确立）**：当提示词是给 AI 视频做背景/空镜/道具位时，**前景与地面必须留空**——不能只写"空间干净"，要正向写 `completely clear and empty across its whole surface`，并把地面物件（地垫/毛巾/水瓶/落地风扇等）全部删掉；"生活痕迹"类道具一律挪到**墙面、窗台、台面**上（不占人物与运镜的活动区），并负向锁 `no objects on the floor` 一类。王叔原话：「不要在前景放什么东西」「地板上不要有东西」。
8. **禁用 `--style raw`（铁律，2026-10-11 王叔确立）**：**以后所有任务都不写 `--style raw`。** 正文末尾的参数只保留 `--ar` / `--stylize` / `--v`。想贴近提示词字面、减少 MJ 风格加成，**靠压低 `--stylize`（设计图与技术参考用 100-150）来实现**，不要用这个参数。王叔原话：「不要把 --style raw 写进去，以后都去掉这个」。历史文件里出现过的 `--style raw` 一律视为过期写法。
9. **禁用 `--sref` / `--cref` / `--cw`（铁律，2026-10-13 王叔确立）**：**`--v 8.2` 下这些参数没有功能，一律不写。** 王叔原话：「--sref --cref 都是 8.2 没有功能，以后不要写这个了」。**角色一致性、风格一致性不再靠参数，改靠：① 把要锁的图直接作为 image prompt 放在提示词最前面（配合 `--iw`）；② 或在提示词文字里锁特征。** 历史文件里出现过的 `--sref` / `--cref` / `--cw` 一律视为过期写法，不照抄。

## 七、执行流程

1. 判定任务类型：写新 / 优化 / 拆解他人提示词。
2. 收集信息：主体、世界观或历史设定、氛围基调、画幅用途。
3. 按八模块搭骨架 → **默认展开 4 个感受变体**（见输出铁律 6）→ 逐模块填词 → 自查三问：每个名词有材质吗？光有动作和对比吗？有负向排除吗？
4. 英文正文落盘 txt + 中文注释 → present_files。**正文参数区只写 `--ar` / `--stylize` / `--v`，绝不写 `--style raw`。**
5. 用户有参考图时：**不要写 `--sref` / `--cref` / `--cw`（8.2 下无功能，见铁律 9）**——指导用户把参考图直接作为 image prompt 放在输入最前面（可配 `--iw`），提示词本身仍按公式写。

## 八、常见坑位速查（症状 → 触发词 → 修法）

| 症状 | 真正的病因（触发词） | 修法 |
|---|---|---|
| **屋顶一出就是中式** | `curling up at the eaves`（翘檐）+ `glazed jade / green tiles`（绿色釉面瓦）+ `ridge`（正脊）三件套同时出现 = 东亚官式建筑配方 | 三样全删。改有机材质：`overlapping nacre plates set like scales, pearl and pale rose`，只写 `lifting only at the tips like a leaf`，并锁 `no Chinese roof, no upturned eaves, no glazed roof tiles` |
| 角度变成正交死平 | `top-down` / `straight down` / `overhead` / `bird's eye` | 删掉，改 `oblique` + `perspective` + `receding toward the top of the frame` |
| 写实要求却出塑料偶像剧感 | `pastel` / `high-key` / `dreamy soft focus` / `beauty` | 删掉，改真实摄影参数（35mm / f/2.8）+ 去假四禁：`no CGI look, no plastic surfaces, no over-smoothed skin, no beauty filter` |
| **精灵／贵族题材出破败感** | `weathered` / `stained` / `patched or missing` / `moss creeping` / `worn smooth` | 降"高级感"和降"破败感"是两个正交轴：只压 **scale**（modest / small in scale），**维护状态**拉满（smooth pale / laid true and even / precisely cut and clean / folded neatly），并锁 `no decay, no ruin, no broken tiles, no peeling paint, no rust, no dirt, no weeds` |
| 想要孤景却总被补山补远岛 | 只写了 `island` / `isolated`，模型会自动补背景地形做层次 | **正向声明 + 负向锁地形**同时做：正向 `barely rises above the water, with no hills and no high ground`、`nothing taller in sight`；负向 `no mountains, no hills, no cliffs, no high ground, no background islands, no distant coastline, no headland` |
| 人物在大场景里崩脸 | 写了 figures / crowds 却没限规模 | 只写 `a few ... small in frame`，并锁 `no crowds, no close-up figures, no detailed faces` |
| 提示词越写越长、还越不听话 | 同一批约束在多个段落重复，负向列表堆到 30+ 项 | 单条压到 150–200 词；负向砍到 12–15 项且**不跨段重复**；写实类堆叠词只留一次 |
