# card-number-impact · 数字冲击

小号数字从 0 飞速计数，边数边变大，速度线向中心汇聚；到目标值时重重砸下：闪白、色散、冲击波环、火星四溅、镜头抖动，辉光从炽白冷却成余烬，标签“剪辑时间省下 / TIME SAVED ON EDITING”落定。全屏卡，4.0 秒，1080×1920，30 fps，带合成音效。

![thumb](thumb.jpg) · 预览：`preview.mp4`（202×360）

## 做法

- 数字用思源黑体 Heavy，炽白→橙→朱红的竖向渐变，同一组数字再画进半分辨率辉光层做光晕；数值在每一帧内保持不变（帧内所有子帧用同一个数），所以计数时字形清楚、不会叠影，而缩放和速度线仍有真实运动模糊。
- 计数曲线是 quadIn（越数越快），最后一下直接跳到目标值；落地时过冲 1.28 倍再弹回。
- 冲击：闪白（暖色）、2–3 帧色散、两道冲击波环、90 颗沿速度方向拉长的火星、40 颗慢慢飘散的余烬、0.6 秒衰减的平移 + 微旋转抖动；背景的红色光晕随之冷却。

## 适合场景

关键数据、结论、“提升 X 倍 / 省下 X%”；目标值、单位、标签都可改（整数）。

## 主要参数（`src/build.py` 的 `PARAMS`）

| 参数 | 默认 | 说明 |
|---|---|---|
| `value` / `unit` | 90 / % | 目标值、单位 |
| `label` / `sub` | 剪辑时间省下 / TIME SAVED ON EDITING | 数字上方、下方的字 |
| `t_count` / `t_hit` | 0.35 / 1.6 s | 开始计数、砸下的时刻 |
| `hot` | #FF5A1F | 主色 |

## 声音

每一次数值变化一个 tick（每帧最多一个，越往后越轻越亮，最后连成一片），一条 riser 和一个反向吸气收在砸下那一帧；砸下是四层叠在同一帧：`impact_big` + `sub_drop` + `hit` + 一丝 `glitch`，之后余烬 `shimmer` 和噼啪声，标签出现一个 `pop_soft`；底下一层随计数收紧的低频隆隆声。成片 −21.8 LUFS / 峰值 −6.2 dBTP。

## 重渲

```bash
cd library/card-number-impact/src
python3 build.py stills --times 0.9 1.5 1.72 3.5
python3 build.py render --out <输出目录>
```

字体：思源黑体 Medium / Bold / Heavy（`fonts/`；Heavy 不在 `scripts/get_fonts.sh` 默认下载列表里，下载地址见 `fonts/SOURCES.md`）。

## 文件

`src/number_impact.js`（组件）、`src/sound.py`、`src/build.py`、`src/shotkit.py`（各条目共用）。
