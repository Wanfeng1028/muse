# Code Music Video Skill

**让音乐时间驱动画面，把代码 MV 制作流程交给 Agent。**

从 [mexicat/pdoom-video](https://github.com/mexicat/pdoom-video) 提炼的独立通用
Skill：音乐时间数据 → 场景设计 → 确定性代码 → 浏览器预览 → 短片验收 → 离线导出。
方法与工具适配分开，不绑定个人电脑、账号或某个模型。

> A portable Agent Skill for deterministic, music-driven code videos.
> Includes workflow guidance, a timeline contract, a validator and a project
> brief. Bring your own music and rendering engine.

![代码音乐视频制作流程一图流](media/workflow.png)

## 它能做什么

- 制定音乐驱动的程序化 MV、歌词排版和图形动画制作计划。
- 统一节拍、段落、歌词与画面的时间坐标。
- 指导可定位到任意时间、可重复渲染的场景实现。
- 把短片同步验收、离线逐帧渲染和成片检查串成完整流程。
- 按需使用人工时间标注或自动分析，不强制下载大模型。

**这是制作方法包，不是一键生成器。** 不包含原项目音乐、歌词、字体、
场景代码或渲染引擎；不直接替代剪辑软件或文生视频平台。

## 安装

仓库根目录就是 Skill。将它克隆到 Agent 的 skills 目录，并以
`code-music-video` 命名。本例针对 Codex；自定义 `CODEX_HOME` 时用其 skills
目录代替默认路径。

macOS / Linux:

```sh
git clone https://github.com/q2522879285-source/code-music-video-skill.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/code-music-video"
```

Windows PowerShell:

```powershell
$skills = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $HOME '.codex\skills' }
git clone https://github.com/q2522879285-source/code-music-video-skill.git (Join-Path $skills 'code-music-video')
```

其他支持 `SKILL.md` 的 Agent，可把整个目录放入自己的 Skill 发现路径。
安装只增加指令与本包脚本，不安装分析模型或渲染依赖。

## 使用

```text
用 $code-music-video 制作代码音乐视频。
音乐：我提供的音频，使用 0–30 秒。
规格：16:9，1920×1080，60 fps。
方向：冷静的线框空间，副歌切入高能量图形。
先做制作计划，再实现一个包含转场的短片测试；不要发布。
```

Agent 从 [SKILL.md](SKILL.md) 开始，只读取当前分支需要的参考。
也可以只说“用这个 Skill 检查时间线”，不必启动完整制作。

## 本地检查

只需要 **Python 3.10+，无第三方 Python 依赖**：

```sh
python scripts/validate_timeline.py examples/timeline.json
python -m unittest discover -s tests -v
```

示例是原创的 6 秒虚构时间线，用于格式测试，不是音频分析结果。
校验器可定位乱序节拍、不连续段落、重叠歌词、越界时间与非法能量值；
通过校验不代表它们与某首音乐已经同步。

## 文件入口

| 文件 | 用途 |
|---|---|
| [SKILL.md](SKILL.md) | 制作步骤、完成标准与停止条件 |
| [assets/brief.template.md](assets/brief.template.md) | 项目规格、场景计划与验收记录模板 |
| [references/contracts.md](references/contracts.md) | 时间线格式、工具能力与分段帧计数契约 |
| [references/audio-analysis.md](references/audio-analysis.md) | 人工/自动时间分析与可选歌词对齐 |
| [references/pdoom-adapter.md](references/pdoom-adapter.md) | 上游引擎映射与命令示例 |
| [scripts/validate_timeline.py](scripts/validate_timeline.py) | 可直接执行、可导入的时间线校验器 |
| [SOURCES.md](SOURCES.md) | 来源、提炼边界与迁移实验 |

## 验证边界

| 项目 | 状态 |
|---|---|
| 时间线正例、失败例与 CLI | 本包自动测试 |
| Skill 元数据与文件结构 | 本包结构校验 |
| 上游引擎接口与命令 | 对照固定版本文档/源码检查 |
| 完整 MV、Windows 引擎运行、4K 吞吐 | 未在本包认证；由实际项目测试 |

新音乐需重新分析时间、设计场景并接入渲染器；不是换一个 MP3 就能沿用
原片的场景编排。分数帧率不属于时间线 v1；需要时扩展契约及校验器。

## 来源与许可

灵感来源：[mexicat/pdoom-video](https://github.com/mexicat/pdoom-video)。
原项目代码为 MIT，歌曲、歌词和字体有独立权属。本仓库不分发这些素材。
本包原创代码与文档使用 [MIT License](LICENSE)。
