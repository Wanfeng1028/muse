# 分镜 JSON · schema v0.1

机器可读版本：`timeline/schema.json`（JSON Schema 2020-12）。校验与解析：`python3 -m timeline.validate SB.json`、`python3 -m timeline.resolve SB.json`。

## 1. 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | `"0.1"` | 必填 |
| `canvas` | `{w, h, fps}` | 默认 `1080×1440 @ 30`；`h` 可选 1920（9:16），`fps` 可选 60 |
| `style` | string | `styles/<name>.json`（或路径）；换风格只换这一项 |
| `style_overrides` | object | 可选，深合并进令牌（单条视频微调） |
| `duration` | number | 时间轴长度（秒），帧数 = round(duration × fps) |
| `base` | clip[] | L0 底片片段，见 §3 |
| `camera` | camkey[] | L4 全局镜头，见 §4 |
| `words` | string | 词级时间码文件（相对分镜文件），见 §7 |
| `shots` | shot[] | 叠层组件，见 §5 |
| `transitions` | transition[] | 转场组件，见 §6 |
| `music` | object | 音乐意图，原样透传给音频侧：`{mode: synth\|file\|none, preset, file, gain_db, duck: {under: "voice", depth_db ≤ 0}}` |
| `finish` | object | L5 统一收尾：`{contrast, saturation, brightness, gamma, grain}`；`light_sweep` 预留未实现 |
| `qa` | object | 门禁参数，见 §8 |

## 2. 时间写法（所有时间字段通用）

- 数字：时间轴绝对秒。
- 词锚 `{"word": i}`：words.json 里序号为 `i`（0 起）的词，必须落在某个底片片段里。
- 词锚 `{"text": "剪映skill", "occurrence": 1}`：时间轴上第 n 次（1 起，默认 1）出现的这段文字。匹配前做 NFKC、小写、去空白和标点，所以 `剪映 Skill` 能对上 ASR 的「剪 / 映 / sk / ill」；多字词的时长平均分给每个字。
- 两种词锚都可加 `"edge": "start"|"end"`（默认 start）和 `"offset": 秒`。
- 仅 `end` 可用 `{"dur": 秒}`（= start + dur）。
- 仅 `sfx.at` 可用 `"start"|"mid"|"end"`（所属镜头的起/中/止）和 `{"rel": 秒}`（相对镜头开始）。

## 3. base 片段（L0 / L2）

```json
{"id": "b1", "src": "/abs/or/relative.mp4", "in": 15.5, "out": 19.433333, "at": 0.0,
 "fit": "cover", "audio": true, "matte": "person_matte.mp4", "camera": []}
```
- `in/out` 按源帧对齐（解析器会报告吸附）；`at` 应在输出帧边界上。
- 片段不能重叠；空隙渲染黑场并警告。
- `matte`（L2 人像遮罩）：与 `src` 同时基、同尺寸的灰度视频，白 = 人。有遮罩时 `layer: "behind"` 的图形会被人挡住。
- `camera`（片段内取景）：与全局镜头二选一，两者都在动时报错。

## 4. camera 关键帧（L4 全局镜头）

`{"t": 时间, "zoom": ≥1, "cx": 0..1, "cy": 0..1, "ease": 名称}`
- `ease` 描述**以该关键帧结尾**的那一段；首帧之前、末帧之后保持。
- zoom 按对数插值，中心线性插值；取景窗口恒为画布比例，所以只会等比缩放，不会拉伸，也不会出画。
- 缓动名：`lin linear step sineIn sineOut sineInOut quadIn quadOut cubicIn cubicOut cubicInOut quintInOut expoIn expoOut expoInOut`（与 `engine/core.js` 的 `E`、`render/camera.py` 同一套公式）。
- `step` 用于在全遮盖转场的中点瞬时复位镜头。

## 5. shots

```json
{"id": "s02", "component": "kinetic_keyword",
 "start": {"text": "剪映skill", "offset": -0.08}, "end": {"dur": 2.3},
 "layer": "front", "depth": 0.0, "z": 1,
 "params": {"text": "剪映 Skill", "y": 0.205},
 "sfx": [{"id": "pop_soft", "at": "start", "gain_db": -6}]}
```
- `component`：`components/<id>.js`；参数名、类型、范围由组件自己的 `params` 声明校验（`node timeline/dump_specs.mjs` 可列出）。
- `kinetic_keyword` 未给 `params.text` 且 start 是文字锚时，自动用锚点文字。
- `layer`：`"front"`（L3，默认）或 `"behind"`（L1，人身后；需要底片有 `matte`，否则警告）。
- `invert`：`true` 时这一镜走反相混合图层（L3i）：单独渲成 `overlay_invert.mov`，在 L3 之后按 `bg·(1−a) + |bg·a − O|`（预乘 difference）合成，白墨在亮底变暗、暗底保持亮，中灰底（灰阶约 73–182）对比不足。只允许组件导出了 `invert = true`（目前 `chapter_tag`），否则解析报错；与 `layer: "behind"` 同用也报错。解析后这一镜的 `layer` 为 `"invert"`。用法和实测见 `references/director.md` 技法卡。
- `depth`：视差系数。0 = 屏幕锁定（HUD，默认）；1 = 与底片同动；0–1 之间为视差。公式：`T_d(P) = (P − c_d)·z^d + C`，`c_d = C + (c − C)·d`（c 为镜头视野中心，C 为画面中心）。QA 读到的 bbox 已经过同一变换。
- `z`：同层内的绘制顺序（默认数组顺序）；转场永远在最上层。

## 6. transitions

`{"id": "t01", "type": "token_cut", "at": 3.933333, "dur": 0.6, "align": "center", "params": {}, "sfx": [...]}`
- `align`：`center`（默认，中点 = at）、`start`、`end`。
- 转场组件的职责是在中点把画面 100% 盖住，底片剪口放在 `at` 上就看不见；QA 会检查中点是否全遮盖。中点不在任何片段边界上时解析器警告。

## 7. words.json

```json
{"version": "0.1", "clock": "media", "media": "/abs/path/video.mp4",
 "words": [{"i": 0, "w": "如果你", "s": 0.0, "e": 0.48, "p": 0.94}]}
```
- 由 `python3 -m timeline.words --whisper ASR.json [--compiled compiled.json] --media VIDEO --out words.json` 生成；`--compiled` 把原片时间码按剪映编译计划映射到剪后时间轴，被剪掉的词丢弃。
- 时间轴映射：`src` 与 `media` 相同的每个片段，`t = at + (t_media − in)`。`clock: "timeline"` 表示已是时间轴时间。

## 8. qa（门禁）

| 字段 | 默认 | 说明 |
|---|---|---|
| `safe_zone` | `xhs_3x4` / `xhs_9x16` | `qa/safe_zones.json` 里的画面分区 |
| `avoid` | `["face", "captions"]` | 排斥区：脸框、嘴（脸框下 1/3）、字幕带（画面高 74–86%） |
| `captions.band` | 无 | 覆盖字幕带 `[x0, y0, x1, y1]`（比例） |
| `face.pad` | 0 | 脸框外扩比例 |
| `sample_every` | 1 | 每几帧查一次 |
| `overlap_tolerance_px` | 0 | 不同镜头 bbox 允许的交叠面积 |
| `min_font_px` | 24 | 最小字号 |

任何一条命中即渲染失败（`BUILD_STATUS.json` = FAIL，成片改名 `final.QA_FAILED.mp4`，退出码 1）。

## 9. 解析结果（resolved.json，给渲染器和音频侧）

- 所有时间都是绝对秒：`shots[].t0/t1`、`transitions[].t0/at/t1`、`camera[].t`、`base[].t0/t1`。
- `shots[].layer`：`behind` / `front` / `invert`（由 `invert: true` 归一而来），渲染器按层各出一个 overlay，空层跳过。
- `sfx`：全片扁平音效提示 `[{id, t, source, source_kind, gain_db?, pan?, dur?}]`，按时间排序，音频侧直接消费。
- `tokens`：合并后的风格令牌；`words`：映射到时间轴的词；`music`、`finish`、`qa` 原样带出。

## 10. 组件契约（components/*.js，ES module）

导出 `id`、`role`（overlay / hud / transition）、`desc`、`params`（`{name: {default, type, desc, min?, max?, values?}}`）、`sfx_hints`，可选 `invert = true`（声明可放进反相混合图层），以及：
- `draw(ctx, localT, params, tokens, env)`：`ctx` 为全分辨率主层；`env = {W, H, fps, s(=W/1080), dur, t, glow(半分辨率辉光层，同一坐标系), subdt, mode, seed, id, invert}`。不要对 `env.glow` 调 `setTransform`。`env.invert` 为真时这一镜在反相图层，组件应只画白墨（层级用 alpha）、不画辉光。
- `bbox(localT, params, tokens, env)` → `[{kind: text|shape, label, x, y, w, h, alpha, font_px?, bleed?, full?}]`，与 draw 共用同一份布局函数。
- 可选 `mbSamples(localT, …)`：本帧需要的运动模糊子帧数；可选 `post(localT, …)` → `{flash, ca, fade}`。
- 颜色参数写 `@name`（取 `tokens.colors.name`）或 `#hex`；字体只通过 `tokens.type.<角色>` 取。

## 11. 相对 v0 草案的改动

1. `camera` 从片段内移到顶层（L4 全局镜头），片段内 `camera` 只作取景且与全局互斥；`ease` 语义写明为“结束于该帧的那段”，新增 `step`。
2. shots 新增 `layer`（behind/front）和 `depth`（视差）；base 新增 `matte`（L2 人像遮罩）；新增顶层 `finish`（L5）。
3. 时间写法补充 `edge`、`offset`、`{"dur"}`、`{"rel"}`、`"mid"`；`word` 序号明确为 0 起，`occurrence` 为 1 起、按时间轴上可见的词计数。
4. transitions 新增 `align`；解析结果给出 `t0/at/t1`。
5. sfx 在解析后扁平成全片 `sfx` 列表（音频侧契约）；`music` 允许附加字段。
6. qa 新增 `captions.band`、`face.pad`、`sample_every`、`overlap_tolerance_px`、`min_font_px`，且全部为门禁。
7. `canvas` 限定 w=1080、h∈{1440,1920}、fps∈{30,60}。
8. （2026-09-28）shots 新增 `invert`（反相混合图层 L3i）；组件契约新增可选导出 `invert` 和 `env.invert`；解析结果的 `layer` 多一个取值 `invert`。不写 `invert` 的分镜解析与合成结果不变。
