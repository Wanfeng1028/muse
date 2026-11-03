# crypto-kol-video · Claude Skill

**Make 9:16 Chinese crypto / AI explainer videos for Twitter (X) creators — branded with the creator's own avatar and @handle.**

这是一个 Claude Skill，让 Claude 帮 crypto 和 AI 博主把一个选题做成竖屏科普短视频，可用于抖音、视频号和 X：

- 🎬 **代码出片**：Remotion 绘制仿交易界面风格的动画，分镜按口播逐句卡点
- 🧑‍🎤 **博主 IP**：第一次使用时，Claude 会问你的 Twitter 账号，抓取你的头像，放进封面第一帧、开头弹出、全片角标和结尾关注卡
- 🎙️ **配音和字幕**：默认 MiniMax speech-2.8-hd（用你自己的 Key，在你本机生成）；离线 ASR 自动逐句对齐字幕，关键词黄色高亮
- 🎵 **声音**：代码合成的无版权 BGM 和音效，侧链压低，统一到 −14 LUFS
- ✅ **先核实再写**：先查交易所官方规则再写稿，标注估算口径和风险提示

## 安装

**Claude Code / Claude Agent SDK**
```bash
git clone https://github.com/jamesxxx-ai/crypto-kol-video-skill ~/.claude/skills/crypto-kol-video
bash ~/.claude/skills/crypto-kol-video/scripts/setup.sh
```

**Claude.ai / Claude 桌面版（Cowork）**：下载本仓库的 zip，在 设置 → Capabilities → Skills 里上传。

依赖：Node 18+、Python 3.10+、ffmpeg。配音默认用 [MiniMax](https://www.minimaxi.com/) 的 `mmx` CLI，也可以换成任何 TTS 或真人录音。

## 用法

直接对 Claude 说：

> 帮我做一个视频：同样 3 倍做多，杠杆现货和合约谁先爆仓？竖屏，中文字幕和配音

Claude 会依次：
1. 问你的 Twitter 账号，抓取头像请你确认
2. 调研并核实官方规则
3. 写口播稿给你确认
4. 生成配音脚本，由你在本机双击运行
5. 做分镜动画、对齐字幕、混音、渲染，交付成片和封面

## 目录
```
SKILL.md                 Claude 读的工作流说明
references/              版式、分镜套路、核实清单、配音
scripts/kol.py           brand / new / avatar / check / voicekit / timeline / mix
scripts/render.sh        渲染与封装；stills.sh 出静帧总览
template/                Remotion 工程（品牌组件、封面、字幕、进度条、示例分镜）
examples/                示例 video.json（爆仓 vs 止损）
```

## 手动跑一遍示例
```bash
S=~/.claude/skills/crypto-kol-video
python3 $S/scripts/kol.py brand @your_handle                # 抓取头像；失败时加 --avatar 本地图片
python3 $S/scripts/kol.py new ~/kol/demo                    # 新建项目（自带示例稿和示例分镜）
python3 $S/scripts/kol.py voicekit ~/kol/demo ~/kol/demo/voice && bash ~/kol/demo/voice/gen_fill.sh
python3 $S/scripts/kol.py timeline ~/kol/demo ~/kol/demo/voice/out/male-qn-jingying
python3 $S/scripts/kol.py mix ~/kol/demo
bash $S/scripts/render.sh ~/kol/demo demo
```

## 说明
- 头像抓取使用公开服务 `api.fxtwitter.com` 和 `unavatar.io`，失败时可以手动提供图片。
- 视频内容仅供教育科普，不构成投资建议。第三方 Logo 只能使用你有权使用的官方素材。
- Remotion 对部分公司商用有许可要求，见 [remotion.dev/license](https://www.remotion.dev/license)。

MIT License
