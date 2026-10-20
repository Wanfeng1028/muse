[English](README.md) | **简体中文**

# ShotFlow for Remotion · 镜头与卡点

从参考片的具体画面出发，设计对象连续、信息可读、声音位置可核对的 Remotion 视频。

这是一个可安装的 Agent Skill，包含 **8 类镜头配方、10 条参考片索引和 3 个本地分析工具**。适合产品介绍、界面动效、参考片拆解与单镜头练习。中文说明为主；不包含可直接运行的 Remotion 应用或成片模板。

## 能帮你做什么

| 镜头方法 | 想让观众看懂的变化 |
|---|---|
| 卡片汇聚归位 | 多份内容被收进同一工作区 |
| 容器展开 | 一句输入逐步成为完整界面 |
| 阅读镜头 | 镜头跟随下一处要读的信息，并给结果留停顿 |
| 拖线与节点展开 | 一次操作连接成完整流程 |
| 几何与描边接续 | 图形借共同中心、线条或方向承接下一状态 |
| 按钮填屏 | 一个操作自然带入下一场景 |
| 等距品牌工位 | 对象沿工作流通过不同处理阶段 |
| 固定句式轮换 | 保留句子结构，轮换功能或结果 |

具体观察、适用条件和实现建议见 [镜头配方](references/shot-library.md)。技能还提供分镜记录、对象身份与时间轴管理、声音证据分级和验收方法。

## 原始参考在哪里

[参考目录](references/reference-catalog.md) 保留 10 条原帖链接、代表镜头秒段、文字观察和历史音轨测量结论。你可以从链接回看原作，再定位要学的片段。

**仓库不包含参考视频、原片截图、品牌图形、配乐、完整研究缓存或原作者工程。** 不需要下载这 10 条视频，也不需要特定本地目录，才能使用镜头配方。精确复刻或确认音效时，再检查当前任务可用的素材。

参考记录来自 2026-09-27 的取样研究，链接与媒体版本可能变化。视觉时间段用于定位，不代表原作逐帧参数；信号周期只是候选，未被试听确认为音乐主拍。研究也没有确认这些原作用 Remotion 制作。公开文字观察与重建建议，目的是学习方法并使用自己的内容创作。

## 安装到 Codex

仓库根目录就是 skill 目录，`SKILL.md` 无需再嵌套一层。以 macOS / Linux 的用户级安装为例：

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/JudgePeach/remotion-shotflow.git \
  "$HOME/.agents/skills/remotion-shotflow"
```

项目级安装时，将完整仓库目录放到 `<项目>/.agents/skills/remotion-shotflow/`。Windows 可将其放到用户目录下的 `.agents/skills/remotion-shotflow/`。已有同名 skill 时先检查内容，避免覆盖本地修改或重复安装。

Codex 支持用户级 `~/.agents/skills` 和项目级 `.agents/skills`；新增技能通常会自动发现，未出现时重启客户端。参见 [官方技能文档](https://learn.chatgpt.com/docs/build-skills)。其他兼容 Agent Skills 的客户端可按各自的技能目录安装；本仓库未逐一验证这些客户端。

仅使用文字工作流与镜头配方，无需安装 Python 或 FFmpeg。编写 Remotion 代码时，配合当前可用的官方 `remotion-best-practices` 技能和工程锁定版本；本技能补充镜头设计，不替代官方 API 规则。

## 开始使用

```text
使用 $remotion-shotflow，把我的产品界面做成 15 秒介绍片。
重点展示“导入内容 → 自动整理 → 查看结果”，先在 Studio 预览。
```

```text
使用 $remotion-shotflow，学习 Washu 参考的 7.6–10 秒。
我只需要一个分镜方案：用自己的四张内容卡，实现汇聚、进入输入框和归位。
```

```text
使用 $remotion-shotflow，检查我提供的本地视频与音乐。
区分信号测得的候选、实际试听确认的拍点和新设计的音效位置。
```

技能可以只交付分镜、只检查一镜或直接改已有工程。制作视频时先预览；最终渲染或导出按用户的明确请求执行。示例 [8 秒分镜](assets/shot-plan.example.md) 与 [cue 表](assets/cue-sheet.example.json) 是原创练习设计，示例音效文件没有随包提供。

## 可选本地工具

三个脚本只读取显式提供的本地输入、写入指定输出；不会下载素材、上传数据、安装依赖或改写源媒体。媒体读取限制为本地 `file,pipe` 协议。

| 工具 | 用途 | 依赖 |
|---|---|---|
| [sample_frames.py](scripts/sample_frames.py) | 按实际解码 PTS 取最近帧，生成带时间标签的联系表 | Python、Pillow、FFmpeg / FFprobe |
| [analyze_audio.py](scripts/analyze_audio.py) | 检查原声道、声音突起与周期候选，记录时间基准 | Python、NumPy、SciPy、FFmpeg / FFprobe；绘图另需 Matplotlib |
| [compile_cues.py](scripts/compile_cues.py) | 把音效内部锚点换算为成片帧位置 | Python 标准库 |

统一建议 **Python 3.11+**。安装 Python 依赖可使用独立虚拟环境；FFmpeg / FFprobe 需另行安装并位于 `PATH`。

```bash
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 使用：.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# 只有需要音轨图表时才安装
python -m pip install -r requirements-plot.txt
```

从仓库目录运行：

```bash
# 编译随包 cue 示例；不需要音效文件，不代表素材已可播放
python scripts/compile_cues.py \
  --input assets/cue-sheet.example.json --out output/cue-frames.json

# 对自己提供的视频取样
python scripts/sample_frames.py \
  --input /path/to/reference.mp4 --out output/frames-01 \
  --start 1 --end 3 --step 0.2

# 生成待试听核对的音轨候选
python scripts/analyze_audio.py \
  --input /path/to/reference.mp4 --out output/audio-01
```

媒体工具要求输出目录尚不存在；cue 编译默认拒绝覆盖已有输出。音频工具的退出码 0 不等于已确认节拍，要继续检查 JSON 的 `status`。候选 cue 默认拒绝编译；需要草稿时显式使用 `--include-candidates`，输出仍保留候选身份。工具结果会记录输入的本地路径，分享生成的研究资料前检查这些元数据。

详细用法：[抽帧](references/frame-sampling-cli.md) · [音轨测量](references/audio-analysis-cli.md) · [音画工作流](references/audio-sync.md) · [验收](references/render-qa.md)。这些工具面向短参考片，分析会读取完整媒体；长片请先制定分段与时间映射方案。

## 验证与贡献

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

测试在临时目录生成自己的素材，检查实际时间映射、原声道状态、候选身份、输入保护与输出拒绝覆盖，不下载第三方视频。媒体测试需要上表中的依赖；缺失时会跳过。GitHub Actions 使用 Ubuntu 与 Python 3.11 / 3.13 运行检查；实际远端结果以 Actions 记录为准。Windows 尚未实际验收。

欢迎补充有出处的镜头观察、改进小工具和修正文档。提交规则与最小复现要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证与来源

本仓库的技能说明、分析脚本和原创示例采用 [MIT License](LICENSE)。第三方原作、商标、品牌素材、声音与独立安装的依赖不在本仓库的授权范围内，各自权利与许可证保持独立。来源和分发范围见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本项目是社区技能，与 Remotion、OpenAI 及参考作品作者没有官方关联。
