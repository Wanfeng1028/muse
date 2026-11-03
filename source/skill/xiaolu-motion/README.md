# xiaolu-motion · 口播动效底座

给任何创作者用的口播/录屏视频剪辑包装系统：读分镜 JSON,出透明动效叠层,再用 ffmpeg 分层合成到真人口播或录屏上,最后过 QA 门禁。目标是让 Agent(Claude Code、Codex 等)读逐字稿直接写分镜、直接出成片,不做可视化剪辑台。代码与风格分离:品牌(配色、字体、质感)只是 `styles/` 下的一个令牌包,换风格只换令牌文件。

配套一份 [`SKILL.md`](SKILL.md)(给 Agent 看的完整导演工作流:确认选题 → 定风格 → 出分镜样帧 → 剪辑出片,每步都要人确认)和一个 [`library/`](LIBRARY.md) 动效镜头库(几十个可直接参考的具体实现:关键词弹出、章节进度条、转场、分屏工作台……每条都有预览视频和来源说明)。

> 本目录只含引擎侧。`audio/` 由音频侧维护(音效/音乐,全部代码合成,见 [`audio/README.md`](audio/README.md))。

## 效果预览

完整清单和预览视频见 [`LIBRARY.md`](LIBRARY.md)(每条都有 `preview.mp4` + `thumb.jpg` + 来源说明)。几个代表性效果:

| | | | |
|---|---|---|---|
| ![](library/semantic-starfield/thumb.jpg) | ![](library/falling-text/thumb.jpg) | ![](library/card-number-impact/thumb.jpg) | ![](library/fusion-word-behind/thumb.jpg) |
| 语义星空 | 落字 | 数字冲击 | 字在人后 |

## 目录

| 路径 | 内容 |
|---|---|
| `SKILL.md` | 给 Agent 看的导演工作流入口:四步流程、固定规则(纸条字幕/人物不消失/不压脸不压嘴等),细节指针见 `references/`(剪辑技术、性能与稳定性、QA 门禁、导演方法等) |
| `library/` | 动效镜头库,见 [`LIBRARY.md`](LIBRARY.md) 总表;每条含 `src/`(参考实现)、`preview.mp4`、`thumb.jpg`、`README.md` |
| `engine/` | 浏览器内渲染内核(ES module):`core.js` 缓动/弹簧/哈希/噪声/颜色,`text.js` 中文逐字排版与聚焦入场,`particles.js` 火花与浮尘,`post.js` WebGL2 后期(子帧运动模糊、双半径辉光、暗角、闪白、色散、颗粒,透明/不透明两种输出),`runtime.js` `renderFrame(t)`、分层、视差、bbox,`fonts.js` FontFace(ArrayBuffer) 注入 |
| `components/` | 参数化组件:`kinetic_keyword`(关键词逐字聚焦+高亮底)、`chapter_tag`(章节标签+HUD 进度)、`token_cut`(切刀扫描全遮罩转场)、`ip_intro`(IP 固定开场,默认占位素材——见下文"换成你自己的") |
| `styles/` | 令牌:`base.json`(模板,列全部键)、`coldlight.json`(冷光)、`paperwhite.json`(纸白)、`scrapbook.json`(拼贴手账)、`kepu-explainer.json`(科普讲解)、`paper-handdrawn.json`(纸本手绘) |
| `timeline/` | `schema.json` + `SCHEMA.md`、`resolve.py`(校验+词锚解析+扁平 sfx)、`validate.py`、`words.py`(ASR → words.json)、`anchors.py`、`dump_specs.mjs` |
| `render/` | `python3 -m render …`:并行出透明层(ProRes 4444/HEVC-alpha)、分层合成、镜头表达式、字体解析、alpha 探针 |
| `qa/` | 门禁:`check.py`(精确 bbox)、`pixel_qa.py`(任意成片,Apple Vision 人脸/文字/卡片检测)、`alpha_selftest.py`、`camera_selftest.py`、`contact_sheet.py`、`token_switch.py`、`safe_zones.json`。Vision 探测已做分块+`autoreleasepool`,长视频不会把内存吃爆(见 `references/performance.md`) |
| `scripts/` | `get_fonts.sh`(下载/校验开源字体)、`with_heavy_lock.py`(全机重任务并发锁,最多两个、内存告急自动停) |
| `examples/minimal/` | 开箱即用的最小示例:合成渐变底片(无真人素材),干净 clone 直接能跑通 |

## 快速开始

```bash
git clone <this-repo> xiaolu-motion && cd xiaolu-motion
./scripts/get_fonts.sh                                             # 下载开源字体(思源黑/宋、霞鹜文楷)
python3 -m timeline.validate examples/minimal/storyboard.json      # 校验分镜
python3 scripts/with_heavy_lock.py -- \
  python3 -m render build examples/minimal/storyboard.json --selftest
# -> examples/minimal/out/: final.mp4、overlay_front.mov(ProRes 4444)、
#    overlay_front.hevc_alpha.mov、contact_sheet.png、qa/、BUILD_STATUS.json
```

依赖:Python 3.13(playwright 1.55、numpy、opencv-python、Pillow、fontTools、jsonschema)、Node 22(只用于导出组件参数表)、ffmpeg 8(`prores_ks`、`hevc_videotoolbox`、`libx264`)、Google Chrome(headless,`channel="chrome"`;Playwright 1.55 缓存的浏览器版本对不上)、Xcode 命令行工具里的 `swiftc`(Vision/AVFoundation 探针,首次运行自动编译到 `.cache/bin/`)。**只支持 macOS**(Apple Vision 是 QA 门禁的核心)。全程 headless,不弹窗。

## 流水线

1. **解析**(`timeline/resolve.py`):JSON Schema → 底片 ffprobe、按源帧吸附 → words.json 映射到时间轴(可选,纯数字秒的分镜不需要 ASR)→ 词锚转秒 → 按组件自身的 `params` 声明校验参数 → 扁平 `sfx`。
2. **透明层**(`render/overlay.py`):N 个 headless Chrome 各渲一段连续帧,`renderFrame(i/fps)` 的预乘 RGBA 直接经本地 HTTP 流进各自的 ffmpeg,不落 PNG 序列。
   - ProRes 4444:`prores_ks`、`yuva444p10le`、16 位 alpha、预乘、BT.709 标记,分段后 `-c copy` 无损拼接。
   - HEVC-alpha:从成品 ProRes 走一次 `hevc_videotoolbox`,MOV/hvc1,预乘(VideoToolbox 默认,SEI `alpha_channel_use_idc=1`)。要写全 BT.709 三个标记,必须以 AYUV 喂给编码器;事后用 `hevc_metadata` 补标记会让 AVFoundation 解不出 alpha 层。
   - 按层渲染:`layer: behind` 的镜头出 `overlay_behind.mov`,`front`(默认,含转场)出 `overlay_front.mov`,`invert: true` 的镜头出 `overlay_invert.mov`。
3. **分层合成**(`render/composite.py`,一次 ffmpeg):L0 底片 → L1 人后图形 → L2 人像(底片 × 灰度遮罩)→ L3 人前图形 → L3i 反相 HUD(`invert: true`,difference 混合,见 `references/director.md`)→ L4 全局镜头(底片和遮罩在 ffmpeg 里做,图形在引擎里按 `depth` 做视差)→ L5 统一收尾(eq + 颗粒)。预乘混合写成 `bg·(1−a) + O`(`maskedmerge` + `blend=addition`,平面 RGB)。**不用** ffmpeg 自带的 `overlay=alpha=premultiplied`:实测它在 gbrp 下整体偏 16 级,半透明边缘权重也不对(见 `qa/alpha_selftest.py`)。
4. **镜头**:`perspective … eval=frame` + 三次插值,子像素平滑。crop 的输出尺寸只在初始化时求值,crop/scale 式推近会按整像素跳。取景窗口恒为画布比例,只会等比缩放。
5. **QA 门禁**:`qa.check`(精确 bbox)+ `qa.pixel_qa`(对成片像素复核)。任何一项命中:`final.QA_FAILED.mp4`、`BUILD_STATUS.json` = FAIL、退出码 1。规则清单见 `references/qa.md`。

## QA

- 排斥区:脸框、嘴(脸框下 1/3)、字幕带(画面高 74–86%);另有安全区、最小字号、不同镜头 bbox 交叠、转场中点必须全遮盖。
- `qa.check`:每帧向页面取各组件的 bbox(与 draw 共用布局,已含视差变换);人脸来自 Apple Vision 对底片源帧的检测,经同一套 cover-fit 和镜头数学换算到画布。
- `qa.pixel_qa`:给没有 bbox 的成片用。Vision 找人脸(含唇部)、中文文字行、矩形卡片;字幕靠与 SRT 文本匹配识别(忽略时间)。规则:压脸、压嘴、压字幕带、字幕不在字幕带、顶栏常驻(同一顶部文字 ≥80% 采样且 ≥ min(10s, 采样窗口 80%) )、空卡(卡片主体 ≥62% 空白网格)、压盖(文字互压、文字骑卡片边、卡片部分重叠;卡片边须在像素上真实存在才算)。
- 自证:跑一遍"快速开始"里的 `examples/minimal/` 命令,`out/BUILD_STATUS.json` 应为 `"status": "PASS"`,`out/qa/qa_report.json` 和 `out/qa/pixel_final_report.json` 里 `violations` 应为空——这是仓库里唯一一份不依赖任何私有素材、干净可复现的 QA 通过样例。

## 换成你自己的(`components/ip_intro.js`)

固定开场组件默认打包的是占位素材,不是任何人的真人资产:

1. 把你自己的照片处理成蓝底/纯色底的表情卡,跑 `python3 components/ip_intro/tools/cutout.py <你的蓝底图> components/ip_intro/assets/stickers/<name>.png` 抠成透明大头贴,再在 `components/ip_intro/assets/manifest.json` 里登记。
2. 往期封面素材属于本机资产,默认不入库(`components/ip_intro/assets/covers/.gitignore`)——用 `python3 components/ip_intro/tools/prep_covers.py <你的配方 JSON>` 按自己的封面生成 `covers/` 目录,组件缺图时会画空白纸卡占位,不会报错。
3. 组件参数(`prefix`/`name`/`name_color`/`sub`/`sub_hi` 等,见 `components/ip_intro/README.md`)按你自己的名字、口号、品牌色改。

平台名、产品名同理——分镜和组件参数里都留成可配置项,不要在 `library/` 的参考实现里看到写死的名字就照抄进你自己的分镜。

## 字体(开源默认)

令牌默认使用可分发的开源字体。跑 `./scripts/get_fonts.sh` 下载到仓库根目录 `fonts/`(已 gitignore,校验和自动核对),或装到 `~/Library/Fonts`。找不到时退回本机系统字体(苹方/宋体-简/SF),并在 `BUILD_STATUS.json.fonts_missing_open` 里标为不可分发——本地起草没问题,正式发布前确认用到的字体角色都已可分发。详见 `fonts/SOURCES.md`(版本、下载 URL、SHA-256)和 `NOTICE`(许可摘要)。

| 角色 | 字体 | `get_fonts.sh` 下载 |
|---|---|---|
| sans | 思源黑体 Source Han Sans SC | 是(Regular/Medium/Bold) |
| serif | 思源宋体 Source Han Serif SC | 是(Bold/Heavy) |
| kai | 霞鹜文楷 LXGW WenKai | 是(Regular) |
| display | 得意黑 Smiley Sans | 否,见 `fonts/SOURCES.md` |
| mono | JetBrains Mono | 否,见 `fonts/SOURCES.md` |
| latin | Inter | 否,见 `fonts/SOURCES.md` |

## 性能(M4,4 个 worker,10 秒 300 帧)

- 每帧(单 worker):JS 发起绘制 ≈0.4 ms,GPU 完成+回读 ≈8.8 ms,传输+ProRes 编码背压 ≈42 ms。
- 透明层 300 帧 8.6 s(含每 worker ≈1.3 s 启动),HEVC-alpha 转码 ≈2.4 s;合成 7.6 s;两道 QA 7.2 s;联系表 2.6 s;不含自测整条 ≈30 s。
- 9:16 @60 fps 冒烟:600 帧透明层 19.7 s、合成 17 s。
- 中间文件:10 秒示例全部产物约 15-50 MB(取决于是否转 HEVC-alpha)。

全机层面的并发和内存保护见 `scripts/with_heavy_lock.py`——重任务(编码、Vision 探测、Chrome 渲染)都应该用它包起来跑,详见 `references/performance.md`。

## 已知限制

- 组件只做接口验证,未做视觉精修;`token_cut` 是冷光风格,`scrapbook`/`kepu-explainer`/`paper-handdrawn` 三个新风格包是按对应演示视频的观感重新配的令牌起点,不是逐像素还原源素材。
- L2 人像遮罩只收灰度视频路径,未接入真实遮罩(behind 层的图形在没有遮罩时等同 front 层)。
- L5 目前只有 eq + 颗粒;`light_sweep` 只预留字段。
- 像素 QA 是启发式:Vision 的矩形检测会有误差,卡片边做了像素真实性校验;结论附带截图供人工复核。
- HEVC-alpha 是 8 位 4:2:0:与 ProRes 相比 alpha 最大差 4 级,彩色锐边最大差约 50 级(均值 0.09)。剪映实际导入效果要人工验收。
- 默认开源字体本机未安装时用系统字体兜底(报告里已标不可分发)。
- `library/` 里不少参考实现来自具体项目的真实代码,坐标/参数常按某个具体画幅写死,移植到你自己的分镜前通常要重新量一遍——每条 `README.md` 会标注这一点。

## 兼容性

这套引擎和 `SKILL.md` 不绑定具体 Agent 产品或个人身份,按通用格式编写。Claude Code、Codex 等能读取仓库文件、执行 shell 命令的 Agent 都可以直接用——把 `SKILL.md` 交给 Agent,配合逐字稿和素材,就能按四步流程走完整个剪辑包装工作流。

## 许可

Apache License 2.0(见 `LICENSE`)。第三方字体许可见 `NOTICE` 和 `fonts/SOURCES.md`,字体文件本身不在仓库内。

---

## English

xiaolu-motion is an open-source editing/packaging engine for talking-head and screen-recording short-form video: a JSON storyboard drives a headless-Chrome + WebGL2 renderer that produces transparent motion-graphics overlays, ffmpeg composites them onto your footage, and an Apple Vision–powered QA gate checks the result pixel-by-pixel (no text on faces/mouths/caption band, no stuck HUD text, no empty cards, transitions that actually cover the cut). Style is a swappable token file (`styles/*.json`), not hardcoded into components.

See [`SKILL.md`](SKILL.md) for the full director workflow (confirm topic → pick style → storyboard preview → render + QA, with a check-in before each step) and [`LIBRARY.md`](LIBRARY.md) for a library of reference shot implementations with preview clips. Quick start: `./scripts/get_fonts.sh` then `python3 -m render build examples/minimal/storyboard.json --selftest` (synthetic gradient footage, no real people, runs from a clean clone). macOS only (Apple Vision). Works with Claude Code, Codex, or any agent that can read files and run shell commands. Licensed under Apache 2.0; third-party OFL fonts are downloaded separately, not bundled (see `NOTICE`).
