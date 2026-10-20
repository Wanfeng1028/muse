# PDoomVideo 存档说明

来源仓库：https://github.com/JohnHeibel/PDoomVideo （本次存档基于 main 分支浅克隆后逐文件拉取，2026-10-20）

## 这是什么

Claude Opus 5.5 用代码"画"出来的一支完整 MV 工程：《I'm Upping My P(doom)》，全长 156.6 秒。做法是 p5.js + p5.brush 水彩逐帧绘制、无头 Chrome 渲染、ffmpeg 合成 MP4，全仓库内容均由模型在 Claude Code 里生成，只给了两条方向：用 Clawd 角色设计、每句歌词要有有趣的画面和转场。

剧坊已收录的 **painted-animation** skill 就是从这个工程提炼出的通用方法，它自带的 template 则是作者后续做的通用底座 ClaudeAnimationBase。

## 文件构成（已全量存入，共 25 个文件，752KB）

| 路径 | 内容 |
|---|---|
| STORYBOARD.md | Opus 写的逐镜头分镜计划 |
| ANIMATION_GUIDE.md | Opus 写给并行子 agent 的风格与代码指南（核心提示词资产） |
| README.md | 原仓库说明（两代生成过程、渲染方法） |
| src/ch/ | 九个章节的场景源码（c01–c09） |
| src/ | 共享代码：角色 Clawd、配角、道具、歌词、时间线 |
| studio.html | 逐帧绘制的页面（p5.js + p5.brush） |
| render.mjs | 渲染脚本：无头 Chrome 逐帧出图 + ffmpeg 编码 |
| legacy/ | 第一代生成（flash-version.html、test-scenes.js） |
| package.json / package-lock.json | 依赖声明 |

## 未存入的内容

- `assets/pdoom.mp3`（3.4MB 歌曲音频）：媒体文件不入本仓库，需要时去原仓库取。
- 原仓库 README 里引用的演示图/视频（GitHub user-attachments 外链）：未镜像，点原仓库 README 查看。
