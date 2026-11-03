---
name: xiaolu-motion
description: "口播/录屏短视频剪辑与包装的导演工作流,配一套可复用的动效镜头库:确认选题 → 定风格 → 出分镜样帧 → 剪辑出片并过 QA 门禁,产出可直接发布的短视频成片。用于剪辑或包装口播/录屏类短视频(小红书、抖音、Shorts、Reels)时触发:删停顿、加动态字幕和运动图形、挑选视觉风格、或交付前跑像素级 QA 检查。Director workflow and reusable motion-graphics shot library for turning a talking-head or screen-recording video into a polished, packaged short-form edit — style selection, storyboard previews, effect shots, and a QA gate before final render. Use when editing or packaging a talking-head/voiceover video for short-form platforms (Xiaohongshu, Douyin, Shorts, Reels): cutting silence, adding kinetic captions and motion graphics, picking a visual style, or running a pixel-level QA pass before delivery."
---

# xiaolu-motion — 口播视频剪辑与包装 Skill

给任何创作者用的口播视频剪辑包装系统。输入逐字稿/分镜想法 + 真人口播或录屏素材,输出过 QA 门禁的短视频成片。核心思路:**代码即分镜**——JSON 分镜描述画面,浏览器(headless Chrome + WebGL2)渲染透明动效层,ffmpeg 分层合成到底片,Apple Vision 做像素级把关。不做可视化剪辑台,Agent 直接读文字、写分镜、出成片。

引擎、组件、渲染器、QA 门禁已是仓库一部分(`engine/` `components/` `render/` `qa/` `timeline/`);本文档讲的是**工作流和固定规则**,不是 API 文档——API 细节见各目录代码注释和 `README.md`。只在 macOS 完整可用(Apple Vision 做检测,`swiftc` 编译探针),环境要求见仓库 `README.md`。

## 四步流程

每一步做完都要拿给用户确认,得到明确点头才进下一步——风格和分镜这两步尤其不要抢跑,返工成本远高于多问一句。

1. **确认选题**:复述你理解的核心信息和目标平台/画幅,让用户确认。逐字稿没有词级时间码就先跑 ASR(思路见 `timeline/words.py`),分镜时间点可以用词锚 `{"text": "…"}` 代替绝对秒数。
2. **定风格**:挑 2-3 个候选(`styles/` 已有风格包,或 `library/` 演示成片截图),渲一张静态样张对比甩给用户选,选定后才进入分镜——风格决定后面所有令牌引用,返工要重写每一镜。用法见 `references/styles.md`。
3. **出分镜样帧**:按逐字稿写分镜 JSON(schema 见 `timeline/SCHEMA.md`),挑关键镜头渲静态样帧确认构图/字号/节奏,通过再渲全片——渲全片是四步里最贵的一步。参考做法见 `references/library.md`。
4. **剪辑出片**:先删停顿再决定是否提速(`references/editing.md`),渲**低清全片**确认剪辑点/字幕/节奏,再出高清成片,跑 QA 门禁(`references/qa.md`)——QA 不过就是没做完,不是"差不多能用",不把 `QA_FAILED.mp4` 当交付物。

## 固定规则

分镜怎么写、组件怎么调参都要服从这些设计前提,不是可选建议:

- **纸条字幕**:字幕是"贴在画面上的纸条"(见 `library/` 纸条字幕条目),不是无背景纯文字描边。
- **重点词放大配音效**:关键词短暂放大/加高亮底 + 轻 pop 音效(`components/kinetic_keyword.js`),不靠文字动效自己抓注意力。
- **人物不消失**:切进全屏图形/图表时真人收进右下 PiP,不整个消失;只有极短全屏转场例外。
- **不压脸、不压嘴**:图形/字幕/卡片不压脸框,尤其嘴部(脸框下三分之一)——QA 硬规则,写分镜时就该避开。
- **平台名/品牌名可配置**:分镜、组件参数里的平台名/产品名/品牌色做成参数或令牌,不硬编码。
- **无人段 ≤ 3 秒**:连续无真人画面(纯图形转场/素材插入)不超过 3 秒。

导演视角上"这一镜好不好"怎么判断(钩子、节奏、镜头设计、人物可读性、自检顺序)见 `references/director.md`。

## 需要时读哪份参考

| 何时读 | 文件 |
|---|---|
| 删停顿 / 整体提速的具体参数和命令 | `references/editing.md` |
| 并发内存锁、`.partial` 写法、ffmpeg 帧对齐、Vision 探测防泄漏、子帧运动模糊采样数 | `references/performance.md` |
| QA 门禁完整清单、先低清后高清的交付节奏 | `references/qa.md` |
| 怎么在 `library/` 镜头库里挑效果、移植参考实现 | `references/library.md` |
| 怎么写/继承一个风格包(`styles/*.json`) | `references/styles.md` |
| 判断一镜好不好:故事钩子、节奏、镜头/转场设计、人物可读性、自检顺序;反相混合 HUD 文字和粒子聚字两个具体技法 | `references/director.md` |
| 换成自己的固定开场素材(照片、封面) | `components/ip_intro/README.md` |
| 镜头库总表、预览视频 | `LIBRARY.md` |

## 兼容性

这套 SKILL 按 Agent Skills 通用格式编写,不绑定具体 Agent 产品——在 Claude Code、Codex 等支持读取仓库内 `SKILL.md` 的 Agent 里都可以直接引用。
