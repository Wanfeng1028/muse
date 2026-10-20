# audio/ · 小鹿动效系统的声音库（xlaudio）

**分工：BGM 来自剪映曲库；代码合成负责音效和声音标识。** 本目录把《在我开口之前》的配乐合成器（用户认可：−14 LUFS、真峰值 −1.3 dBTP、55 个卡点全部对齐）拆成可复用的库，去掉了那条片子专属的编排。所有音效和声音标识都由 Python 代码从数学上合成（振荡器、FM、加法合成、滤波噪声、合成冲激响应），不用采样、音色库、MIDI 音源或 AI 音乐服务，没有第三方授权问题，并且能逐采样对齐画面帧。

我们听不到声音。质量靠乐理、合成方式和测量保证（每个产物都有 ffmpeg ebur128 报告、频谱图、削波 / 直流 / 咔哒检查），**最终听感必须由用户人工验收**，清单在文末。

## 目录

```
audio/
  xlaudio/            库
    dsp.py            振荡器、FM（过采样）、加法合成、时变 SVF、合成混响 IR、压缩 / 真峰值限幅 / 软削波
    instruments.py    乐器与原始音色（crystal pluck、celesta、钟、FM 电钢、sub、鼓组、whoosh、riser …）
    sfx.py            音效注册表 + render_sfx（参数、种子、参考电平归一）+ 21 个通用音效
    motion.py         样片动作音效 5 个：enter / land / push / reveal / hit（同一音色家族）
    ident.py          声音标识：3 个两音动机候选，各有片头版和转场版
    cues.py           render_cues：分镜 sfx 字段 → 音效轨
    mix.py            mix_with_voice：人声处理 + 外部 BGM 闪避 + 母带 + 报告
    grid.py           卡点：BeatGrid（小节 / 拍 / 秒 / 帧换算）、BeatMap、读剪映 .beat
    score.py          参数化配乐底床（次要，停在 1 个预设 coldlight_ambient）
    meter.py          BS.1770-4 响度 / 真峰值（迭代用，报告以 ffmpeg 为准）
    analysis.py       ffmpeg ebur128、咔哒扫描、频谱图 / 电平图
    wavio.py          WAV 读写；其他格式和采样率交给 ffmpeg 解码
  cli.py              命令行
  sfx/CATALOG.md      音效与声音标识清单（由 cli.py catalog 生成）
  examples/           make_examples.py 与产物 out/
  tests/              pytest，40 项，约 13 s
```

依赖：Python 3.13、numpy、scipy、numba、matplotlib（只画图用）、pytest（只测试用）、PATH 上的 ffmpeg。本机都已具备，没有装任何新库（`requirements.txt` 只是记录）。首次运行 numba 编译约 10 s，缓存写在 `xlaudio/__pycache__/`。

## API

```python
import xlaudio as xa

y = xa.render_sfx('hit', seed=0, pitch=0, bright=0.6)     # (2, n) float64，48 kHz，已归一到参考电平
xa.list_sfx('motion')        # ['enter', 'land', 'push', 'reveal', 'hit']
xa.list_sfx('ident')         # 3 个候选 × 片头 / 转场
track = xa.render_cues(storyboard['sfx'], duration=42.5, out_path='sfx_track.wav')
report = xa.mix_with_voice('voice.wav', bgm_path, 'sfx_track.wav', 'final.wav', bgm_start=12.0)
grid = xa.BeatGrid(120, fps=30); grid.bbt(5, 1); grid.frame(grid.bar_time(4))
beats = xa.load_jianying_beat('path/to/track.beat')
res = xa.render_score('coldlight_ambient', duration=30, energy=[(0, .3), (16, .9)], sections={'drop': 16})
```

| 函数 | 说明 |
|---|---|
| `render_sfx(id, seed=0, normalize=True, gain_db=0, **params)` | 单个音效 / 标识。参数：`pitch` 半音、`bright` 0..1、`dur` 秒，以及各音效自己的参数（见 CATALOG）。未知参数报错，越界参数截断并警告。同一 (id, 参数, seed) 逐采样一致。 |
| `render_cues(cues, duration, sr=48000, out_path=None, return_log=False)` | cue 字段 `id`、`at`（秒）、`gain_db`、`pan`、`params`，可选 `seed`、`align`、`fps`，也接受 `kind` / `t` / `frame` / 顶层 `dur` / `pan: [from, to]`（静姐项目 timeline 写法）。输出正好 round(duration × sr) 个采样，默认写 32-bit float WAV（叠加不削波）。 |
| `mix_with_voice(voice, bgm, sfx, out_path, …)` | 见下文“人声混音”。返回报告 dict，`report_path=` 另存 JSON，`stems_dir=` 导出处理后的人声 / 闪避后的 BGM / 音效轨 / 闪避增益曲线。 |
| `BeatGrid(bpm, beats_per_bar=4, offset=0, fps=30)` | `beat_time`、`bar_time`、`bbt`（DAW 式 1 起算）、`bar_beat`、`snap`、`beats`、`downbeats`、`frame`、`table`（给分镜用的拍表，含帧号和量化误差）、`frame_error_ms`。`frame_locked_bpms(fps)` 列出拍点正好落在整帧上的速度（30 fps：120、112.5、100、90 …）。 |
| `BeatMap` / `load_jianying_beat(path)` | 显式拍点列表；剪映等剪辑软件能导出曲目的踩点分析文件（JSON：`time` 毫秒、`value` 拍位 1–4、`energy`），把路径传给这个函数即可。 |
| `render_score(...)` → `ScoreResult` | 次要功能，见下文。 |
| `analysis.analyze(wav, prefix, …)` | ebur128 + 检查 + 频谱图 / 电平图 + report.json。 |

命令行：`python3 cli.py list | sfx | cues | mix | score | grid | analyze | catalog`，用法见 `python3 cli.py -h`。

## 样片三件套

### 1. 五个动作音效（`motion.py`）

enter（元素入场）、land（落定 / 圆窗落位）、push（推近）、reveal（揭示 / 墨入纸转场）、hit（L3 强调落地）一一对应画面动作，用同一套材料合成：带通噪声“空气声”、crystal FM 拨弦 / celesta（D 大调五声音阶）、正弦鼓体与次低频、同一套合成板式 / 大厅混响。`pitch` 整族一起移调，一个视频里用同一个值。

对位规则（30 fps），详见 `sfx/CATALOG.md`：

- whoosh 型（enter、push）：比画面动作开始提前 3–4 帧。cue 写 `"align": "motion"`，`at` 填动作开始时间，渲染器按 `lead_frames` 自动提前（enter 3.5 帧，push 3 帧）；`dur` 设成动作时长加提前量，声音在到位那一帧到峰。
- impact 型（land、hit）：瞬态与落定同帧，`at` 填落定帧。
- reveal：锚点 0.35 s，写 `"align": "anchor"`，`at` 填墨迹触纸 / 新画面开始出现的那一帧。

### 2. 声音标识（`ident.py`）

三个候选，都是“短拾音 → 长落点”的两音动机；每个候选有片头版（约 2.4–2.8 s，完整尾音，参考 M-max −17 LUFS）和转场版（约 0.95 s，同样两个音间隔收紧到 90 ms，加一道快速空气声，参考 M-max −21 LUFS）。音程和音色两版一致，所以片头和转场听起来是同一个品牌。

| 候选 | 动机 | 音色 | 片头 id / 转场 id |
|---|---|---|---|
| A 晶光 | A5 → E6 上行纯五度，开阔、冷静 | crystal FM 拨弦 + 落点钟声 + 高音颗粒 + 次低频（《在我开口之前》同一套音色） | `ident_crystal` / `ident_crystal_trans` |
| B 暖光 | A5 → F#6 上行大六度，甜、友好 | celesta + FM 电钢底 + 轻钟 | `ident_warm` / `ident_warm_trans` |
| C 小鹿跳 | A5 → D6 上行纯四度，滑音跳上落点 | 木槌 + 泡泡 pop + 附点八分回声 | `ident_hop` / `ident_hop_trans` |

落点（第二个音）是锚点：片头版在 0.45 s，转场版在 0.20 s，cue 用 `"align": "anchor"` 对准 Logo 落定帧或剪辑点。

### 3. 人声混音（`mix.py`）

`mix_with_voice(voice, bgm, sfx, out_path, …)`：

1. **人声**：先测输入的 Integrated LUFS、真峰值、LRA（ffmpeg ebur128），再做 70 Hz 高通 → 相位旋转器（5 节全通，120–500 Hz，只改相位不改频谱，把尖的声门脉冲变对称；测试人声的峰值响度比降了 4.5 dB）→ 增益到 −16 LUFS → 压缩（高于 −12 dBFS 3:1，2 ms / 80 ms）→ 回到 −16 LUFS。
2. **BGM**：用你有权使用的任意音频文件（.mp3/.wav 等，ffmpeg 能解码的格式都行）。`bgm_start` 选从歌的哪一秒开始（从中间开始会自动 0.4 s 淡入），结尾 1.5 s 淡出；比人声短时补静音并在报告里警告，或 `bgm_fit='loop'` 以 2 s 交叉淡化循环。先测所用片段的响度，再把它放到“比人声低 `bgm_rel_lu`（默认 6 LU）”，所以 −9 LUFS 的商业母带和 −20 LUFS 的轻音乐都能直接用。
3. **闪避**：人声 150–4000 Hz 频段 10 ms RMS 高于（−16 − 22）dBFS 视为有声；有声后保持 `hold_ms`（250），提前 `lookahead_ms`（80）开始压，`attack_ms`（60）/ `release_ms`（600）平滑。BGM 压 `duck_db`（−6 dB），另在 300 Hz–4 kHz 再挖 `pocket_db`（−3 dB）给人声让位。短于约 0.3 s 的停顿不回弹，避免“抽吸感”。
4. **母带**：求和 → 25 Hz 高通 → 静态增益 → 带限削波（4× 过采样软削波，只把 8 kHz 以下的修正量加回去，不产生高频毛刺；只有最尖的声门峰会碰到）→ 前瞻真峰值限幅（天花板 −1.3 dBTP）→ 迭代到目标响度（默认 −14 LUFS）→ 用 ffmpeg 复测，真峰值高于 −1.0 dBTP 就降天花板重做。
5. **报告**：输入人声测量、各级增益和压缩 / 削波 / 限幅量、BGM 源响度与施加增益、闪避时间占比、说话时人声比 BGM 高多少 LU、输出 ffmpeg 测量。

## 卡点

`BeatGrid` 处理固定速度的网格（自己合成的音乐，或已知速度的曲子）：小节 / 拍 ↔ 秒 ↔ 帧，拍点量化误差（120 / 100 BPM @ 30 fps 为 0 ms；96 BPM 有拍点正好落在两帧中间，最大 16.7 ms，即半帧），`table()` 直接给分镜用。剪映曲库音乐优先读剪映自己缓存的 `.beat` 踩点文件（`load_jianying_beat`）。

还没做的：对任意外部音乐做节拍检测。以后的做法，二选一：
- 接 librosa：`librosa.beat.beat_track` + `librosa.onset.onset_strength`，装在 `audio/.venv`，写进 requirements；
- 自研（不加依赖）：频谱通量起音包络 → 自相关估速度（限 60–180 BPM，偏好 30 fps 整帧速度）→ 动态规划选拍（Ellis 2007）→ 用低频能量和和弦变化判小节线；再用剪映 `.beat` 当标注做回归测试。

## 配乐底床（次要）

`render_score(preset, duration, bpm, key, energy, sections, loop)` 只保留 1 个预设 `coldlight_ambient`（冷光氛围电子：加法合成 pad、crystal pluck 琶音、sub、软鼓组，和声 i(add9)–VImaj9–iv9–Vsus4），停在现有进度：能量曲线控制层次密度和亮度，段落标记（`drums_in` / `build` / `drop` / `breakdown`，自动吸附到小节线）控制进鼓、蓄力、drop、抽空；`loop=True` 生成可无缝循环的整周期；`ScoreResult.meta` 给出每小节的时间 / 采样 / 帧 / 和弦，`cut(bar_from, bar_to)` 按小节线裁剪。

## 示例与自检

```bash
python3 examples/make_examples.py all --voice VOICE_20S.wav \
    --bgm path/to/your_bgm.mp3 --bgm-start 12
python3 -m pytest tests -q -p no:cacheprovider
```

2026-09-26 实测（ffmpeg 8.0 ebur128；每项都有 `examples/out/<名>.ebur128.txt`、`.report.json`、`.spectrogram.png`、`.levels.png`）：

| 产物 | 内容 | I (LUFS) | TP (dBTP) | 检查 |
|---|---|---|---|---|
| `sfx_sampler.wav` | 32 个 id × 2 个变体，间隔 0.5 s，111.9 s，保持参考电平 | −23.7 | −8.1 | 无削波；直流 −122 dBFS；咔哒 0；首尾为 0 |
| `score_coldlight_ambient_30s.wav` | 30 s，8 s 进鼓、16 s drop、24 s 抽空、26 s 收束 | −14.0 | −2.0 | 无削波；直流 −104 dBFS；咔哒 0；LRA 2.3 |
| `score_coldlight_ambient_loop8bars.wav` | 8 小节无缝循环，16 s | −14.0 | −2.5 | 接缝处台阶 0.011，低于正常采样差 99.9 分位 0.177；接缝咔哒 0 |
| `mix_jianying.wav` | 19 号片口播 0–20 s + 剪映曲库曲目（从 12 s 起）闪避 + 5 个动作音效 | −14.0 | −1.3 | 无削波；直流 −117 dBFS；混音引入的咔哒 0（测到的 3 处都在原人声里）；LRA 2.6 |

混音例子的关键数据：人声输入 −25.4 LUFS / −3.6 dBTP（峰值响度比 21.9 dB，很尖）；相位旋转 −4.5 dB，压缩最大 5.8 dB；BGM 源片段 −9.0 LUFS / +1.7 dBTP，施加 −13.0 dB；说话时人声高于 BGM 12.9 LU，闪避时间占 98%（这段几乎没有长停顿）；母带带限削波活动 40 ms，限幅最大 2.5 dB，超过 3 dB 的时间 0 ms。

`examples/out/*.wav` 和 stems 由代码随时重建，已写进 `.gitignore`：混音里有出镜者的口播和剪映曲库音乐，不进仓库。

## 已知限制

- 没有人耳试听，音色好坏、电平平衡、标识是否好记，都只能由用户判断。
- 音效参考电平按“人声 −16 LUFS”设计，是推算值；第一次正式用时按听感整体调 `gain_db`，调好的值应回写到 `sfx.py` 的 `ref`。
- 闪避靠电平判断有无人声，不区分人声和其他响声；口播里有长段背景噪声时要调 `vad_rel_db`。
- 19 号片候选音轨本身有 5–8 处宽带瞬态（嘴音或剪口），混音器不处理，也不做降噪、去齿音、去口水音。
- 对外部 BGM 不做节拍检测（只读剪映 `.beat`）；BGM 比人声短时默认补静音。
- 配乐只有 1 个预设，停在现有进度，没有打磨。

## 人工试听清单（用户）

1. `examples/out/sfx_sampler.wav` 0.3–19.3 s：5 个动作音效（enter、land、push、reveal、hit，各两个变体）是否像同一家族，和画面动作的对应是否贴切，有没有刺耳或发闷。
2. 同一文件 19.8–47.0 s：3 个声音标识候选（晶光 / 暖光 / 小鹿跳，片头版和转场版），选一个，或者说出想要的方向。
3. `examples/out/mix_jianying.wav`：BGM 在说话时的音量合不合适（现在比人声低约 13 LU）、停顿处 BGM 回来的速度、5 个音效相对人声的响度、人声有没有被处理出“挤压感”或失真（重点听 0.5–3 s 的重音）。
4. 其余通用音效（拼盘 47.5 s 以后）只需抽查有没有明显难听的。
5. `score_coldlight_ambient_30s.wav`：只在以后要用自有配乐时再听。

## 来源与许可

- 合成器源自《在我开口之前》配乐（`dsp.py`、`instruments.py`、`mix.py`、`meter.py`、`analysis.py` 的算法沿用并泛化），全部为本项目代码合成，无第三方权利。
- 剪映曲库音乐由用户的剪映会员授权用于小红书、抖音、视频号；本库只读取本机缓存，不复制进仓库。
- 不使用 Suno、Udio 或任何付费音乐服务。
