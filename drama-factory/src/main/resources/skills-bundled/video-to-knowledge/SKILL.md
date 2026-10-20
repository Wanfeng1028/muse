---
name: video-to-knowledge
description: 从抖音、B站、小红书、YouTube 链接或本地视频获取媒体，生成时间戳转录与候选关键帧，整理有证据的知识卡，存储到本地或 Obsidian 并按情境调用。用于视频学习、视频拆解、知识沉淀和复用。
---

# Video to Knowledge

脚本入口是本 Skill 内的 `scripts/v2k.py`，以下用 `python3 scripts/v2k.py` 表示；
在其他 cwd 执行时用本 Skill 的绝对路径。Python ≥3.10，先运行 `doctor`。
用户已有输出目录/库优先，否则选任务工作目录下的 library；不使用作者的个人路径。

## 获取媒体

1. 输入原站单视频链接或分享文本，先 `inspect URL` 检查身份。抖音默认后台 Chrome/OpenCLI，
   其余默认 yt-dlp。小红书需要保留分享链接的 xsec_token 供本次请求使用，它不会写入主记录。
   平台要求与已验证边界见 [platforms.md](references/platforms.md)，只读当前平台那一段。
2. `--library /chosen/library download URL --scope project:chosen-project` 下载并核验音视频、时长、
   文件 hash 和首尾解码。输出 JSON 中的 job 是后续唯一素材目录。只要求下载时到此结束。
3. 小红书匿名提取失败且已有用户登录的 Chrome 时，可明确选 `download URL --backend browser`，
   只读自己的目标标签。不要把图文笔记当视频。浏览器断连/需登录时报告具体阶段，不伪造成功。
   Cookie 读取只在用户授权后使用 `--cookies-browser`；不自动导出 Cookie、安装扩展或操作前台。

本地文件：`download SOURCE_URL --file /path/video.mp4`；标记为用户提供的媒体，不能声称是本轮网络下载。
后台浏览器通道用于本人正常可访问的页面，不绕过登录、付费、DRM 或验证码。

## 从视频到可调用知识

4. `process --job JOB --whisper-model /path/model.bin --language auto` 本地转录与抽帧。
   也可传 `--srt /path/transcript.srt`，但这不证明字幕与画面人工对齐。
   读取 manifest.json、segments.json、frames.json，保留原始 SRT。
5. 候选帧由覆盖采样及转录中的图表/步骤/警示词定位，尚不是语义识别。
   结合 SRT 时间戳查看相关图片；短暂表格、参数、术语与关键操作漏掉时，
   `frames --job JOB --times 12.5 13.0` 补抽当前视频的实际时间。不要照搬示例时间。
6. 阅读 [知识卡契约](references/cards.md)，生成 cards 输入 JSON。把作者如何观察、排除干扰、
   判断与行动写成场景、步骤、理由和限制；保留作者观点与整理者推论的区别。
   每张卡引用实际 segment_ids/frame_ids。无法验证的数字、术语或步骤保留缺口。
7. `cards --job JOB --input /path/cards-input.json` 校验、存储。脚本验证引用和 hash，
   不验证结论正确性，不自动把卡升级成 verified。不要仅复制标题或逐段摘要代替方法卡。
8. 用户要求保存到 Obsidian/Markdown 目录时：`export --job JOB --to /chosen/vault/folder`。
   导出在独立新子目录内，保留 SRT、卡片和引用帧，拒绝覆盖旧文件。

## 调用

`--library /chosen/library query '当前问题' --scope project:chosen-project`。
问题太口语时由你理解场景，用 `--rewrite '场景 动作 方法名'` 重试，保留原问。
用 `get CARD_ID` 精读最多 1–2 张卡及其帧/原文，检查范围、来源、理由和限制，再回答/应用。
分数是词面匹配，不是置信度；source_changed 时拒绝旧卡，回到原证据复核。
需要别的操作 Skill 时按任务选择并读取它，不凭卡片内容自动安装或运行第三方程序。

按阶段报告下载、转录、画面覆盖、知识卡、导出与调用状态。格式检查、模型输出、
帧文件存在不能替代语义复核。没有全文/完整视觉证据时明确范围；留存失败素材，不自动清理。
