# 川云添 · 自动剪辑 Pro — 使用说明

[返回 README](../README.md) · [Skill 入口](../SKILL.md) · [排障](TROUBLESHOOTING.md)

## 安装与运行目录

环境：Node.js 24+（推荐 24 LTS）、Git、FFmpeg、ffprobe。以下命令在完整仓库根目录运行：

```bash
git clone https://github.com/cytxnyu/chuanyuntian-auto-edit-pro.git
cd chuanyuntian-auto-edit-pro
npm ci
```

在 Codex 中安装时将完整仓库放到 `$HOME/.agents/skills/auto-edit-pro`，执行 `npm ci` 后新开会话，调用 `$auto-edit-pro`。不要只复制入口文档。

也可让 `$skill-installer` 从本仓库根目录安装，随后进入实际安装目录执行 `npm ci`。不同宿主和旧版本的目录可能不同，以所在环境为准；参见 [Codex 官方 Skills 文档](https://learn.chatgpt.com/docs/build-skills)。

## 输入与边界

- 合成模式：已完成基础剪辑的视频 + 与它完全对应的 UTF-8 SRT。
- 透明叠加模式：至少提供 SRT，并锁定目标尺寸和帧率。
- 选择字幕模式：`burned-in`、`generated` 或 `none`。
- 有真实证据卡时，提供可读取的图片和来源；人物深度穿插需同步透明人物帧序列。
- 缺少 SRT 时先查找，提出转写和时间轴校对方案，等用户确认后再转写；此 CLI 不内置转写器。

本 Skill 不负责删除重复台词、口误、漏读、气口和长停顿。视频剪辑修改后应重新导出并校对 SRT。代码中的媒体代理用于浏览器兼容，不是重新剪辑；音频可能重新编码。

## 输出模式与字幕

| 参数 | 用法 |
|---|---|
| `--output-mode composite` | 默认推荐。必须同时提供 `--video` 和 `--srt`，最终输出 `renders/packaged.mp4` |
| `--output-mode overlay` | Remotion 输出无音轨的 ProRes 4444 Alpha `renders/overlay.mov`，可不提供视频 |
| `--captions burned-in` | 原视频已有固定字幕，保留它且不增加重复字幕层 |
| `--captions generated` | 用已校对 SRT 生成字幕，不是识别语音 |
| `--captions none` | 不生成字幕层，SRT 仍用于语义与时间规划 |

合成模式采用探测到的源视频规格；`--width`、`--height`、`--fps` 是 **SRT-only 模式**的画布参数，不是合成模式的强制转码开关。需要改变源视频规格时，先另外确认转码与时间轴策略，再以固定版本重新开始 Gate A。

## Gate A — 检查与方案

```bash
npm run package-video -- --video "input.mp4" --srt "input.srt" --out "run" --renderer remotion --captions burned-in --output-mode composite
```

输出 `BRIEF.md`、`SOURCE_PROBE.json`、`STORYBOARD.md`、`storyboard.json` 和 `input-manifest.json`。逐段检查台词、结构、组件、动作、人物遮挡、字幕接棒和素材需求。**必须收到本次 Gate A 方案的明确批准**再继续；其他项目的批准不适用。

## Gate B → Gate C — 输入准备与审核帧

```bash
npm run package-video -- --video "input.mp4" --srt "input.srt" --out "run" --renderer remotion --captions burned-in --output-mode composite --approve-gate-a --approve-gate-b
```

先准备 `public/`、`props.json` 等工程输入，必要时生成不改顺序的 H.264/AAC 制作代理；随后**自动进入 Gate C，不再请求 B 到 C 的批准**。生成 `gate-c-review/` 审核静帧、联系表和 `GATE_C_REPORT.json`，不生成最终视频。

A/B 标记共同记录已批准方案的执行状态。旧 `--approve-gate-c` 参数仍可识别，但不必传。只有明确要求“本次只准备输入”时才附加 `--gate-b-only`。

### Gate C 人工复核

核对实际帧的有意遮挡、手势位置、透明人物层边缘、密度、裁切、对比、语义和字幕/关键词连续性。静帧正常并不等于运动正常，必要时补看时间轴与短样段。任何失败或未检查项都先处理，再请求 Gate D。

**当前通用选择器要求八种不同语义结构，各取节拍 72% 的稳定帧。** 对结构较少的短片会报错，不应为通过检查扩写原片或强行套八种结构。应在 Gate A 说明冲突并另行约定工程级审片策略；本发布版没有通用短片自动豁免。

## Gate D — 最终导出

只有 Gate C 审核通过，且用户明确批准 Gate D，才运行：

```bash
npm run package-video -- --video "input.mp4" --srt "input.srt" --out "run" --renderer remotion --captions burned-in --output-mode composite --approve-gate-a --approve-gate-b --approve-gate-d --render
```

输出 `renders/packaged.mp4`、最终代表帧、联系表和 `RENDER_MANIFEST.json`。验证参数、完整解码、黑帧和 SHA-256；发生编码时不把声音内容保留描述为二进制无损复制。交付时保留源视频/SRT、仓库、`storyboard.json`、`props.json` 和 `public/`，以便复现修改。

## SRT-only 透明输出

先以目标工程规格做 Gate A：

```bash
npm run package-video -- --srt "input.srt" --out "run-overlay" --renderer remotion --captions burned-in --output-mode overlay --width 1920 --height 1080 --fps 30
```

随后沿用同样的 Gate A 批准 → B 自动 C → Gate D 批准流程，在对应阶段添加相同批准标记。`burned-in` 表示外部底片已有字幕、不重复生成；需要叠加层包含字幕时改为 `generated`。

最终透明 MOV 必须为 ProRes 4444、含 Alpha 像素格式且无音轨；检查采样 Alpha 变化与全片解码。把它与底片在外部剪辑软件中从同一起点叠加，不改变速度、画布或时间偏移。仅有 SRT 时不能据此验证真实脸部、手势和字幕位置。

## 人物互动与证据素材

整个画面均可作为舞台。位置、大小、透明度和人物遮挡应有语义目的，入口、停留、退场与可读时间明确；不是强制全屏遮脸。

真实手势交互先观察源帧并记录时间；深度交叉使用已对齐的透明人物帧序列，通过 `--subject-frames` 提供，具体字段见 [全屏舞台](../references/whole-screen-stage.md)。仓库没有自动抠像或手跟踪流程，不可拿半透明原片冒充抠像。

`evidence-panel` 需要实际批准的图片、可读标签和来源。缺少证据时保留说话人的归属，用论点或示意表达；不得生成假截图、数字、评价或产品操作结果。

## 可选 HyperFrames

HyperFrames 仅支持 legacy 布局与风格，混合风格全屏舞台和 Gate C/D 使用 Remotion。需要可选项目时，先在独立输出目录生成 HyperFrames 的 legacy Gate A 方案；本次方案获批并明确只准备输入后，再执行第二条命令：

```bash
npm run package-video -- --video "input.mp4" --srt "input.srt" --out "run-hyperframes" --renderer hyperframes --style-mix legacy --captions burned-in --output-mode composite
# 本次 Gate A 已获批准后；继续保存方案，不重复传入风格覆盖参数
npm run package-video -- --video "input.mp4" --srt "input.srt" --out "run-hyperframes" --renderer hyperframes --captions burned-in --output-mode composite --approve-gate-a --approve-gate-b --gate-b-only
npx hyperframes@0.7.99 lint ./run-hyperframes/hyperframes
npx hyperframes@0.7.99 check ./run-hyperframes/hyperframes --snapshots
```

该输出是可编辑项目，不等于最终视频。切换渲染器时新建输出目录并重新检查方案，避免复用不兼容的舞台配置。

## 可复现视觉风格

新方案默认在 71 种已登记风格中执行 `seeded-shuffle`，语义结构独立按内容确定。用 `npm run list:styles` 浏览目录，或用 `npm run list:styles -- --category components --pool` 获取组件类子池。

新任务 Gate A 可加入 `--style-pool waves,metallic-paint,grid-scan` 限定风格池，或以 `--style-mix legacy` 保留旧审美。实际种子、池和节拍分配存入 storyboard，继续执行同一 RUN 时不重抽；短片不为覆盖整个池而新增无意义节拍。

说明与字段：[视觉风格混合](../references/visual-style-mixing.md) · [扩展目录](../references/react-bits-catalog.md)。

## 常用运行参数

- `--out`：保存此任务的方案、工程输入与输出；不同任务使用不同目录。
- `--storyboard`：复用已审定分镜文件；仍检查源参数与输入哈希。
- `--concurrency`：Remotion 并发数 1–16，默认 2。
- `--timeout`：Remotion 超时配置，毫秒整数，最少 7000，默认 120000。

完整约束：[Gate 合同](../references/gates.md) · [视觉结构](../references/visual-structures.md) · [视觉质检](../references/visual-quality-gates.md)。
