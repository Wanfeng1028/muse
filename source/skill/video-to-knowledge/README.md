# Video to Knowledge Skill

An evidence-linked Agent Skill for Douyin, Bilibili, Xiaohongshu and YouTube.

把视频变成能够按情境调用的知识：来源 → 下载核验 → 时间戳转录 → 候选关键帧 →
方法/知识卡 → 本地或 Obsidian 存储 → 按需检索与应用。

这是一个可独立克隆的 Skill 仓库。处理和检索脚本使用 Python 标准库；知识卡由调用它的 Agent
阅读转录与画面后整理，不偷偷把视频发给云端模型。不绑定某人的 Obsidian 路径、Agent 品牌或记忆数据库。

## 依赖与安装

- Python ≥3.10。
- ffmpeg/ffprobe：媒体核验、音轨与帧。
- yt-dlp：B站、YouTube、小红书匿名路线；保持当前可用版本。
- Node.js（YouTube JavaScript runtime）及当前 yt-dlp 所需 EJS 组件。
- whisper.cpp 的 whisper-cli 与自己下载的兼容模型；模型无需进仓库。
- 抖音/小红书后台浏览器路线：Chrome、OpenCLI 及其 Browser Bridge，本人正常登录。

仓库可放入 Agent 的 skills 目录，或通过其 Skill 安装机制选择本仓库根目录。
Codex 使用 `~/.codex/skills/video-to-knowledge`；Claude/Hermes 使用各自用户 skills 目录。
也可先克隆到任意目录直接运行：

```sh
python3 scripts/v2k.py doctor
python3 scripts/v2k.py inspect 'https://www.youtube.com/watch?v=jNQXAC9IVRw'
```

可选 `python3 -m pip install .` 安装 `v2k` 命令。依赖程序独立安装；doctor 只检测，不自动安装。
模型优先使用参数或 WHISPER_CPP_MODEL；也可复用
`~/.local/share/whisper.cpp/models/ggml-large-v3-turbo.bin` 下已经存在的本地模型，不自动下载。
Agent 的实际发现/启用规则以平台当前配置为准。

## 一条完整链路

```sh
# 1. 下载，记下输出中的 job 路径
python3 scripts/v2k.py --library ./library download 'https://www.youtube.com/watch?v=jNQXAC9IVRw' --scope project:learning

# 2. 将 job 路径作为变量传入。本地模型路径由使用者提供。
python3 scripts/v2k.py process --job "$VIDEO_JOB" --whisper-model "$WHISPER_CPP_MODEL" --language auto

# 3. Agent 阅读 SRT、segments.json 和 frames.json 中的图片，按契约创建自己的 cards-input.json
python3 scripts/v2k.py cards --job "$VIDEO_JOB" --input ./cards-input.json

# 4. 情境检索与按需读取
python3 scripts/v2k.py --library ./library query '当前遇到的问题' --scope project:learning
python3 scripts/v2k.py --library ./library get "$CARD_ID"

# 5. 可选保存到 Obsidian/Markdown 目录
python3 scripts/v2k.py export --job "$VIDEO_JOB" --to "$KNOWLEDGE_FOLDER"
```

变量必须由使用者根据实际输出设置。也可通过 V2K_LIBRARY 指定库位置。
本地导入：download SOURCE_URL --file PATH；已有字幕：process --srt PATH；
补抽帧：frames --times SECONDS；小红书登录页：download URL --backend browser。
详细流程见 [SKILL.md](SKILL.md)、[平台路由](references/platforms.md)、[知识卡契约](references/cards.md)。

## 存储与可信度

每个 job 独立目录，保留 manifest、公开来源、媒体 hash、原始 SRT、结构化分段、
帧时间/路径/hash、知识卡。身份和下载失败阶段可回查，不用旧文件填成功。
卡片绑定 scope，查询默认只检索同一 scope；按需读取证据，不把全库注入上下文。
证据变更后返回 source_changed 并拒绝旧卡；卡与导出拒绝覆盖已有成果。
写卡前同时核验结构化分段和帧元数据；停用卡不返回正文，导出路径限定在目标子目录。
旧版本没有元数据 hash 的 job 仍可读取已有卡；新增卡或补帧需重新处理一个新 job。

候选帧用时间覆盖及转录提示定位，Agent 仍需看图；不是自动语义识图。
图文帖、无语音、ASR空结果、登录/网络失败和覆盖缺口分别记录，不伪造字幕或完整理解。
分数是词面匹配，口语问题可由 Agent 显式 rewrite；没有内置云端语义服务。

当前以单链接/分享文本或本地文件获取视频，不自动扫描用户收藏库。
公开视频、转录与知识卡默认保留在本地，不随代码开源。仓库中只有合成测试素材结构，
没有个人笔记、Cookie、媒体签名、访问 token、浏览器配置或模型文件。

## 验证和贡献

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

功能检查包含四平台 URL、访问 token 剥离、错误域名/列表拒绝、Cookie显式选择、
合成媒体全链路、时间戳/帧引用、scope 隔离、导出、证据变化拒绝。
真实平台的下载与解析验收单独记录在 [validation.md](docs/validation.md)，
成功一个样本不表示任意视频、账号、地区或未来版本都能运行。

修改平台适配器时提供脱敏的失败阶段和新样本回执。不要提交第三方视频、Cookie或原始网络响应。
这是学习工具；使用自己有权获取和处理的内容，遵守来源平台的访问要求。

## License

MIT。ffmpeg、yt-dlp、whisper.cpp、OpenCLI 各自保持其许可证，不在本仓库打包其二进制、源码或模型。
媒体及创作者内容的权利不由本仓库许可证授予。
