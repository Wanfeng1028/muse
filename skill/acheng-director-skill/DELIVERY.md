# Acheng Director 4.3.8｜交付入口

这是导演规范与可运行生产工具包：七个专业子入口、多线叙事与知情合同、表演交接与因果灵动表演、全资产依赖、角色四视图身份基准、4–15秒分段、五模式H3编译、条件视效、红猴子能力整合、归档恢复，以及面向用户的双层交付视图和逐槽位参考图上传助手。八套样例覆盖不同媒介、题材、参考条件和表演机制，不包含付费模型实际出片。

## 先看这里

- [4.3.8资料库接入说明](UPGRADE-4.3.8.md)：36张局部问题卡、31个视觉条目、7种材质适配及原门禁保留。
- [4.3.8功能消费链审查](reports/v4.3.8-functional-review.md)：三条参考链、各工序用途、已修复断点、真实验收与自动化边界。
- [视觉与材质资料手册](references/116-visual-reference-library.md)：按物件/媒介查库并写入资产、关键帧和H3的实际正文。
- [4.3.7 优化说明](UPGRADE-4.3.7.md)：局部专业提问、原规范保留范围、参考图链路修复与验收边界。
- [专业决策入口](references/115-directed-decisions.md)：七模块、32个具体决策场景；只运行当前命中的小节。
- [使用指南](使用指南.md)：如何调用、何时上传参考图、如何复制图像与H3提示词。
- [3.5.4简便操作指南](3.5.4简便操作指南.md)：从解压到首次复制提示词的最短路径。
- [独立提示词交付规则](references/72-standalone-prompt-delivery.md)：GPT Image适配、逐段完整上下文和代号消解。
- [STYLE MOTHER 风格锚定合同](references/62-style-anchor.md)：多资产默认必须使用的母版、用户明确豁免、依赖和验收边界。
- [打戏方向与速度合同](references/40-action-choreography.md)：每镜轴线、速度曲线和慢动作触发规则。
- [人类可读交付视图合同](references/73-human-readable-delivery.md)：V3.0式总控台、段落地图、资产卡、复制区与验收呈现顺序。
- [v3能力迁移与验收边界](reports/v3-capability-trace.md)：原能力如何进入当前规则、数据、输出和检查。
- [v2.1独立提示词修正记录](reports/prompt-delivery-review.md)：上一次修正的历史范围。
- [技能主入口](SKILL.md)：按阶段路由与执行命令。
- [交付完整性门禁](references/94-delivery-integrity.md)：只读范围、反省略、证据和未决项回执；可用 `scripts/delivery_integrity.py` 执行。
- [原始资产审查及修正](references/99-source-audit.md)：源内容差异、架构问题、保留及裁决。
- [红猴子整合合同](references/93-red-monkey-integration.md)：可纳入能力、唯一 owner、触发、冲突裁决与自检。
- [红猴子整合清单](data/red-monkey-integrations.json)：机器可读的纳入／顾问／门禁／拒绝矩阵。
- [统一数据合同](references/90-production-contract.md)：剧本、镜头、A/B/C支路、资产与场记接口。
- [最终包验收](reports/package-acceptance-v4.3.8-final.json)：当前资料路由、生产文件版本、引用映射与适用门分数；旧版报告仅作历史追溯。
- 包校验值：见新 ZIP 同目录的同名 .sha256 文件；包内旧版校验记录只对应它们标明的历史构建。
- [132段实际媒体核验](reports/previs-media-acceptance.json)：逐文件SHA、1920×1080、24fps、96帧、4秒。

## 八套可直接复核的生产案例

| 生产卡 | 数据 | 编译提示词 |
|---|---|---|
| [重工业机甲](examples/01-hollywood-mecha-combat-h3.md) | [14秒完整生产数据](examples/01-mecha.production.json) | [Ref2VA六字段](examples/compiled/mecha/MECHA_SEG01.h3.txt) |
| [文戏对峙](examples/02-dramatic-micro-acting-h3.md) | [20秒、两段10秒](examples/02-drama.production.json) | [第一段](examples/compiled/drama/DRAMA_SEG01.h3.txt)、[第二段](examples/compiled/drama/DRAMA_SEG02.h3.txt) |
| [超巨构神魔对决](examples/03-colossal-scale-combat-h3.md) | [14秒完整生产数据](examples/03-colossal.production.json) | [Ref2VA六字段](examples/compiled/colossal/COLOSSAL_SEG01.h3.txt) |
| [三集八线悬疑](examples/04-serial.production.md) | [180秒、12个独立生成段](examples/04-serial.production.json) | [H3清单](examples/compiled/serial/UPLOAD.md)、[全资产顺序](examples/compiled/images/serial/UPLOAD.md) |
| [非写实纸鹤动作](examples/05-ink.production.md) | [36秒、三段12秒](examples/05-ink.production.json) | [I2VA/FL2VA/L2VA](examples/compiled/ink/UPLOAD.md) |
| [2D动画电话戏](examples/06-animated-phone.md) | [10秒、Ref2VA跨硬切](examples/06-animated-phone.production.json) | [参考图与跨切对白](examples/compiled/animated-phone/UPLOAD.md) |
| [喜剧误会](examples/07-comedy-misunderstanding.md) | [20秒、两段10秒](examples/07-comedy-misunderstanding.production.json) | [夸张节拍与道具反转](examples/compiled/comedy-misunderstanding/UPLOAD.md) |
| [悬疑低声戏](examples/08-suspense-whisper.md) | [10秒、I2VA首帧](examples/08-suspense-whisper.production.json) | [声音先行与延迟倒影](examples/compiled/suspense-whisper/UPLOAD.md) |

灰模PNG只负责构图与动作相位示意，原始人物身份来自生产卡文本；没有把灰模当成电影美术成片。每套卡含完整动作／表演、图像七步提示词、模型提示词和末尾账本。编译输出目录携带其引用图像，移动目录后仍可找到素材。

独立资产图提示词与上传清单：[文戏（无需图）](examples/compiled/images/drama/UPLOAD.md)、[机甲（需构图图）](examples/compiled/images/mecha/UPLOAD.md)、[巨构（需构图图）](examples/compiled/images/colossal/UPLOAD.md)。默认展示资产名请看各图像目录的`ASSET_NAMES.txt`；复制其中`.image.txt`全文给GPT Image；视频目录的`UPLOAD.md`列出每段H3输入。不要把生产JSON、BodySpec或内部编号表当模型提示词。

## 内容完整性

十一项指定核心规范均已展开；另有媒介预设、Seedance兼容、数据合同、质量门和源审查。新增32号规范把人物目标、社交策略、动作因果、运动弧、语气节拍和切镜声音写成可编译字段。20号规范内逐条列出原作者001–132名称与文件，data目录提供同源机器索引。30号规范保留原始100条出处，并增加任务指定十类的E001–E100五轨配方。原版盛唐、IM2、巨构、打戏、H3与冷热记忆资料以原文保留并逐文件哈希，不用标题代替源资料。

## 使用顺序

从完整示例复制生产数据并改成自己的项目，保留总时长和素材路径。剧本初稿可先使用 `templates/script-stage.json`，资产初稿可先使用 `templates/asset-stage.json`，分别运行post_hooks。完整镜头包先audit再compile。只改特效用基线SHA和vfx补丁；跨场次先archive，需要继续时restore到新目录。

默认工具不会调用视频／图像模型，也不会自动花费额度。H3真实生成能力和执行参数由当前入口确认。编译资产或视频包时会额外写出 `DELIVERY_VIEW.md`，用于先看懂交付内容；JSON核心工具只需Python3.10+；YAML支持需PyYAML；重新生成灰模PNG需Pillow；拉片和Previs媒体检查需ffmpeg/ffprobe。

## 验收含义

结构得分100表示该样例的适用机器合同全部通过；实际分母见当前验收报告，包含十项基础门和按范围启用的叙事、资产、表演交接与灵动表演合同。N/A明确列出。跨集例的基础资产提示词可提交，三个依赖未生成身份/场景图的关键帧明确为草案。纸鹤参考是本包程序绘制的原创单帧，不是AI生成视频。影片身份稳定性、自然表演、碰撞质感、精确冲击帧和真实音频频谱仍需生成后验收，不宣称全球排名。

132 段白模 MP4 随包放在 `camera-moves-whitebox-132/`，每段按 `data/camera-moves.json` 的 `source_file` 匹配；它们只是可选的运镜／Previs 参照，不是角色、场景或最终成片资产。媒体技术验收见 `camera-moves-whitebox-132/manifest.json` 和 `reports/previs-media-acceptance.json`；影片级艺术效果没有因技术参数核验而自动被证明。
