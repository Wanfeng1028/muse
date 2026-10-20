# 合成示例

[返回 README](../README.md) · [使用说明](USAGE.md)

本公开发布版仅保留 `synthetic-horizontal`，用于验证安装、媒体探测、SRT 解析和 Gate A。它不含真人、私人口播、聊天截图或商业联系方式，也不冒充真实剪辑效果。

## 生成测试素材并运行 Gate A

在安装过依赖的仓库根目录运行：

```bash
npm run make:synthetic
npm run example:synthetic
```

第一条命令使用 FFmpeg 本地生成：

- `examples/synthetic-horizontal/input.mp4`：4 秒、1920×1080、30fps、H.264 测试图案，搭配 440Hz 正弦音。
- 字幕已经随仓库提供：[input.srt](../examples/synthetic-horizontal/input.srt)，共两条合成文本，时间范围 0–4 秒。

**测试音不含人声，SRT 不是语音转写。** 不用此素材检验语音识别、人物抠像、手势匹配或真实字幕精度。

第二条命令不包含批准标记，只执行 Gate A，输出目录是 `examples/synthetic-horizontal/run/`。预期出现：

- `BRIEF.md`、`SOURCE_PROBE.json`；
- `STORYBOARD.md`、`storyboard.json`；
- `input-manifest.json`，包含输入哈希与媒体规格。

此步骤不会生成最终 `packaged.mp4`。测试 MP4 和运行目录为本地产物，不随源码发布；重新执行 `make:synthetic` 会覆盖该测试文件。

## 为什么不直接演示完整渲染

4 秒测试只有两条字幕，不适合强行安排八种语义结构。当前通用 Gate C 选择器要求八种不同结构，因此该 fixture 的用途明确限定为 **Gate A 安装自测**。如果要演示完整包装，请提供合适的真实口播与校对 SRT，先审批方案；若短片有效结构不足，先约定工程级审核策略，不要擅自增加台词或取消审核。

## 用自己的素材开始

参考 [README 中的可复制提示词](../README.md)。准备同一剪辑版本的视频和 SRT；没有 SRT 时先确认转写与校对方案。使用新的输出目录，按照 Gate A → B 自动 C → Gate D 的批准流程工作。

如需分享自己的效果，请先完成真实输出验收，再公开必要的截图、命令、媒体参数和输出哈希；不要把未渲染工程或合成测试图称为真实成片案例。

## 可选合成风格演示

只有明确要求查看组件演示时才运行 `npm run demo:styles -- --out DEMO_DIR`。它生成三个既有组件 MP4、静帧与画廊，只覆盖原始四种风格，不是 71 项全览，也不代表真人视频获批。查看全部风格名称使用 `npm run list:styles`；目录见[视觉风格混合](../references/visual-style-mixing.md)。
