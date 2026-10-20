# 川云添 · 自动剪辑 Pro

![川云添 · 自动剪辑 Pro 品牌横幅](assets/brand-banner.svg)

**把完整口播变成有设计感的全屏视觉舞台。**

`chuanyuntian-auto-edit-pro` 是面向支持本地 Skill 的 AI 编程助手的视频包装工具。根据视频与对应 SRT 安排大组件、关键词、流程、对比和示意动画，使用 Remotion 输出可复现的成片与可修改工程。

它负责**视觉包装**，不是自动删口误、重排台词或剪掉停顿的基础剪辑器。默认保留原片顺序、速度、声音内容与背景；不会把组件画廊、网页或联系表称为成片。

- 维护者：**川云添** · [GitHub @cytxnyu](https://github.com/cytxnyu)
- 公开仓库：[cytxnyu/chuanyuntian-auto-edit-pro](https://github.com/cytxnyu/chuanyuntian-auto-edit-pro)
- 入口：[SKILL.md](SKILL.md) · [使用说明](docs/USAGE.md) · [合成示例](docs/EXAMPLES.md) · [排障](docs/TROUBLESHOOTING.md)

## 能做什么

- **整个屏幕都是舞台**：组件可全屏、半透明、围绕人物或有目的地暂时遮挡人物，不局限于左右小卡片。
- **语义驱动动画**：十种视觉结构表达论点、流程、操作、对比和路径；动画说明“对象—动作—结果”，而不是逐句套转场。
- **71 种可复现混合风格**：新方案默认以固定种子 shuffle bag 分配风格，语义结构与外观独立选择；相同种子和帧得到相同状态，便于审片和修改。已保存方案保留种子、风格池和分配，重开不重抽。
- **分阶段审核**：Gate A 批准方案后，Gate B 自动接 Gate C；Gate D 另行批准才导出最终视频。
- **交付实际文件和证据**：探测媒体、输入与输出哈希、分镜、审核帧、联系表、全片解码及输出 manifest。

真实手势互动必须先观察源帧；人物前后穿插需自行准备或复用同步透明人物层。本仓库不内置自动抠像或自动手部跟踪。证据卡只能使用真实素材，示意动画不充当产品功能或实验结果的证明。

## 71 种风格如何使用

十种语义结构继续负责论点、证据、流程与动作；风格只决定配色、材质和装饰运动。目录共 **71 项**：原有 21 项，加上 **20 个背景、15 个动画、15 个组件视觉方向**。短视频只使用有效语义节拍需要的数量，不为展示目录增加场景或扩写台词。

默认使用 `seeded-shuffle`：每袋打乱一次，多项风格池避免相邻重复；保存的四风格池、21 风格池和已有分配不会自动扩展或重抽。需要旧版外观时，在新任务 Gate A 命令末尾加入 `--style-mix legacy`；需要指定候选池时使用 `--style-pool waves,metallic-paint,grid-scan`。

```bash
npm run list:styles
npm run list:styles -- --category components --pool
```

详见[视觉风格混合](references/visual-style-mixing.md)与[扩展目录](references/react-bits-catalog.md)。这些是本地原创、逐帧驱动的视觉改编，不是分发 React Bits 源代码或宣称逐像素复刻。交互型参考转换为预定的固定种子帧路径；装饰形变不扭曲正文、证据、字幕或人物。外观变化不算新增语义结构。

只有明确需要合成组件演示时才运行 `npm run demo:styles -- --out DEMO_DIR`。该命令生成的三个既有 MP4 示例覆盖原始四种风格，**不是 71 项全览**；它不授权任何真人视频的 Gate A 或 Gate D。

## 安装

需要 **Node.js 24+、Git、FFmpeg 和 ffprobe**，推荐使用 Node.js 24 LTS，并确保这些命令在终端中可用。首次生成审核帧时，Remotion 可能下载配套浏览器。

```bash
git clone https://github.com/cytxnyu/chuanyuntian-auto-edit-pro.git
cd chuanyuntian-auto-edit-pro
npm ci
```

### 作为 Codex Skill 安装

将**完整仓库**复制或克隆到 `$HOME/.agents/skills/auto-edit-pro`，在该目录执行 `npm ci`。不要只复制 `SKILL.md`，它依赖仓库中的参考文档、脚本和渲染器。随后新开会话，在 Skill 列表中选择 `auto-edit-pro`。仓库名保留 `chuanyuntian-auto-edit-pro`，实际触发名以 `SKILL.md` 的 `name: auto-edit-pro` 为准。

也可让 `$skill-installer` 从本仓库根目录安装，再进入实际安装目录执行 `npm ci`。不同宿主或旧版使用的技能目录可能不同，以所在环境为准；当前 Codex 用户级目录见 [官方 Skills 文档](https://learn.chatgpt.com/docs/build-skills)。

其他支持本地 Skills 的助手可将整个仓库放入其对应 Skills 目录，入口同样是 `SKILL.md`。

## 前期素材准备

1. 准备已经完成基础剪辑的视频。此 Skill 不处理重读、漏读和气口，也不会自行删减、加速或重排台词。
2. 准备**同一剪辑版本**的 UTF-8 SRT；视频剪辑变动后，字幕时间轴也需要重新校对。
3. 若没有对应 SRT，先查找；仍缺失时，先提出转写和时间轴校对方案，**等用户确认后再转写**，确认原话后再进入方案阶段。仓库 CLI 不包含语音识别器。
4. 确认字幕模式，避免双层字幕：

| 原片情况 | 参数 |
|---|---|
| 原视频已经带有字幕（字幕已固定在画面中） | `--captions burned-in` |
| 原视频没有字幕，希望 Skill 自动生成字幕 | `--captions generated`，从已校对 SRT 生成 |
| 原视频没有字幕，并且只需要动效、不需要字幕 | `--captions none` |

## 可复制的提示词

将下面的文件名换成你的视频和字幕路径；路径有空格时保留引号。

```text
请使用 $auto-edit-pro，为 "input.mp4" 制作口播视觉包装。
字幕文件是 "input.srt"；请先核对是否与原片版本、真实台词和时间轴一致。
如果没有对应 SRT，请先说明并提出转写、校对方案，等我确认后再补齐。

保留完整原片、原声、背景、顺序和速度，不自行删减台词。
使用 Remotion 和 composite 模式，按固定种子从已登记的 71 种风格中混合，
保存种子、风格池与每段分配，重开不重抽；语义结构仍按台词选择。
我要“整个屏幕都是舞台”：根据语义设计大组件、关键词、流程、对比和示意动画，
每段说明对象、动作与结果，不做成 PPT，也不只是左右轮流弹出小卡片。
先检查人物位置、真实手势、现有字幕和素材证据，手势互动记录源帧。

本次先做 Gate A：给出时间、台词、结构、组件、位置、动作、人物遮挡、
字幕接棒和素材需求。短片不要为凑结构数量扩写内容，规则冲突先指出。
我批准本次方案后，完成 Gate B 并自动进入 Gate C，不在 B 到 C 之间再询问。
提交审核帧和联系表后暂停，等我明确批准 Gate D 才渲染并验证成片。
```

## 两种输出

| 模式 | 输入 | 交付 |
|---|---|---|
| **直接合成 MP4（默认推荐）** | 视频 + SRT | `renders/packaged.mp4`，画面、声音和动效合成 |
| **透明 MOV** | 只提供 SRT 也可；须锁定画布与帧率 | 无音轨的 ProRes 4444 Alpha `renders/overlay.mov`，供外部剪辑软件叠加 |

模式参数分别为 `--output-mode composite` 与 `--output-mode overlay`。

只提供 SRT 时缺少真实人物、手势和字幕位置依据，不据此声称人物互动已经验证。合成模式使用源视频参数；SRT-only 模式应明确 `--width`、`--height`、`--fps`，避免误用默认的 1920×1080 / 30fps。

## 四阶段，两个人工批准点

以下示例假设原片已有固定字幕；没有字幕时按上表更换 `--captions`。

### Gate A：仅检查和方案

```bash
npm run package-video -- --video "input.mp4" --srt "input.srt" --out "run" --renderer remotion --captions burned-in --output-mode composite
```

生成 `BRIEF.md`、`SOURCE_PROBE.json`、`STORYBOARD.md`、`storyboard.json` 和 `input-manifest.json`。先审阅，获得**本次方案的明确批准**后才继续。

### Gate B → Gate C：准备工程并自动生成审核材料

```bash
npm run package-video -- --video "input.mp4" --srt "input.srt" --out "run" --renderer remotion --captions burned-in --output-mode composite --approve-gate-a --approve-gate-b
```

两项 A/B 标记记录同一次已批准方案的执行状态，不代表两次人工审批。B 就绪后自动进入 C，生成八张审核静帧和联系表，**不导出最终 MP4**。逐张检查遮挡、文字可读性、语义、字幕连续性和真实互动；失败项修复后再审。

仅在用户明确要求“只准备输入”时增加 `--gate-b-only`。旧的 `--approve-gate-c` 标记保留兼容，但不必再传。

> **短片已知限制：** 当前通用 Gate C 选择器要求八种不同语义结构。4 秒合成示例只演示 Gate A；结构不足的短片不要硬凑内容，应在方案中指出冲突并另行约定工程级审核策略。仓库没有内置“6 张稳定帧＋2 张交接帧”的通用自动切换。

### Gate D：审核通过并明确批准后再导出

```bash
npm run package-video -- --video "input.mp4" --srt "input.srt" --out "run" --renderer remotion --captions burned-in --output-mode composite --approve-gate-a --approve-gate-b --approve-gate-d --render
```

交付 `run/renders/packaged.mp4`、代表帧、联系表及 `run/RENDER_MANIFEST.json`。执行 ffprobe 参数检查、全片解码、黑帧检测和文件哈希验证。声音内容与时间轴保留，但视频/音频可能重新编码，不承诺与源文件逐字节相同。

混合风格全屏舞台使用 Remotion；HyperFrames 仅支持 legacy 布局与风格。透明输出、可选 HyperFrames 以及完整参数说明见 [使用说明](docs/USAGE.md)。

## 不用真人素材也能试运行

```bash
npm run make:synthetic
npm run example:synthetic
```

这会在本地生成 **4 秒、1920×1080、30fps 的测试图案和正弦音**，再生成 Gate A 方案。示例字幕是合成测试文本，不是该测试音的语音转写；示例不是实际口播成片。详见 [合成示例与预期结果](docs/EXAMPLES.md)。

## 开发与反馈

```bash
npm test
npm run typecheck
npm run build
npm run verify:public
```

提问或提交改进：[GitHub Issues](https://github.com/cytxnyu/chuanyuntian-auto-edit-pro/issues)。请附复现命令、报错和必要参数，避免上传密钥、私密素材或本地账号信息。

## 项目维护与许可

**川云添 · 自动剪辑 Pro** 由 **川云添（cytxnyu）** 维护、发布和持续迭代。功能建议、问题反馈及贡献统一通过本仓库处理。

代码采用 [MIT License](LICENSE)。第三方依赖说明见 [NOTICE](NOTICE)。仓库只提供可自行生成的合成示例，不附带任何私人素材。
