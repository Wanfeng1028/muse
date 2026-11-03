# card-flow-nodes · 连线工作流

工作流的节点依次亮起（口播素材、文案 → 分镜 → 动效、音效 → 成片），节点之间画出连线，光点沿线逐级流动，最后汇入结果节点；结果节点的圆环充能一圈，完成时爆开。冷光风格（取自《在我开口之前》的前半段：近黑蓝底、冰青、紫、细线 HUD）。全屏卡，4.6 秒，1080×1920，30 fps，带合成音效。

![thumb](thumb.jpg) · 预览：`preview.mp4`（202×360）

## 做法

- 图结构由 `nodes` + `links` 给出，层级自动算（最长路径），节点按层依次出现、同层错开；连线是竖向 S 形三次贝塞尔，出现时有一个亮点走在线头。
- 数据按层流动：每条线在它起点那一层的时间窗里跑 7 个光点（短线段 + 亮核 + 辉光，加真实运动模糊），到达时下一层节点脉动一下。
- 结果节点：流动进入最后一层时圆环开始充能，满圈时轻微闪白、一圈扩散环和 24 颗光点散开，标签从半透明变亮。
- 节点是深色玻璃质感的圆角卡片、细描边、矢量图标（胶片、文字、分格、星芒、波形、播放）和编号；顶部 HUD 有标签、进度线和“06 / 06”计数。

## 适合场景

讲流程、自动化、“一套东西串起来”、AI 工作流；节点和连线可随意改（任意有向无环图）。

## 主要参数（`src/build.py` 的 `PARAMS`）

| 参数 | 默认 | 说明 |
|---|---|---|
| `nodes` | 6 个节点 | `id`、`label`、`icon`（film/text/grid/spark/wave/play）、`x`/`y`（画面比例）、`result`、`sub` |
| `links` | 6 条 | `[from, to]` |
| `title` | WORKFLOW | 顶部小标签 |
| `cyan` / `violet` | #6EE7F5 / #8E7DFF | 冷光主色 |

## 声音

每个节点亮起一颗 `blip`，音高按五声音阶依次升高；每条线画出一声很轻的 `laser_zip`；每一层数据流动一道轻 whoosh、到达一颗 `pop_soft`；流动期间底下是细碎的高频“数据声”颗粒；进入结果节点一条短 riser，完成时 `impact_soft` + D6 钟声 + `shimmer`。成片 −29.5 LUFS / 峰值 −17.4 dBTP。

## 重渲

```bash
cd library/card-flow-nodes/src
python3 build.py stills --times 0.9 2.3 3.1 4.2
python3 build.py render --out <输出目录>
```

字体：思源黑体 Medium / Bold（`fonts/`）。

## 文件

`src/flow_nodes.js`（组件）、`src/sound.py`、`src/build.py`、`src/shotkit.py`（各条目共用）。
