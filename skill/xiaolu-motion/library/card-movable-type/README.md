# card-movable-type · 活字印刷标题

金属活字从暗处升起、翻转，按阅读顺序一块块落进钢制排字槽，楔子锁版，一道光扫过抛光字面，副标题聚焦出现。全屏卡，4.4 秒，1080×1920，30 fps，带合成音效。

![thumb](thumb.jpg) · 预览：`preview.mp4`（202×360）

## 做法

- 每个字是一块有体积的铅字（透视相机、背面剔除、每个面按 Blinn-Phong 打光）：钨丝灯主光从左上、冷色逆光从后方。字面上的字是凸起的抛光金属（阴影、肩部、高光斜边），底面是氧化金属加机加工纹。
- **字永远正向、按阅读顺序**：字只画在活字的正面，并且经过这个面自己的投影四角映射（左上→右上、左上→左下），所以飞行中翻转也不会出现镜像或倒字；落位从左到右依次进行，飞行结束时旋转角正好是整圈。
- 升起–顶点–落下是抛物线，落定后弹一下；锁版时整行被楔子挤紧 6 px，镜头轻微震动。
- 背景：虚焦的字盘（透视、重模糊、零星金属反光）、光束里的浮尘、暗角和颗粒；子帧运动模糊来自 `engine/post.js`。

## 适合场景

标题卡、章节开头、“开源 / 工具 / 印刷 / 排版 / 一字一句”相关的主题；2–7 个字的短标题最好看。

## 主要参数（`src/build.py` 的 `PARAMS`，默认值见 `src/movable_type.js`）

| 参数 | 默认 | 说明 |
|---|---|---|
| `text` | 开源镜头库 | 标题，每字一块活字（2–7 字） |
| `sub` | OPEN SOURCE · MOTION LIBRARY | 锁版后出现的副标题 |
| `label` | LETTERPRESS | 左上角小标签，留空不显示 |
| `t0` / `stagger` | 0.15 / 0.12 s | 第一块起飞时间、相邻两块间隔 |
| `rise` / `fall` | 0.62 / 0.27 s | 上升、下落用时 |
| `lock_gap` | 0.34 s | 最后一块落位到锁版 |
| `metal` / `glyph` / `key` / `rim` / `bg` | — | 金属色、字面高光、主光、逆光、底色 |

## 声音

每块活字落槽一声 `type_clink`（本条目合成：自由振动金属条的非谐波模态 1 : 2.76 : 5.40 : 8.93 + 瞬态 + 钢轨闷响 + 一次小回弹），锁版 `type_lock`（更低更重的金属“咔”+ 棘轮双击），起飞轻 whoosh，扫光 `shimmer`，副标题一颗 `pluck`，底下一层暖色房间底噪和 D 调低音垫。时间点取自组件的 `timing()`，与画面同源。成片 −27.0 LUFS / 峰值 −8.0 dBTP（音效按 xlaudio 参考电平，设计成压在 −16 LUFS 人声下面）。

## 重渲

```bash
cd library/card-movable-type/src
python3 build.py stills --times 0.6 1.4 2.45 3.7      # 审图
python3 build.py render --out <输出目录>              # <输出目录>/card-movable-type.mp4 + 本目录 preview.mp4 / thumb.jpg
```

需要仓库根目录 `fonts/` 里的思源宋体 Heavy、思源黑体 Medium（`scripts/get_fonts.sh`），以及 Chrome、ffmpeg、Python 3.13（playwright、numpy、Pillow、fontTools、scipy、numba）。渲染前会逐字检查字体里有没有这个字（没有就报错，不会出豆腐块）。

## 文件

- `src/movable_type.js`：引擎组件（与 `components/*.js` 同一契约：`params`、`draw`、`bbox`、`mbSamples`、`post`、`timing`）。
- `src/sound.py`：两个本条目合成的音效（运行时注册进 xlaudio，不改 audio 包）+ 音效表 + 底噪。
- `src/build.py`：这一条的 `SHOT` 配置。
- `src/shotkit.py`：所有 card-* / fusion-* 条目逐字相同的渲染脚本：用仓库自带的 `engine/runtime.js` 在 headless Chrome 里渲染这个组件（子帧运动模糊、辉光、暗角、颗粒），xlaudio 出声，混流、校验帧数后改名，再出 360p 预览和缩略图。
