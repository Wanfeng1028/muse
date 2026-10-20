# code-film · 用代码拍片的总导演

> A director-level agent skill for code-generated video with **Remotion** — story, storyboard, rhythm, style, motion, camera, sound, rendering and QA.
>
> **Built with Claude Opus 5.5** · 由 Claude Opus 5.5 协助创作

`code-film` 是一个面向 AI 编程助手的技能（skill）。它把「从零用代码做一支视频」变成一套可执行的导演流程：**讲故事 → 分镜规划 → 节奏设计 → 风格定调 → Remotion 实现 → 音画同步 → 渲染与自检 → 交付成片**。

它不只是一个「会写 Remotion 代码」的技能，而是一套完整的制片方法论：一切取舍都以故事为先，声音是时钟，`storyboard.json` 是唯一事实来源，画面永远是帧号的函数。所有可量化的环节都写成了脚本去自检，动感和听感则明确交给用户判断。

---

## 这是什么 / What is this

**中文**：`code-film` 是给 AI 编程助手（Claude Code、Kimi Code 等）使用的 agent skill。给定一个主题、一段文案、一首音乐或一堆素材，它能引导你完成情绪短片、PV、文字动效、MG 动态设计、科普讲解、产品宣传、数据可视化、音乐卡点、字符/ASCII 动画、2D/3D 混合动画，乃至 3 分钟以上的长片。

**English**: `code-film` is an agent skill for AI coding assistants (Claude Code, Kimi Code, etc.). Given a topic, a script, a piece of music, or a pile of raw assets, it walks you through producing emotional shorts, promotional videos (PV), kinetic typography, motion graphics, explainers, product promos, data visualizations, beat-synced music videos, ASCII/character animation, mixed 2D/3D animation, and even long-form pieces over 3 minutes.

## 特性 / Features

- 🎬 **全流程导演方法论**：故事 → 分镜 → 节奏 → 风格 → 动态预演 → 正式制作 → 声音 → 自检 → 交付，九个步骤环环相扣。
- 📋 **两种工作模式**：默认「陪跑模式」在 5 个关卡停下让用户确认；用户说「全自动」才一口气做完。
- ⏱️ **声音是时钟**：按配音、音乐结构或 BPM 网格排时间，所有动作落在拍子上。
- 🧱 **单一事实来源**：`storyboard.json` 同时驱动画面、音效和字幕，杜绝音画错位。
- 🔬 **可量化的自检**：Python 脚本校验分镜、分析音乐 BPM/节拍、合成配乐与音效、渲染缩略图墙、体检成片（黑帧/冻帧/静音/响度）、响度标准化。
- 🎨 **可复用工程模板**：一个开箱即用的 Remotion 工程，自带虚拟摄像机、字符画、文字动效、颗粒/暗角质感与 13 种合成音效。
- 🚫 **拒绝随机**：画面只由帧号决定，禁止 `Math.random()`、CSS 动画、`setTimeout`——渲染稳定、可复现。

## 工作模式 / Modes

| 关卡 | 交给用户看什么 |
|---|---|
| ① 故事 | 一句话立意、结构、情绪曲线、全部屏幕文字和旁白（逐字定稿） |
| ② 分镜 | 分镜表（时间、画面、文字、声音、运镜、转场）和总时长 |
| ③ 风格帧 | 3 到 5 张关键镜头的静帧 PNG，外加配色、字体和质感说明 |
| ④ 动态预演 | 低清预演视频（灰盒加音乐也可以），只看节奏和时间 |
| ⑤ 成片 | 成片、自检报告，以及需要用户亲自看、亲自听的检查清单 |

- **陪跑模式（默认）**：每个关卡都交给你确认，你点头才继续。
- **全自动模式**：只有你说「全自动」「不用问我」「直接出片」时才进入，一口气做完，产物照样落盘。

## 目录结构 / Repository layout

```
code-film/
├── SKILL.md                    主技能文件：方法论、流程、工程约定、失败模式
├── references/                 20 个知识文件（故事、分镜、节奏、风格、运镜、音乐、QA…）
├── scripts/                    10 个 Python 工具（建工程、校验、分析音乐、合成音效、自检…）
├── assets/
│   ├── remotion-template/      开箱即用的 Remotion 工程模板（含示例配乐与音效）
│   └── templates/              策划书 / 长片总纲模板
├── README.md
└── LICENSE                     MIT
```

## 环境要求 / Requirements

- **Python 3.9+**（脚本通用）
- **numpy**（音频合成与分析脚本）
- **ffmpeg / ffprobe**（视频体检与响度标准化脚本）
- **Node.js + npm**（Remotion 工程）
- **Remotion 4.0.530**（模板已在 `package.json` 中锁定版本）
- 视频工程需放在**纯英文路径**下（中文路径偶尔会让渲染工具出错）

## 安装为技能 / Install as a skill

把整个 `code-film/` 目录放进你的 AI 助手技能目录，然后让助手读 `SKILL.md` 即可：

- **Claude Code**：`~/.claude/skills/code-film/`
- **Kimi Code**：`~/.kimi-code/skills/code-film/`（或项目内 `.kimi-code/skills/code-film/`）

## 快速开始 / Quick start

```bash
# 1. 从模板创建工程（脚本会复制 remotion-template 并写入标题/分辨率/帧率）
python scripts/new_project.py D:/films/sun --title "我从未见过太阳"

# 2. 进入工程并安装依赖
cd D:/films/sun && npm install

# 3. 浏览器预览（可拖时间轴）
npm run studio

# 4. 渲染单帧检查
npx remotion still Film out/f0120.png --frame=120

# 5. 半分辨率快速预演
npm run draft

# 6. 正式渲染
npm run render

# 7. 成片体检 + 响度标准化
python <skill>/scripts/qa_video.py out/film.mp4
python <skill>/scripts/finalize.py out/film.mp4 out/final.mp4
```

## 脚本索引 / Scripts

| 脚本 | 用途 |
|---|---|
| `new_project.py` | 从模板创建工程，写入标题、分辨率、帧率 |
| `check_storyboard.py` | 校验分镜：空档、重叠、总时长、拍点、阅读时间、重复、高潮位置 |
| `analyze_music.py` | 分析音乐：BPM、节拍、强拍、段落、能量曲线、重音、空拍 |
| `synth_music.py` | 纯代码合成配乐，同时输出段落时间图 |
| `synth_sfx.py` | 纯代码合成音效库，并记录每个音效的峰值时间 |
| `media_durations.py` | 批量读取配音时长，排出逐句时间轴 |
| `contact_sheet.py` | 生成缩略图墙，一眼看完整片构图和色彩走向 |
| `qa_video.py` | 成片体检：黑帧、冻帧（拖沓）、静音、响度、编码参数 |
| `finalize.py` | 两遍响度标准化，加 faststart，输出交付文件 |

## 参考文档 / References

`SKILL.md` 会在不同环节引导你读取 `references/` 下的知识文件：`routing.md`（接单与拆解）、`story.md`（讲故事）、`planning.md`（策划与分镜）、`rhythm.md`（节奏）、`music-edit.md`（音乐剪辑）、`sound.md`（音效与混音）、`motion.md`（动画）、`camera-transitions.md`（运镜与转场）、`typography.md`（文字动效）、`aesthetics.md`（质感）、`styles.md`（风格库）、`3d.md`（3D）、`pure-code.md`（纯代码方案）、`ai-assets.md`（AI 素材）、`long-form.md`（长片）、`remotion.md`（工程与渲染）、`qa.md`（自检）、`examples.md`（完整示例）。

## 许可证 / License

- 本仓库代码与文档采用 **MIT License**，详见 [LICENSE](./LICENSE)。
- 模板内置字体 **JetBrains Mono** 遵循 **SIL Open Font License 1.1**，版权归 The JetBrains Mono Project Authors，许可证文本见 [`assets/remotion-template/public/fonts/LICENSE-JetBrainsMono.txt`](./assets/remotion-template/public/fonts/LICENSE-JetBrainsMono.txt)。
- 模板内的示例配乐与音效由 `scripts/synth_music.py` / `scripts/synth_sfx.py` 合成，属于本仓库原创素材。
- **Remotion** 对个人与小团队免费，公司商用可能需要购买授权，请在交付商业项目前确认其授权条款。

## 致谢 / Acknowledgments

本技能由 **Claude Opus 5.5** 协助创作（Built with Claude Opus 5.5）。This project was created with the assistance of **Claude Opus 5.5**.