# 音效与声音标识清单（CATALOG）

> 本文件由 `python3 cli.py catalog` 从代码里的注册表生成，改音效请改 `xlaudio/*.py` 再重新生成，不要手改。
> 全部声音由 Python 代码合成（振荡器、FM、加法合成、滤波噪声、合成冲激响应），无采样、无音色库、无 AI 音乐服务，无第三方授权问题。48 kHz 立体声，同一组 (id, 参数, seed) 每次渲染逐采样一致。

## 怎么用

```python
import xlaudio as xa
y = xa.render_sfx('hit', seed=0, pitch=0, bright=0.6)        # (2, n) float64, 48 kHz
track = xa.render_cues([{'id': 'enter', 'at': 3.20, 'align': 'motion'},
                        {'id': 'land',  'at': 3.70},
                        {'id': 'reveal', 'at': 8.00, 'align': 'anchor', 'gain_db': -2}], duration=42.5)
```

cue 字段与分镜 JSON 的 `sfx` 字段一致：`id`、`at`（秒）、`gain_db`、`pan`（-1..1）、`params`；可选 `seed`、`align`、`fps`，也接受 `frame` 代替 `at`。

**对位规则（30 fps）**

- whoosh 型（enter、push、whoosh_*）：声音比画面动作开始提前 3–4 帧。写 `align: "motion"`，`at` 填动作开始的时间，渲染器按各音效的 `lead_frames` 自动提前（enter 3.5 帧、push 3 帧、whoosh_fast 3.5 帧、whoosh_mid 5 帧、whoosh_slow 10 帧）。
- impact 型（land、hit、impact_*、stamp、tock、clack）：瞬态与落定同帧。`at` 填落定那一帧，`align` 用默认的 `start`（或 `motion`，提前量为 0）。
- 有锚点的（reveal、ident_*）：写 `align: "anchor"`，`at` 填需要对齐的那一帧（墨迹触纸 / Logo 落定 / 剪辑点），锚点之前的预备声会自动排在前面。
- 结尾对齐的（riser、reverse_whoosh）：写 `align: "end"`，声音的结尾正好落在 `at`。
- `align: "peak"`：把最响的 10 ms 对准 `at`，适合手动对 whoosh。

**参考电平**：`gain_db = 0` 时，每个音效已归一到下表的参考值（短促瞬态用真峰值 TP，持续声用 400 ms 最大瞬时响度 M-max），按“人声 −16 LUFS”设计；`mix_with_voice` 母带阶段整体平移，比例不变。需要更响或更轻就调 `gain_db`。

**通用参数**：`pitch` 半音（整族一起移调时每个视频用同一个值）、`bright` 0..1 亮度、`dur` 秒、`seed` 随机种子（只影响噪声类细节）。

## 1. 样片动作音效（5 个，同一音色家族）

共同的合成材料：带通噪声“空气声” + crystal FM 拨弦 / celesta（D 大调五声音阶）+ 正弦鼓体与次低频 + 同一套合成板式 / 大厅混响。

| id | 用途 | 对位规则 | 锚点 / 提前 | 参考电平 | 默认时长 | 参数 |
|---|---|---|---|---|---|---|
| `enter` | 元素入场：卡片 / 文字 / 图标滑入、缩放进入 | whoosh 型：声音比元素开始移动提前 3–4 帧（align=motion 自动提前 3.5 帧）；dur = 入场动画时长 + 提前量，结尾的晶体轻音落在元素到位那一帧 | mark @ 0.30 s，提前 3.5 帧 | TP -15.0 dBTP | 0.90 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.15..0.8（默认 0.3）；`travel` -1.0..1.0（默认 0.3） |
| `land` | 落定：圆窗落位、卡片放下、元素停稳 | impact 型：与落定（位移结束、回弹之前）同帧，align=start 或 motion（提前量 0） | start | TP -12.0 dBTP | 0.90 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5） |
| `push` | 推近：镜头推进、画面放大到细节 | whoosh 型：比推镜开始提前 3 帧（align=motion）；dur = 推镜时长 + 3 帧，声音在推到位时到达峰值 | mark @ 0.70 s，提前 3.0 帧 | M-max -24.0 LUFS | 1.05 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.3..2.0（默认 0.7） |
| `reveal` | 揭示 / 墨入纸转场：新画面像墨一样晕开出现 | 锚点在 0.35 s：align=anchor 对准墨迹触纸 / 新画面开始出现的那一帧（之前 0.35 s 是吸入式预备） | mark @ 0.35 s | M-max -22.0 LUFS | 2.15 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.8..4.0（默认 1.8） |
| `hit` | L3 强调落地：关键结论 / 大字 / 数字砸下来 | impact 型：与强调元素落地同帧；需要蓄力时，在同一帧再放一个 reverse_whoosh（align=end） | start | TP -9.0 dBTP | 1.40 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5） |

合成方式：

- `enter`：上扬空气声（900→4200 Hz 带通噪声，峰值在 80%）+ 到位时的 A6 晶体轻拨 + 板式混响。
- `land`：D3 正弦鼓体（下滑 1.5×→1×）+ D2 次低频 + 25 ms 气流噪声 + D5 晶体轻拨与 85 ms 后的微弱回弹。
- `push`：两路向外展开的空气声（300→2400 Hz，峰值 88%）+ D3 起半个八度上升的滤波锯齿 + 板式混响。
- `reveal`：反向汇聚的预备气声 → 带通噪声“晕开”（中心频率下沉）+ D6 celesta + A5 晶体 + 高音颗粒 + D2 轻底，大厅混响。
- `hit`：110 Hz 鼓体 + 62→44 Hz boom + 6 ms 噪声脆击 + D6/A6 晶体双音 + F#6 轻钟，板式混响。

## 2. 声音标识（两音动机，3 个候选 × 片头 / 转场两版）

三个候选各是一个“短拾音 → 长落点”的两音动机。片头版保留完整尾音，转场版把两音间隔收紧到 90 ms、尾巴缩短并加一道快速空气声，音程和音色不变，所以两处听起来是同一个品牌。等用户试听后选定一个。

| id | 用途 | 对位规则 | 锚点 / 提前 | 参考电平 | 默认时长 | 参数 |
|---|---|---|---|---|---|---|
| `ident_crystal` | 候选「晶光」片头 / 落版标识音（两音动机完整版） | 落点（第二个音）在 0.45 s：align=anchor 对准 Logo / 标题落定那一帧；第一个音提前 0.16 s | mark @ 0.45 s | M-max -17.0 LUFS | 2.80 s | `pitch` -7.0..7.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`space` reverb amount 0..1 (default per candidate)（默认 None） |
| `ident_crystal_trans` | 候选「晶光」转场签名（同一两音动机缩短版） | 落点在 0.20 s：align=anchor 对准剪辑点；两音间隔 90 ms，下方快 whoosh 掠过 | mark @ 0.20 s | M-max -21.0 LUFS | 0.95 s | `pitch` -7.0..7.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`space` reverb amount 0..1 (default per candidate)（默认 None） |
| `ident_warm` | 候选「暖光」片头 / 落版标识音（两音动机完整版） | 落点（第二个音）在 0.45 s：align=anchor 对准 Logo / 标题落定那一帧；第一个音提前 0.18 s | mark @ 0.45 s | M-max -17.0 LUFS | 2.80 s | `pitch` -7.0..7.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`space` reverb amount 0..1 (default per candidate)（默认 None） |
| `ident_warm_trans` | 候选「暖光」转场签名（同一两音动机缩短版） | 落点在 0.20 s：align=anchor 对准剪辑点；两音间隔 90 ms，下方快 whoosh 掠过 | mark @ 0.20 s | M-max -21.0 LUFS | 0.95 s | `pitch` -7.0..7.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`space` reverb amount 0..1 (default per candidate)（默认 None） |
| `ident_hop` | 候选「小鹿跳」片头 / 落版标识音（两音动机完整版） | 落点（第二个音）在 0.45 s：align=anchor 对准 Logo / 标题落定那一帧；第一个音提前 0.20 s | mark @ 0.45 s | M-max -17.0 LUFS | 2.40 s | `pitch` -7.0..7.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`space` reverb amount 0..1 (default per candidate)（默认 None） |
| `ident_hop_trans` | 候选「小鹿跳」转场签名（同一两音动机缩短版） | 落点在 0.20 s：align=anchor 对准剪辑点；两音间隔 90 ms，下方快 whoosh 掠过 | mark @ 0.20 s | M-max -21.0 LUFS | 0.95 s | `pitch` -7.0..7.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`space` reverb amount 0..1 (default per candidate)（默认 None） |

合成方式：

- `ident_crystal`：A5 → E6 上行纯五度（开阔、冷静、科技感），crystal FM 拨弦 + 落点钟声 + 高音颗粒 + 次低频。
- `ident_crystal_trans`：同一两音动机，间隔收紧到 90 ms，尾巴缩到约 0.7 s，加快速空气声。
- `ident_warm`：A5 → F#6 上行大六度（甜、友好、温暖），celesta + FM 电钢底 + 轻钟 + 板式混响。
- `ident_warm_trans`：同一两音动机，间隔收紧到 90 ms，尾巴缩到约 0.7 s，加快速空气声。
- `ident_hop`：A5 → D6 上行纯四度，滑音跳上落点（“起跳”），木槌 + 泡泡 pop + 附点八分回声。
- `ident_hop_trans`：同一两音动机，间隔收紧到 90 ms，尾巴缩到约 0.7 s，加快速空气声。

## 3. 通用音效库（保留，不再扩充）

| id | 用途 | 对位规则 | 锚点 / 提前 | 参考电平 | 默认时长 | 参数 |
|---|---|---|---|---|---|---|
| `whoosh_fast` | 快切、卡片弹出、镜头急推、字幕飞入 | 峰值在 42% 处：比位移起点提前 3–4 帧（30 fps）放置，峰值落在速度最快的那一帧附近 | peak，提前 3.5 帧 | M-max -23.0 LUFS | 0.30 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.15..0.5（默认 0.3）；`travel` -1.0..1.0（默认 0.7）；`peak` 0.2..0.8（默认 0.42） |
| `whoosh_mid` | 常规转场、元素横移、画面推拉 | 峰值在 55% 处：比位移起点提前 4–6 帧放置；或用 align=peak 直接对准最快帧 | peak，提前 5.0 帧 | M-max -23.0 LUFS | 0.60 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.35..1.0（默认 0.6）；`travel` -1.0..1.0（默认 0.6）；`peak` 0.2..0.8（默认 0.55） |
| `whoosh_slow` | 大段落转场、场景切换、慢推镜 | 峰值在 60% 处：比转场起点提前 8–12 帧；用 align=peak 对准切点 | peak，提前 10.0 帧 | M-max -23.0 LUFS | 1.20 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.8..3.0（默认 1.2）；`travel` -1.0..1.0（默认 0.5）；`peak` 0.2..0.8（默认 0.6） |
| `reverse_whoosh` | 吸入式蓄力：落版、重击、标题出现之前的“吸气” | 末端对齐落点：用 align=end 让结尾正好落在 impact / 标题落定那一帧 | end | M-max -23.0 LUFS | 0.80 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.25..3.0（默认 0.8）；`width` 0.0..1.0（默认 0.8） |
| `tick` | 数字滚动、计数、进度点、时钟、逐项出现的小点 | 与数字跳变 / 元素出现同帧；连击时间隔 ≥ 2 帧，末尾一下接 tock 表示锁定 | start | TP -18.0 dBTP | 0.03 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.01..0.06（默认 0.022） |
| `tock` | 锁定、定格、数值确定、列表行落位 | 与“停住”的那一帧同帧（数字滚动结束、卡片停稳） | start | TP -15.0 dBTP | 0.07 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.04..0.2（默认 0.07） |
| `ui_click` | 按钮点击、鼠标点选、开关、光标确认 | 与按钮按下（缩放最小 / 颜色变化）同帧 | start | TP -16.0 dBTP | 0.04 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.012..0.08（默认 0.03） |
| `typing_key` | 打字、逐字出现的字幕、命令输入；heavy=1 为空格/回车/上屏 | 每个字出现的同一帧放一个（每帧最多一个）；词尾或回车用 heavy=1 | start | TP -18.0 dBTP | 0.02 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`heavy` 0..1（默认 0） |
| `pop_soft` | 图标 / 标签 / 气泡弹出，列表项出现，轻提示 | 与元素缩放到最大（回弹顶点）同帧；多个元素依次出现时间隔 3–5 帧并逐个 pitch +2 | start | TP -14.0 dBTP | 0.14 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.06..0.3（默认 0.12） |
| `pluck` | 关键词高亮、要点出现、音乐化的提示（可按音符排成旋律） | 与高亮出现同帧；多个要点依次出现时用和弦音（note=D5/F#5/A5） | start | TP -14.0 dBTP | 2.80 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.6..3.0（默认 1.6）；`note` note name or MIDI number（默认 A5）；`space` 0.0..1.0（默认 0.25） |
| `bell` | 章节开始、结论出现、“叮”一下的高光时刻、片尾 | 与标题 / 结论落定同帧；前面可接 reverse_whoosh（align=end 对同一帧） | start | TP -14.0 dBTP | 4.70 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 1.5..6.0（默认 3.5）；`note` note name or MIDI number（默认 A5）；`space` 0.0..1.0（默认 0.3） |
| `impact_soft` | 元素落定、卡片放下、轻量强调、文字砸到位 | 与落定（位移结束、回弹前）同帧 | start | TP -12.0 dBTP | 0.60 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.3..1.5（默认 0.6） |
| `impact_big` | 大标题落版、段落高潮、反转、drop 点 | 与画面重击同帧；前面接 riser 或 reverse_whoosh（align=end 同一帧） | start | TP -8.0 dBTP | 2.40 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.8..3.0（默认 1.8）；`tail` 0.0..1.0（默认 0.5） |
| `riser` | 蓄力、悬念、倒计时、进入高潮前 | 用 align=end：结尾对准 drop / impact 那一帧（结尾 20 ms 收口，接重击不会双响） | end | M-max -21.0 LUFS | 2.50 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.8..8.0（默认 2.5）；`octaves` 0.25..2.0（默认 1.0） |
| `sub_drop` | 低频下沉：重击的低频层、情绪下坠、黑场 | 与 impact 同帧叠用；单用时与画面下沉 / 黑场同帧。手机外放主要靠 bright 带出的谐波 | start | TP -14.0 dBTP | 1.40 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.5..3.0（默认 1.4） |
| `glitch` | 数字故障、信息错误、画面抖动 / 撕裂、AI 出错的梗 | 覆盖画面故障帧的起止（dur 设成故障持续时长）；与第一帧抖动同帧开始 | start | TP -14.0 dBTP | 0.30 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.08..1.5（默认 0.3）；`density` 0.0..1.0（默认 0.5） |
| `stamp` | 盖章、打勾确认、“已完成”、印记落下 | 与印章接触纸面（缩放到最小）同帧 | start | TP -10.0 dBTP | 0.16 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5） |
| `shimmer` | 闪光、魔法感、AI 生成完成、画面变亮、星点 | 与闪光 / 高亮开始同帧；dur 与闪光持续时间一致 | start | M-max -26.0 LUFS | 2.25 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.4..4.0（默认 1.2）；`density` 0.0..1.0（默认 0.5）；`root` pentatonic root (C..B, # b ok)（默认 D） |
| `blip` | 启动、界面出现、通知小点、数据点亮起 | 与元素出现第一帧同帧 | start | TP -16.0 dBTP | 0.22 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.1..0.5（默认 0.2） |
| `laser_zip` | 切分、扫描线、划线、裁切、快速下划线 | 与切线 / 扫描开始同帧；dur 等于划过所需时间 | start | TP -16.0 dBTP | 0.08 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`dur` 0.03..0.25（默认 0.05） |
| `clack` | 锁定、卡扣、选中框锁住、最终确认（zap>0 带电子尾巴） | 与锁定帧同帧 | start | TP -14.0 dBTP | 0.04 s | `pitch` -12.0..12.0（默认 0.0）；`bright` 0.0..1.0（默认 0.5）；`zap` 0.0..1.0（默认 0.0） |

合成方式：

- `whoosh_fast`：带通噪声扫频 + 低八度层 + 高频空气层，中心频率随包络先升后回落（掠过感），声像按 travel 移动。
- `whoosh_mid`：带通噪声扫频 + 低八度层 + 高频空气层，中心频率随包络先升后回落（掠过感），声像按 travel 移动。
- `whoosh_slow`：带通噪声扫频 + 低八度层 + 高频空气层，中心频率随包络先升后回落（掠过感），声像按 travel 移动。
- `reverse_whoosh`：两路不同种子的反向形状噪声从两侧向中间汇聚，指数上升后 4 ms 收尾。
- `tick`：2.1 kHz 木质 FM（比率 1.5，指数 10 ms 内归零）。
- `tock`：640 Hz 木块 FM + 半频正弦鼓体。
- `ui_click`：1.5–10 kHz 噪声瞬态 + 3.4 kHz 短音 + 220 Hz 微鼓体。
- `typing_key`：2–4 kHz 带通噪声 3–8 ms + 1.5 kHz 微音高；种子决定 ±5% 音高和 ±1.2 dB 电平，连打不机械。
- `pop_soft`：420→880 Hz 快速上滑正弦（气泡感）+ 少量二次谐波 + 2 ms 噪声点击。
- `pluck`：“在我开口之前”的 crystal pluck：FM 1:2，指数 4→0（约 80 ms），附 4 ms 噪声瞬态，可加合成板式混响。
- `bell`：FM 1:3.5 非谐波钟 + 基频拍频暖层 + 半频 hum，带合成大厅混响。
- `impact_soft`：70→48 Hz 短 boom + 110 Hz 鼓体下滑 + 低通噪声（亮度控制截止）。
- `impact_big`：50→35 Hz boom + 95 Hz 鼓体 + 低通噪声 + 高通噪声 crash 尾 + 合成房间混响。
- `riser`：带限锯齿上升 + 打开的低通滤波 + 噪声，指数渐强。
- `sub_drop`：88→32 Hz 指数下滑正弦，tanh 饱和（bright 越大谐波越多，手机外放越听得见）。
- `glitch`：8–45 ms 碎片随机拼接：带限方波、带通噪声、FM、4× 过采样的采样保持噪声、静音，每片随机声像。
- `stamp`：70 Hz / 80 ms 闷击 + 165 Hz 中低频层（手机可闻）+ 30 ms 纸面噪声。
- `shimmer`：高音区五声音阶正弦颗粒云（密度随时间衰减）+ 6–11 kHz 空气噪声 + 合成大厅混响。
- `blip`：FM 1:2 近正弦 D6 + 微小上滑（-40 cents→0）。
- `laser_zip`：5000→1800 Hz 正弦下扫 + 跟随带通噪声。
- `clack`：塑料 / 木质 clack（噪声 + FM 2.3 + 160 Hz 体）+ 可选下行 FM zap。

## 试听

`examples/out/sfx_sampler.wav`：按上面的顺序，每个 id 两个变体（默认参数 seed 0；第二组参数 seed 1），间隔 0.5 s，保持参考电平。时间点见 `examples/out/sfx_sampler.cues.json`。
