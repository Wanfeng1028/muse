# 千容AI · 拆书视频流水线

**`qianrong-video-skill`** —— 只用代码 + 真实素材，做出一支能上热门的 60 秒竖版拆书视频。
不用剪辑软件，不用拉时间轴，**能配音、能卡点、能机器验收**。

这套流程的价值不在「做出一个片子」，而在**片子上的每个判断都能被一条命令证伪**：
「动效差点意思」变成帧间差分的一个数，「像 PPT」变成镜头数与镜头内运动的计数，
「卡点不准」变成毫秒级的偏移量，「配音没对上」变成旁白窗口余量的秒数。

```text
① 定验收线 → ② 写创作稿 → ③ 备真实素材 → ④ 拆解参考片
      → ⑤ 搭建合成 → ⑥ 渲染 → ⑦ 对抗性验收   （不过线 → 回到 ⑤）
```

---

## 一、演示成片

### 密度流 + TTS 旁白版 ·《唤醒创造力》

<p align="center">
  <a href="demo/qianrong-creative-60s.mp4">
    <img src="assets/demo-creative-poster.jpg" alt="《唤醒创造力》60s 拆书片 — 密度流 + TTS 旁白" width="42%">
  </a>
</p>

**60.0s · 1080×1920 竖版 · 30fps · 含全程中文旁白**

*17 组卡片 + 1 主张 · BGM 在有人声处自动压低 8.4dB · 旁白总长 47.28s（占片长 79%）*

### 信息密度流版 ·《纳瓦尔宝典》

<p align="center">
  <a href="demo/qianrong-naval-60s.mp4">
    <img src="assets/demo-naval-poster.jpg" alt="《纳瓦尔宝典》60s 拆书片 — 信息密度流" width="42%">
  </a>
</p>

**60.0s · 1080×1920 竖版 · 30fps · 仅 BGM**

*22 组卡片 · 每屏约 2.7s · 纯视觉驱动，靠字幕读*

> **说明：两条片子全程由 AI 对话驱动完成**——从定验收标准、写创作稿、排卡片文案，
> 到卡点对齐、混音 ducking、改配色、修版式，没有手工剪辑，也没有打开过任何剪辑软件。
> 唯一的人工输入是「确认哪个方向」和「哪里不对」。

---

## 二、它和「随便生成一段视频」有什么区别

| | 常见做法 | 这套流程 |
|---|---|---|
| 好坏标准 | 靠感觉，反复返工 | 先写验收标准（加权维度 + 硬否决项），再动一帧 |
| 画面素材 | 生成的假界面、编的数字 | 真实产品截图、真实数据 |
| 动效 | 「再加点效果」 | 先量出来是镜头太长、还是镜头内没东西在动 |
| 卡点 | 肉眼对齐 | 从音乐源文件算出真实脉冲，全片吸附 |
| 配音 | 「随便配一段」 | **先出 TTS 实测时长，再反推卡片数**，每段留 ≥0.4s 余量 |
| 验收 | 看一遍觉得还行 | `audit_video.py` 逐项测，退出码 0/1 |

---

## 三、四种形态（按需求选档）

同一个骨架，四种交付形态。**先定形态，再动手。**

| 形态 | 时长 | 卡片 | 声音 | 适用 |
|---|---|---|---|---|
| **A. 15s 信息流** | 15s | 4 镜 × 1–2 卡 | BGM | 抖音/视频号信息流广告 |
| **B. 60s 极简** | 60s | 6 组 | BGM 为主 | 单概念讲透 |
| **C. 60s 密度流** | 60s | **22 组** | 仅 BGM | 拆书/知识流，观众自读 |
| **D. 60s 密度流 + TTS 旁白** | 60s | **17 组 + 1 主张** | **BGM + 全程中文旁白** | 拆书/知识流，耳朵领着看 |

> ⚠️ **60s 内「卡片越多」和「旁白越长」是互斥的。**
> 按实测语速 4.3 字/秒算，22 组卡需要约 100s 旁白——**超片长 40%**。
> 想两全必须拉到 75–90s，否则只能二选一。
> 完整推导见 `references/tts-narration.md`。

---

## 四、安装

这是一个标准 skill 目录，直接克隆到 skills 路径即可：

```bash
# 用 Codex / Claude Code 的 agent skills 目录
git clone https://github.com/yanghui960/qianrong-video-skill.git \
  ~/.agents/skills/qianrong-video-skill
```

克隆后把整个仓库当作 `qianrong-video-skill` 这个技能使用，入口是 `SKILL.md`。

### 依赖

- **Node**（`npx hyperframes`）——默认渲染器。流程本身与框架无关，任何能输出 MP4 的渲染器都行。
- **Python 3.9+**，需要 `numpy`、`scipy`、`librosa`、`Pillow`。
- **ffmpeg / ffprobe** 在 `PATH` 里。
- **形态 D 额外需要**：`edge-tts`（`pip install edge-tts`）、`soundfile`。
- 可选：一个 OpenAI 兼容的多模态模型，供 `vision_teardown.py` 做语义拆解
  （设置 `VISION_ENDPOINT` / `VISION_MODEL` / `VISION_API_KEY`）。

---

## 五、五分钟上手

```bash
# 1. 把 starter 拷成你自己的片子
cp -r assets/starter/qianrong-ai-promo ~/my-film && cd ~/my-film

# 2. 先证明工具链是通的（开箱就是 0 error）
npx hyperframes@0.8.147 check
npx hyperframes@0.8.147 render -o renders/smoke.mp4 --crf 24

# 3. 换成你自己的文案 / 真实封面 / BGM，然后走完六步
```

starter 里已经写好并验证过的模式：设计令牌、真实封面卡片、「生长式」入场、三层摄影机、结尾留白。

### 形态 D（带 TTS 旁白）额外三步

```bash
# 1. 写旁白剧本 JSON（六段窗口 + 文案），然后生成 TTS 并实测时长
python scripts/narration.py --script narrations/my-book.json --out-dir audio
#    → 超窗直接 exit 1，必须先改稿或改窗口

# 2. 旁白按窗贴轨 + BGM ducking，混成母带（60s）
python scripts/mix_audio.py --vo audio/narration/vo_s1.mp3 ... --bgm assets/bgm.wav \
  --dur 60 --out assets/vo.wav --mix film/assets/mix.wav

# 3. 把 film/index.html 的音频指向 mix.wav，再走 check → render → audit
```

---

## 六、六步流程

### ① 定验收线（最容易被跳过，也最贵）

先写 `ACCEPTANCE.md`：一句话定义「优秀」，加权评分维度，加**硬否决项**（触犯任意一条直接不通过）。
模板见 `references/acceptance-rubric.md`。

### ② 写创作稿

产出一句话核心主张 + 逐镜文案表 + 视觉语言 + 分镜表。
开场 3 秒必须用**观众自己的话**回答「我为什么要在乎」；每个镜头只干一件事。
见 `references/creative-brief.md`。

### ③ 备真实素材

铁律：**产品有真界面就截真界面，有真数据就用真数字。**
先把演示数据做全真，否则成片全是占位。
Playwright 用 `deviceScaleFactor=2` 采集；「活着」的动作要录成真视频，不能用静图。
见 `references/asset-production.md`。

### ④ 拆解参考片（两遍）

至少拆 **3 部**大厂片（一部是风格，三部才是规律）：

- **量化**：`references/reference-teardown.md` —— 镜头数/时长、镜头内运动、卡点偏移。
- **语义**：`references/multimodal-teardown.md` —— 带时间戳的关键帧板喂多模态模型，跑 7 个视角，
  最后一步 `improve_ours` 把参考片和你的片子同屏对比，直接产出改进清单。

**跨片复现的四条规律**收在 `references/design-rules.md`，动手前先读，比重新推导便宜。

### ⑤ 搭建合成

一条主时间线；场景显式声明起止；**一切卡点吸附到音乐的「真实脉冲」**，不要相信标注的 BPM；
数字用逐帧插值，不要「每拍 set 一次」；每个场景都要有环境运动层。
HUD 层（角标、标注）不要跟着摄影机变换走，否则边缘文字会被推出画布。

**密度流专属三条硬规矩**（踩过的坑，见 `references/tts-narration.md`）：

- 卡片必须给 `min-height` 撑版（本机验证 **13.5–22cqw**），否则矮卡导致下半屏大片留白；
  `check` 测不出留白，**抽帧是唯一手段**。
- `.wall` 用 `align-content:space-between` + `flex:1`，父容器 flex column，让网格行铺满。
- 卡片入场必须压在**镜窗前 60%** 内完成，否则中段抽帧会看到「占位空白」。

### ⑥ 渲染

```bash
npx hyperframes@0.8.147 check                       # 必须 0 error
npx hyperframes@0.8.147 render -o renders/xxx.mp4 --crf 20
```

全屏缓慢缩放的片子，CRF 给太低体积会翻几倍；CRF 20 一般观感无差。

### ⑦ 对抗性验收（真正的核心）

不要问「好不好看」，要问**「哪一帧能证明它是死的 / 假的 / 错的」**，然后去量。

```bash
python scripts/audit_video.py renders/xxx.mp4 \
  --total 60 --expect-res 1080x1920 --dur-tol 0.3 \
  --grid-json assets/beat-grid.json --bgm assets/bgm.wav \
  --countup "t0:t1:x:y:w:h" --typing "..." \
  --json evidence/audit.json        # 退出码 0 = 过线，1 = 未过
```

它会测：规格、开场音频能量比、分块运动（**frozen 与 low-motion 分开报**）、空/黑帧、
卡点偏移、推近倍数（区域内模板匹配）、真视频是否在播、数字是否连续。

细节与阈值见 `references/audit-method.md`。

---

## 七、目录结构

```text
qianrong-video-skill/
├── SKILL.md                     技能入口：流程、硬规矩、按需读哪份文档
├── README.md                    英文说明
├── README.zh-CN.md              本文件（中文说明）
├── demo/
│   ├── qianrong-creative-60s.mp4   《唤醒创造力》密度流 + TTS 旁白
│   └── qianrong-naval-60s.mp4      《纳瓦尔宝典》信息密度流
├── references/
│   ├── acceptance-rubric.md     验收标准（维度 + 硬否决项）
│   ├── creative-brief.md        创作稿 / 分镜 / 视觉语言格式
│   ├── asset-production.md      真实素材怎么做、怎么不被做假
│   ├── design-rules.md          五部参考片提炼出的四条规律（附测量数据）
│   ├── multimodal-teardown.md   多模态语义拆解（含调用格式与两个坑）
│   ├── reference-teardown.md    量化拆解
│   ├── audit-method.md          每一项检查、阈值，以及「指标本身会骗人」
│   ├── tts-narration.md         TTS 旁白全流程、时间预算公式、七个坑
│   └── pipeline-checklist.md    最短上手清单
├── scripts/
│   ├── audit_video.py           对抗性验收器（退出码 0/1 + JSON 证据）
│   ├── make_beat_grid.py        从音乐里算真实脉冲节拍网格
│   ├── make_frame_sheets.py     视频 → 带时间戳的关键帧板
│   ├── vision_teardown.py       关键帧板 → 7 视角语义拆解
│   ├── teardown_video.py        六维量化拆解（结构/运动/文字/声音/卡点/配色）
│   ├── narration.py             旁白稿 → TTS 生成 + 时长实测（超窗 exit 1）
│   └── mix_audio.py             旁白按窗贴轨 + BGM ducking 混成母带
└── assets/
    ├── demo-creative-poster.jpg 演示片封面
    ├── demo-naval-poster.jpg    演示片封面
    ├── fonts/                   JetBrains Mono（OFL）
    └── starter/qianrong-ai-promo/  可直接运行的 15s 骨架（开箱 0 error）
```

---

## 八、许可

MIT。第三方组件与字体授权见 `THIRD_PARTY_NOTICES.md`。

---

**千容AI 出品** · 公众号「千容AI」· 拆书视频流水线
