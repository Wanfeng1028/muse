# X 帖子索引：@e1genqq motion studio 清单（2026-10-31）

- 作者：@e1genqq（X）
- 链接：https://x.com/e1genqq/status/2116270712390316375
- 日期：2026-10-31（帖子发布日）
- 主题：作者整理的一份 motion studio 清单，共 20 个开源项目，宣称面向 Opus 5.5 的免费 GitHub skills，覆盖动画、仿真、3D、音频、导出全流程。
- 归档方式：仓库原件浅克隆（--depth 1，已剥离 .git）进 muse-repo/motion-studio/；超大仓库改为索引条目（仅 LICENSE 原文 + 说明）；另有 2 项此前已存于仓库根目录，本轮只核验未重克隆。
- 许可证口径：下表许可证一律以各仓库 LICENSE/COPYING 原文为准，不凭印象写。注意两处与帖子“100% 免费”说法不一致的地方：remotion 用的是自定义两档许可证（不是通用开源许可）；remotion-dev/skills 仓库内未附 LICENSE 文件。
- 单文件大于 50MB 的排除清单：无（12 个全量克隆中未发现大于 50MB 的单文件）。
- 上游 HEAD 均为 2026-11-01 核查的 ls-remote 值。

## 20 项清单

| 序号 | 仓库 | 一句话作用 | 许可证（原文核查） | 归档状态 | 上游 HEAD | Stars |
|---|---|---|---|---|---|---|
| 01 | remotion-dev/remotion | React 视频引擎，用代码做视频 | 自定义 Remotion License（个人与小公司免费，较大规模营利组织需公司许可） | 索引 | fe9ffaa7b349 | 69518 |
| 02 | remotion-dev/skills | Remotion 官方视频 skills（Agent skills） | 仓库内未附 LICENSE（API 亦返回无） | 已存（既有，muse-repo/remotion-skills/） | 30d4553ecd46 | 6000 |
| 03 | juliangarnier/anime | 动画库，时间轴编排 | MIT | 全量 | 01b81be1df68 | 74139 |
| 04 | motiondivision/motion | UI 动画与布局过渡库 | MIT | 索引 | 7415b6cd14df | 34744 |
| 05 | ManimCommunity/manim | Python 动画引擎，做动画图表与公式解说 | MIT | 全量 | 16ea443e2a5f | 42088 |
| 06 | airbnb/lottie-web | 轻量矢量动画播放（Lottie） | MIT | 全量 | bede03d25d23 | 32317 |
| 07 | ahujasid/mcp-for-blender | 让 Claude 建改 Blender 3D 场景的 MCP 插件 | MIT | 全量 | 992233bb2589 | 32935 |
| 08 | mrdoob/three.js | JavaScript 3D 库 | MIT | 索引 | fa01dd6ad164 | 117323 |
| 09 | gkjohnson/three-gpu-pathtracer | three.js 的 GPU 路径追踪（真实光照反射） | MIT | 全量 | 4905be358041 | 1954 |
| 10 | jrouwe/JoltPhysics | 物理引擎（碰撞、刚体、柔体） | MIT | 全量 | ea4599d5044d | 12069 |
| 11 | pmndrs/postprocessing | three.js 后期特效（辉光、景深、调色） | Zlib | 全量 | 9cf03cff2661 | 2921 |
| 12 | Alchemist0823/three.quarks | three.js 粒子与拖尾 VFX | MIT | 全量 | de7c207f791c | 未查到 |
| 13 | cocopon/tweakpane | 场景参数实时调节面板 | MIT | 全量 | 50a18c3dba67 | 4630 |
| 14 | Comfy-Org/ComfyUI | 节点式生成工作流（生图） | GPL-3.0 | 索引 | 6d352802d8f8 | 144388 |
| 15 | QwenAudio/CosyVoice | 多语言配音模型 | Apache-2.0 | 全量 | 074ca6dc9e80 | 24221 |
| 16 | librosa/librosa | Python 音频分析（节拍检测等） | ISC | 全量 | 4ffed287f904 | 8745 |
| 17 | m-bain/whisperX | 语音转字幕，词级时间戳 | BSD 2-Clause | 已存（既有，muse-repo/whisperX/） | 5d3678b85356 | 24987 |
| 18 | obsproject/obs-studio | 录屏与推流软件 | GPL-2.0 | 索引 | 65c320b46e1a | 78724 |
| 19 | mifi/lossless-cut | 免重编码快剪工具 | GPL-2.0 | 全量 | 6fc47dd4cc81 | 45548 |
| 20 | FFmpeg/FFmpeg | 编解码全家桶，编码交付 | LGPL-2.1+（默认），可选部分 GPL-2+ | 索引 | e2740a3e0daa | 66177 |

## 归档位置

- 全量 12 项：muse-repo/motion-studio/anime、manim、lottie-web、mcp-for-blender、three-gpu-pathtracer、JoltPhysics、postprocessing、three.quarks、tweakpane、CosyVoice、librosa、lossless-cut（.git 已剥离，LICENSE 原文保留）。
- 索引 6 项：muse-repo/motion-studio/index/remotion、three-js、ComfyUI、obs-studio、FFmpeg、motion（LICENSE 原文 + NOTE.md 说明未全量原因）。
- 既有 2 项：muse-repo/remotion-skills/（02）、muse-repo/whisperX/（17），本轮核验存在且 LICENSE 状态如上表，未重克隆。
- 评估文档：muse-repo/motion-studio/EVALUATION.md（逐项评估能否用在紫微星盘小程序前端）。

## 备注

- 本索引只记录帖子指向的仓库与核查事实，不复制帖子正文。
- 本轮只归档与评估，不改小程序任何代码。
