# PROMPT PACK: NEON JUMP（Opus 5.5）— 索引笔记

原件：同目录 `neon-jump-prompt-pack.pdf`（原样存档，5 页，Clawd Motion Lab 出品；来源为作者 X 帖子所附 Google Drive 分享）。
内容：一支 14 秒无缝循环短片的完整提示词包——体素吉祥物开红色跑车穿霓虹隧道、飞跃断桥、空中慢动作、落地砸拍后回到第一帧。全部画面由 Claude Opus 5.5 按提示词写成 Blender 场景、GPU 渲染。

包的结构（全文都在 PDF 里，提示词标注为 copy-ready）：
- 第 1 页：成片规格（14.0s / 30fps / 1920x1080 / 420 帧无缝循环 / 137.14 BPM，8 小节 = 14 秒）与六条公式：世界复用、节拍定物理、慢动作慢距离不慢重力、吉祥物从 logo 像素网格来、用测不用猜（帧差查接缝、频谱图+ebur128 查声音）。
- 第 2 页：主提示词（320 词），结构 = BRAND 块（HERO/RIDE/PROP/SET/SIGNS/PALETTE，唯一需要替换的部分）+ FORMAT + BEATS（逐秒节拍表）+ CAMERA + LOOK + CHECKS（先渲染 9 张节拍静帧再全量）。
- 第 3 页：4 条跟进提示词原文与每轮结果（体素尺寸/座位/镜头距离、去掉方向盘与仪表屏、gpu.py 切 OptiX 把 20 小时压到 54 分钟、去噪点降体积）；附"改成自己的"BRAND 替换示例与渲染流程、逐帧节拍表。
- 第 4–5 页：配音提示词（220 词量级，全 numpy 合成、与画面共用 timeline.py）+ 2 条看频谱图后的跟进（低频墙、接缝采样跳变的修法）与最终响度数据（-9.2 LUFS）。

值得借鉴进剧坊的点：先静帧 contact sheet 再全量渲染的质量门；接缝用帧差量化验收；画面与声音共用一份 timeline 驱动；BRAND 块参数化、一套提示词换皮复用。
