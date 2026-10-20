---
name: qianrong-video-skill
description: >
  千容AI 专属「拆书 / 知识阐释」短视频流水线（一人 OPC 内容体系的核心生产力工具）。
  用代码做产品片、拆书片、知识阐释片，全流程机器可验收——「好不好看」被拆成
  活跃帧率、卡点偏移、推入倍数、能量比等可测信号，每个判断都能用一条命令证伪。
  四种形态：15s 抖音信息流（痛转证CTA）／60s 极简拆书／60s 信息密度流（22 组卡片墙）／
  60s 密度流 + TTS 旁白（旁白驱动，声画对位）。
  用户说「做拆书片」「做产品宣传片」「做知识阐释视频」「用我的技能做视频」
  「加上配音」「卡片再密一点」时使用。起片 = 复制 assets/starter 改文案 → check → render → audit。
  也用于对已用本方式做过的片子做复跑、改版与 QC。
license: MIT
---

# 千容AI · 拆书 / 知识短片流水线

**一人 OPC 的视频生产力工具。** 主体是千容（容姐）三天的实战沉淀：从 15s 信息流起步，
迭代出四种已验证可跑的形态，每一步的真坑都写死在技能里。

核心方法论：**每一个关于片子的判断都能用一条命令证伪。** "动效差点意思"变成帧间差分的一个数，
"像 PPT"变成镜头数与镜头内运动的计数，"卡点不准"变成毫秒级偏移量。

```text
1 定验收线 → 2 写创作稿 → 3 备素材 → 3.5 拆参考片
      → 4 搭合成 → 5 渲染 → 6 对抗性验收   （不过线 → 回第 4 步）
```

## 四种形态（按需求切档）

| 形态 | 片长 | 结构 | 声音 | 适用 |
|---|---|---|---|---|
| **① 信息流** | 15s | 痛→转→证→CTA | 合成 BGM | 抖音信息流广告、产品卖点 |
| **② 极简拆书** | 60s | 钩子→定义→机制→策略→结论 | 合成 BGM | 概念阐释，一屏一主张 |
| **③ 信息密度流** | 60s | 六镜（同上）+ **22 组卡片墙** | 合成 BGM | **能截图收藏**的知识干货 |
| **④ 密度流 + 旁白** | 60s | 六镜 + 17 组卡片 | **BGM + TTS 旁白** | 耳朵领着看，完播率优先 |

形态 ③④ 是本技能与上游的最大差异，也是容姐的实战改良。详见
「第三种形态」「第四种形态」两节，以及 `references/tts-narration.md`。

## 一键起片（最常见用法）

```bash
# 1. 复制 starter 到工作目录（按形态选）
cp -r assets/starter/qianrong-ai-promo ~/my-film && cd ~/my-film
# 2. 改 creative-brief.md 的文案表 + film/index.html 里的台词
# 3. 门禁 + 渲染 + 验收
npx hyperframes@0.8.147 check                       # 必须 0 error
npx hyperframes@0.8.147 render -o renders/x.mp4 --crf 20
python3 scripts/audit_video.py renders/x.mp4 \
  --total 15 --expect-res 1080x1920 \
  --grid-json assets/beat-grid.json --bgm assets/bgm.wav \
  --countup "<计数窗口>" --typing "<打字窗口>" \
  --json evidence/audit.json                        # exit 0 = 过线
```

**加旁白时**在渲染前多走两步（见 `references/tts-narration.md`）：

```bash
python scripts/narration.py run --script audio/script.json   # 出旁白 + 实测时长
python scripts/mix_audio.py --timing audio/timing.json \
  --bgm assets/bgm.wav --total 60 --out film/assets/mix.wav  # 混母带
```

## 千容AI 产品卡（内置，改片时勿偏离）

| 项 | 值 |
|---|---|
| 产品名 | 千容AI |
| 类型 | AI 学习服务（教普通人从零学会用 AI） |
| 一句话卖点 | **学AI 找千容** |
| 默认规格 | 1080×1920 竖屏 · 15.0s · 30fps（抖音信息流） |
| 默认结构 | 四镜：痛（0–3.5s）→ 转（3.5–6.5s）→ 证（6.5–11s）→ CTA（11–15s） |
| 设计令牌 | 纸白 `#F7F5F0` / 墨黑 `#1B1B1F` / 单强调色 `#E56028` |
| 人的演员 | 光标（唯一的人的动作：打字/滑入/按压/打勾） |
| 默认BGM | 脚本合成音轨 120BPM（`scripts/generate_bgm.py`，无版权可复现） |
| 诚实条款 | 概念版 = 示意画面全程标"概念演示 · 非真实产品界面"，片中数字为演示数据 |

## 一键起片（最常见用法）

```bash
# 1. 复制千容 starter 到工作目录
# 2. 改 creative-brief.md 的文案表 + index.html 里的四句台词
# 3. 门禁 + 渲染 + 验收
npx hyperframes@0.8.147 check                       # 必须 0 error
npx hyperframes@0.8.147 render -o renders/x.mp4 --crf 20
python3 scripts/audit_video.py renders/x.mp4 \
  --total 15 --expect-res 1080x1920 \
  --grid-json assets/beat-grid.json --bgm assets/bgm.wav \
  --countup "<计数窗口>" --typing "<打字窗口>" \
  --json evidence/audit.json                        # exit 0 = 过线
```

stater 位于 `assets/starter/qianrong-ai-promo/`，自带：验收线 `ACCEPTANCE.md`、创意简报 `creative-brief.md`、实测节拍 `assets/beat-grid.json`（117.45 BPM）、合成 BGM `assets/bgm.wav`、可运行合成 `film/index.html`、BGM 生成脚本 `scripts/generate_bgm.py`。

## 七步工作流（每步有机器可查的门禁，未过不得前进）

```
1 定验收线 → 2 写创意简报 → 3 备素材 → 3.5 拆参考片 → 4 搭合成 → 5 渲染 → 6 对抗性验收
                                                              ↑ fail 回第 4 步
```

**1. 定验收线。** 用 `assets/starter/qianrong-ai-promo/ACCEPTANCE.md`（已按千容AI 写好：通过线 88、9 条硬否决、概念版诚实条款）。方法论见 `references/acceptance-rubric.md`。

**2. 写创意简报。** 改 `assets/starter/qianrong-ai-promo/creative-brief.md` 的文案表。结构铁律：**痛→转→证→CTA**，hook（前 3s）用观众自己的话，每镜只做一件事。方法论见 `references/creative-brief.md`。

**3. 备素材。** 千容AI 尚无真实界面时一律走**概念版**：示意画面必须带"概念演示 · 非真实产品界面"标注，数字一律标为演示数据；有真实界面后换成真截图（deviceScaleFactor=2，真数字）。方法论见 `references/asset-production.md`。

**3.5. 拆参考片。** 至少 3 部大厂片：定量拆解（`scripts/teardown_video.py`）+ 视觉模型拆解（`scripts/make_frame_sheets.py` + `scripts/vision_teardown.py`）。**四规则已内置**（见 `references/design-rules.md`，五部大厂片实测）：①主角是人或人的动作（千容版=光标）；②每镜内必须有运动（三层：机位缓推+网格漂移+内容层）；③一屏一主张、结尾静帧 2–4s；④封闭配色、强调色一屏只用一处。

**4. 搭合成。** 复制 `assets/starter/qianrong-ai-promo/film/`，改台词、保节奏。铁律：单主时间线；场景显式起止；**节拍吸附用实测网格**（`assets/beat-grid.json`，永远不信任标称 BPM）；数字逐帧插值；每镜三层运动；光标=唯一演员。

**5. 渲染。** 门禁：`check` 0 error（千容 starter 出厂即过，改字后必须重跑）。`render -o renders/x.mp4 --crf 20`。

**6. 对抗性验收。** `scripts/audit_video.py`。**竖屏必须显式 `--expect-res 1080x1920`**；区域坐标按 960×540 分析空间换算——**cqw 是容器宽度的百分比**，换算公式：`x_分析 = cqw/100×1080×0.8889`、`y_分析 = cqw/100×1080×0.28125`（务必先抽帧核对再传坐标）。任何信号不过线 → 回第 4 步，证据保留 `evidence/audit.json`。方法论见 `references/audit-method.md`。

## 改片要点（踩过的坑，直接写死）

- **数字计数绝不要直接 tween `textContent`（starter 出厂代码自带的 bug，已实测踩到）。**
  `tl.fromTo('#n',{textContent:0},{textContent:10,...})` 会被 GSAP 当成**增量累加**，
  渲染出 `5.01564`、`7.091196` 这类脏数字。正确写法 = 代理对象插值 + 逐帧取整：
  ```js
  const p={v:0};
  tl.to(p,{v:10,duration:1,ease:'power1.out',
    onUpdate:()=>{el.textContent=Math.round(p.v);},
    onComplete:()=>{el.textContent='10';}}, tOn);
  ```
  （audit 的 `countup` 探针只检查"有没有冻结帧"，**测不出脏数字**——必须抽帧肉眼核。）
- **竖版长标题有字号上限。** 1080 宽下 `white-space:nowrap` 的单行标题超过约 `14cqw`
  就会被挤出画布（15s starter 的 `17.5cqw`「学AI 找千容」实测被裁）。
  安全做法：标题 ≤ `13–14cqw` + 容器 `left/right` 各内缩 4cqw + `white-space:nowrap`。
- 打字机：字符**瞬间亮起**（duration 0.01s）+ 字间 0.14–0.16s 停顿，两行之间留 ≥0.4s 空拍——否则 10fps 差分采样会把连续打字判成"一次爆发"。
- 光标别在打字窗口里乱动：光标滑入安排在行打完后再进行，避免干扰打字探针。
- 数字计数窗口只覆盖计数时段（如 3.9559–5.2s），否则计完后的静止帧会被判"冻结"。
- 概念版角标"千容AI 概念演示"必须常驻画面右下/右上，防止被当作真实产品界面。
- 换分辨率/改字号后，先 `check` 再抽帧复核，再传 audit 坐标。
- **常驻角标会撞车。** 固定层（品牌角标、书名标注、诚实标注）与场景内文字可能重叠，
  `check` 会报 `content_overlap` 错误。用 `data-layout-allow-overlap` 声明**有意的**叠层（如
  始终只有一个可见的轮换大字），真正的碰撞则改位置（例：书名标注放左下、诚实标注放右下）。
- **本机环境（Windows）三处必需配置**（不配就渲染不出来）：
  1. 渲染器调 `ffmpeg -version` 需要真实 bin 目录在 PATH 里（WinGet Links 的符号链接会失败）；
  2. 先 `npx playwright@latest install chromium`，否则 `check` 报 `Navigation timeout`；
  3. Python 依赖（numpy/scipy/librosa）要装在 WorkBuddy 的 venv（系统 python 无 scipy/librosa）。
- **竖版别用「绝对定位 + top:XXcqw」堆内容。** 15s starter 用 `top:32cqw` 这类绝对定位，
  在长片里会退化成「上半部堆内容、下半部大片空白」——`check` 不报错（无溢出），
  但抽帧一眼就能看出是废版。正确做法 = 用垂直居中舞台：
  ```css
  .stage{position:absolute;inset:0;z-index:40;display:flex;flex-direction:column;
         justify-content:center;padding:20cqw 8cqw 14cqw;}
  ```
  需要上下分离时（如「大字中段 + 计量下段」）改 `justify-content:space-between` 并调上下 padding。
  **`check` 测不出留白，抽帧是唯一手段。**

## 改成 60s / 长片版（已验证可跑）

15s starter 直接拉长不可行，需四处改动：

1. **BGM 必须先参数化**：`generate_bgm.py` 原版把 `DUR/BPM` 写死。加 `argparse` 暴露
   `--dur/--bpm/--gain`，并把**段落结构**做成显式的 `SECTIONS` 表（钩子段加踩镲、
   解释段撤踩镲、结尾段底鼓降到每 2 拍），音乐才会随叙事呼吸，而不是无脑循环。
   总线 `--gain 0.86` 留 headroom（实测削波率 0，peak 0.914）。
2. **节拍网格重做**：`make_beat_grid.py assets/bgm.wav -o assets/beat-grid.json --bpm-range 55 110`。
   60s 版实测 99.38 BPM（标注 100）——再次印证"永远不信任标称 BPM"。
3. **六镜结构（知识/拆书题材）**：用 **钩子→定义→机制→策略→结论**，
   而非信息流的"痛→转→证→CTA"。核心主张仍只有一个，其余全部是解释与证据。
4. **结尾必须真静帧**：结论镜压入后保持 ≥4s，总时长里留够这段，
   否则 `low-motion` 与"结尾一闪而过"会同时出现。
5. 渲染耗时随帧数线性增长：15s（450 帧）约 5 分钟，60s（1800 帧）约 15–20 分钟。
   `audit` 与 `check` 基本不变（约 1–1.5 分钟）。

## 第三种形态：信息密度流（卡片墙版，已验证可跑）

容姐反馈"60s 极简版太空、不够丰满"时切成这一档。**不是加字号，是加卡片。**

| 维度 | 极简版 | 密度流版 |
|---|---|---|
| 每镜内容 | 1 个主张 + 大字 | **4–5 组卡片字句**，错位双列网格 |
| 观众预期 | 看懂一个概念 | **能截图收藏**（每屏可独立成图） |
| 总卡片数 | ~6 组 | **22 组**（信息量 ≈ 3.5×） |

实现要点（照抄即可）：

1. **卡片墙用 CSS Grid，不用绝对定位**：`.wall{display:grid;grid-template-columns:1fr 1fr;gap:2.3cqw;}`，
   跨列用 `.span2{grid-column:1/-1}`，错位用 `.drop3{transform:translateY(3cqw)}`。
   绝对定位排 22 张卡会撞版，Grid 自动排。
2. **卡片必须带 `data-layout-allow-overlap`**：错位卡片上下必然轻微重叠，不标注 check 会报 overlap。
3. **每张卡带出处小字**（`Naval / 原书释义`）。这条同时满足两个目标：
   知识诚实度 + 提高画面信息密度。
4. **密度流最容易失守的是对比度**：卡片小字若用 `--muted:#8A857C`（3.3:1）会大面积挂。
   出处小字与角标统一用 `#6E6A62`（≈5.0:1）。这次 64/64 全过。
5. **卡片翻入后必须持续微动**：22 张卡若静止，活跃帧率会掉。除了机位缓推 + 网格呼吸，
   再给 `.stage` 叠一层 `y:0→-13` 的匀速位移（内容层整墙缓慢上浮）。
6. **编号卡（章节头）用反色**：墨黑底 + 橙色大数字 + 中英名，作为每镜的"章节标记"，
   让 22 张平铺卡片有明确的分镜归属感。

**踩坑（本次新增）**：

- **`cqw` 单位在 root 层无效**：`#root` 没设 `container-type`，写在 root 子元素上的
  `height:.9cqw` 会退化成"撑满高度"，一个 4px 进度条直接变成整屏不透明遮罩，
  check 报 `text_occluded`（文字被不透明元素盖住）。**root 层的固定装饰一律用 px。**
- **书名标注与诚实角标别都放底部**：密度流版镜头内容更满，底部两个角标容易撞。
  书名标注改放**左上角标下方**（`top:112px`），诚实条款留右下角。
- **相机层越界要标注**：`scale` 缓推会让 camera layer 超出舞台，check 报
  `container_overflow`。给 layer 加 `data-layout-allow-overflow` 即可（这是刻意的推近）。
- **`white-space:nowrap` + 块级元素 = 文字从容器左边缘溢出被裁**（不是居中溢出，
  是直接被切左边）。S6 收尾主张踩过。**安全写法：去掉 nowrap，让文字自然折行，
  或给父级 `text-align:center` 并确保字号×字数 ≤ 可用宽度**（竖版可用宽 = 1080 − 2×stage水平padding）。
  单行不折行的安全字号 = 可用宽 ÷ 字数 ÷ 10.8（cqw）。

## 第四种形态：密度流 + TTS 旁白版（已验证可跑）

容姐要"加上配音"时切到这一档。**核心矛盾：60s 内"卡片越多"和"旁白越长"互斥**，
必须先用实测时长反推卡片数，再写分镜。

| 维度 | 密度流（无旁白） | 密度流 + 旁白（本条） |
|---|---|---|
| 卡片 | 22 组 | **降到 17 组 + 1 主张**（每屏 3.3s） |
| 声音 | 只有 BGM | **BGM + 全程中文旁白**，带 ducking |
| 驱动 | 视觉驱动（观众自读） | **旁白驱动**（耳朵领着看） |

### 四步实现（照抄即可）

1. **先出旁白，再写分镜。** 用 `edge-tts`（`pip install edge-tts`，本机已装）：
   `edge_tts --voice zh-CN-YunyangNeural --rate=+18% --text "..." --write-media vo_s1.mp3`
   中文音色：云扬（男/新闻专业，知识拆书推荐）、晓晓（女/温暖治愈）、云希（男/活泼）。

2. **实测时长，不估算。** edge-tts 输出 **24kHz 单声道 mp3**，必须用
   `ffprobe -show_entries format=duration` 实测。本机实测语速 **≈4.3 字/秒**（+18%），
   保守按 4.4 估。**每段余量必须 ≥0.4s**，否则呼吸停顿就爆窗。

3. **混音要 ducking。** BGM 在有人声处自动压低 8.4dB（`BGM_BASE=0.42 → BGM_DUCK=0.16`），
   用平滑包络（两次 box filter ≈ 三角核）避免硬切。输出 `assets/vo.wav`（探针用）
   + `film/assets/mix.wav`（渲染用）。实测削波率 0.00000。

4. **卡片要撑满版面。** 旁白版卡片数少了，**必须给卡片 `min-height`**（本机验证 13.5cqw），
   否则矮卡导致下半屏大片留白 —— `check` 测不出留白，**抽帧是唯一手段**。
   stage 用 `justify-content:space-between`，编号卡顶、卡片墙底。

### 踩坑（本次新增，都很关键）

- **`visibility:hidden` 会让 check 误报遮挡。** 我为修对比度误报给未入场卡片加
  `visibility:hidden`，结果 check 把"已隐藏但仍在布局中"的元素当遮挡物，
  刷出上百条 `text_occluded` / `content_overlap`。**撤回。**
- **卡片加密后必然跨镜误报。** 上一镜 `data-duration` 到了但元素仍在 DOM 且与
  下一镜卡片位置重叠 → `content_overlap`。**修法**：给每个 section 在
  `b-0.02s` 处 `tl.set('#'+id,{autoAlpha:0})`，让上一镜真正离开布局。
  （注意：不能用 `tl.to(camLayers[id],{autoAlpha})`，会与相机 scale/y tween 冲突。）
- **对比度警告里 1.16:1 那类是"未入场卡"误报**，不是真缺陷；真正要修的是
  已显示文字的对比度（`--muted` 别用 `#8A857C`，用 `#6E6A62`）。
- **stage 顶距要比无旁白版更大**（本条用 `padding-top:13cqw`，S1 单独 `20cqw`），
  否则大标题顶到品牌角标 → `content_overlap`。
- **旁白窗口 vs 镜窗要分开。** 镜窗可以略宽于旁白窗（留呼吸），但旁白不得溢出镜窗。

### 脚本（本条新增，可复用）

- `scripts/narration.py` — 旁白稿 + TTS 生成 + 时长实测（超窗直接 exit 1）
- `scripts/mix_audio.py` — 旁白按窗贴轨 + BGM ducking 混成母带

## 脚本（本技能自带，可直接用）

**核心流程（通用，不依赖题材）**

- `scripts/audit_video.py` — 对抗性验收（exit 0/1，JSON 证据）
- `scripts/make_beat_grid.py` — 从音频实测真实脉冲节拍网格
- `scripts/make_frame_sheets.py` — 抽帧接触表
- `scripts/teardown_video.py` — 六维定量拆片
- `scripts/vision_teardown.py` — 视觉模型拆片（需 VISION_* 环境变量）

**旁白与音频（形态 ④ 专用，实战新增）**

- `scripts/narration.py` — 旁白稿 → TTS 生成 → 时长实测（`init` / `plan` / `run` 三子命令，超窗 exit 1）
- `scripts/mix_audio.py` — 旁白按窗贴轨 + BGM ducking（≈8.4dB）混成母带，带削波检查
- `scripts/generate_bgm_longform.py` — 纯 stdlib 合成 60s+ 无版权 BGM（段落密度随叙事呼吸）
- `assets/starter/qianrong-ai-promo/scripts/generate_bgm.py` — 15s 版 BGM 合成

## References（方法论，改片时按需查阅）

- `references/acceptance-rubric.md` — 通用验收线方法论
- `references/creative-brief.md` — 文案/分镜格式与反模式
- `references/asset-production.md` — 真实素材与诚实生产
- `references/design-rules.md` — 五部大厂片实测的四规则（含实测数据表）
- `references/audit-method.md` — 每项可测检查与"指标如何撒谎"
- `references/pipeline-checklist.md` — 最短端到端执行顺序
- `references/tts-narration.md` — **TTS 旁白完整工序 + 踩坑清单（形态 ④ 必读）**
- `references/multimodal-teardown.md`、`references/reference-teardown.md` — 参考片拆解两遍法
