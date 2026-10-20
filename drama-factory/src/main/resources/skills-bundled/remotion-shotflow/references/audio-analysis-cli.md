# 本地音轨测量工具

用 `scripts/analyze_audio.py` 从本地视频或纯音频生成候选时间点，供后续试听与画面核对。它分析首条音轨的混合信号，不识别具体音效，不确认音乐主拍，不把波峰自动转换成已确认 cue。

## 运行

需要现有 Python 3.11+、NumPy、SciPy、PATH 中的 `ffmpeg` / `ffprobe`。只有 `--plot` 才需要 Matplotlib。缺失依赖时退出并列出名称；脚本不安装软件、不访问网络、不上传或改写输入。FFmpeg 的协议白名单限制为本地 `file,pipe`。

```bash
python3 "$SKILL_DIR/scripts/analyze_audio.py" \
  --input "/absolute/path/reference.mp4" \
  --out "/absolute/path/research/audio/reference"

# 可选图表；同样接受 .wav、.mp3、.m4a 等纯音频
python3 "$SKILL_DIR/scripts/analyze_audio.py" \
  --input "/absolute/path/music.wav" \
  --out "/absolute/path/research/audio/music" --plot
```

`SKILL_DIR` 指实际 skill 文件夹。`--out` 必须是不存在的新目录；重跑请换用新目录，脚本拒绝覆盖旧结果。分析先在同级临时目录完成，成功后一次提交到目标目录；解码、计算或绘图失败会清理临时文件，不留下混合新旧内容的成功结果。`analysis.json.artifacts` 列出本次生成的文件。

仅支持整轨分析：脚本从起点完整解码，以避免压缩格式 seek、codec delay 与裁切基准混淆。先分析全轨，再按时间筛选 JSON。若只能提供已剪片段，记录该片段对应原片的偏移；本工具无法自行恢复剪掉的原始时间。它面向短参考片，会将音轨解码到内存；长录音应先制定带时间映射的分段方案。

## 输出与状态

| 文件 | 用途 |
|---|---|
| `analysis.json` | 来源 SHA-256、工具版本、原声道电平、时间基准、测量方法、候选时间点及周期假设 |
| `probe.json` | 原容器与各流的元数据；视频不是必需条件 |
| `timing-probe.json` | 首包/首个解码帧、帧数、时间戳间断证据；有音轨时产生 |
| `envelope.json` | 约 50 ms 一点的 RMS/频谱变化包络；不用于精确定位峰值 |
| `overview.png` | `--plot` 时的图表；橙线只代表待核对候选 |

`status` 决定如何继续：

- `measured`：可审阅候选；候选为空也是有效结果。短于 5 秒不计算周期候选，短于 8 秒不计算局部周期窗。
- `digital_silence`：当前文件原采样率、原声道数解码后的全部样本**精确为零**。不能据此推断平台其他版本也静音。
- `no_audio_stream`：没有音轨，不等同于存在静音音轨。
- `mono_downmix_cancellation`：原声道非零，mono 抵消为零；也包含原双声道精确相反、混音后仅剩很小浮点残差的情况。停止以 mono 候选推断原声道静音，改为逐声道核对。严重但不精确的抵消会写入 `warnings`。
- `timing_unavailable` / `timestamp_discontinuity_unsupported`：时间信息缺失或解码帧 PTS 不连续，保留原声道与时序证据，但不输出假定连续的 cue 时间轴。
- `empty_decoded_audio` / `too_short_for_resampling`：没有原始解码样本，或极短音频经过重采样后没有样本。不是异常 BPM，也不证明静音。
- `invalid_nonfinite_decoded_samples`：出现 NaN/Infinity，不继续数值推断。

正常可分类结果返回退出码 0；参数、依赖或解码失败返回非零。自动流程须检查 `status`，不能只看退出码。

典型候选字段如下；数字只是格式示例：

```json
{
  "time_s": 1.247166,
  "review_status": "unreviewed",
  "strength_vs_normalizer": 1.84,
  "strength_vs_clip_max": 0.63,
  "prominence_vs_normalizer": 1.7,
  "local_rms_dbfs": -14.2
}
```

`time_s` 与画面帧工具共用容器 presentation 时间基准：`first_decoded_audio_frame_pts - format.start_time + sample_offset`。`timing` 保留两者原始 PTS、`audio_offset_s`、`presentation_start_pts_s` 与 `origin_basis`。缺失 `format.start_time` 时回退 0，明确写为 `fallback_zero_missing_format_start_time` 且 `origin_verified=false`；这是一项需要结合播放器核对的假设，不能默认为已证实原点。FFmpeg 已应用音频 codec 元数据；不要再手工追加 AAC/MP3 延时，也不要把首包的负 priming PTS 当成首个可听样本。

## 数值解释

分析域为 22050 Hz mono；原声道另以原采样率核验，不用 mono 结果代替原声道静音证据。Hann STFT 窗 1024 样本（约 46.4 ms），步长 220 样本（约 10 ms），居中窗、边界补零，结果裁到真实解码尾部。**时间字段小数位数不是测量准确度**，短瞬态仍需要数十毫秒范围的试听和帧核对。

频谱变化取 80–10000 Hz 的 `log1p(100*abs(STFT))` 正向差分，减去 61 帧局部中位数，截到非负。默认按 p95 归一化；稀疏声音使 p95 接近零时改用最大值并在 `method.normalization` 写明。峰间隔约 120 ms；高度、突出度门限均写入 `method`。强度仅用于同片内部排序，不能跨片解释为响度大小。

低能量区间遵循 `RMS < min(-40 dBFS, 全片 RMS 包络 p95 - 25 dB)` 且连续至少 100 ms；原声道全零时门限为 -40 dBFS。另对候选与自相关使用不低于 -80 dBFS 的操作门限，避免把极小数值残差放大成节奏；它不是人耳可闻性判定。

周期分析将归一化频谱变化限幅到 3，再作去均值的归一化自相关；保留 45–220 BPM 等效周期的局部峰，并列半倍/双倍解释。局部窗 8 秒、步长 4 秒，至少 80% 帧低于门限则跳过。`normalized_autocorrelation_score` 是相关值，**不是概率、识别置信度或已确认 BPM**；没有候选也不能反推出“没有节奏”。

原声道 `null` dBFS 表示数字零，即负无穷；包络绘图中的 -160 dBFS 是显示下限。RMS 不是 LUFS，sample peak 不是 true peak；重采样或有损解码可以产生超过 0 dBFS 的浮点值，不能据此断定源视频削波。完成测量后仍需按 skill 的音画核对流程把候选、试听判断和设计选择分别记录。
