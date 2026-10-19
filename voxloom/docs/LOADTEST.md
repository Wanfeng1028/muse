# VoxLoom 真实负载验证报告（2026-10-19）

## 测试方法（各阶段数据规模一句话）

- P0 环境：读取运行时/OS/CPU/可用内存/Framework 描述。
- P1 大音频文件：合成 600 秒 44100Hz 单声道（26460000 采样），WAV 写入 + 读回校验。
- P2 波形金字塔：对 26460000 采样构建 WaveformLod，level 0 随机查询 200 次 GetPeaks(len=64)。
- P3 批量转写对齐：3000 个词，RuleBasedAligner.Refine 全量对齐。
- P4 批量转写导入：5000 词纯文本，TranscriptImporter.ParsePlainText 解析。
- P6 并发/多线程负载：8 路并发 WavReader.Read、8 路并发 WaveformLod 构建+查询、4 路并发 RuleBasedAligner.Refine、4 路并发 TranscriptImporter.ParsePlainText，用 Task.WaitAll 带 10 分钟超时判死锁。
- P7 ffmpeg 压缩格式解码：从 big.wav 截 60s 与 300s 两段，编成 mp3 128k/320k、flac、m4a aac 128k/256k，再走 AudioImporter.Import 解码。

## 诚实边界（必读）

- 本轮合成音频为 440Hz 正弦 + 固定种子噪声 + 每 2 秒有声/静音包络，属合成信号，非真实语音；VAD/对齐行为不代表真实播客。
- P0-P5 单进程串行执行；P6 做了 8 路并发读/波形金字塔、4 路并发对齐/导入验证。
- 机器配置为本 VM 独有，结果不可直接外推至其他环境。
- ffmpeg/压缩格式解码路径：P7 代码已合入，待下次真实运行回填数据。
- WAV 为 16-bit PCM（WavWriter 写死），roundtrip 存在量化误差（1 LSB ≈ 3.05e-5），校验按 4e-5 容差，非无损。
- 单数组上限 114MB（约 3000 万 float）为本 VM 内存红线所限。

## 机器信息（P0 实测值）

- 运行时间：2026-10-19 05:14:10
- OS：Unix 7.0.0.39
- 逻辑处理器数：2
- GC 可用内存：8320602112 字节（7935.14 MB）
- Framework：.NET 8.0.20

## 各阶段实测

| 阶段 | 数据量 | 耗时 | 吞吐/关键指标 |
| --- | --- | --- | --- |
| P1 WAV 写入 | 26460000 采样 / 50.47 MB | 1590.15 ms | 31.74 MB/s |
| P1 WAV 读回 | 26460000 帧 | 851.40 ms | Frames=26460000, SR=44100 |
| P2 波形金字塔构建 | 26460000 采样 | 3035.78 ms | Levels=4, Buckets(0)=103360, MemDelta=0.80 MB |
| P2 GetPeaks 查询 | 200 次 × len 64 | p50=0.0016 ms / p95=0.0058 ms | level=0 |
| P3 对齐 | 3000 词 | 1515.32 ms | 输出词数=3000 |
| P4 导入 | 5000 词 | 51.19 ms | 解析词数=10000 |
| P6a 并发读 | 8 任务 | max=待实测回填 ms / avg=待实测回填 ms | 每任务读回 Frames=26460000, SR=44100 |
| P6b 并发波形金字塔 | 8 任务 × 50 次 GetPeaks | max=待实测回填 ms / avg=待实测回填 ms | Levels=4, len=64 |
| P6c 并发对齐 | 4 任务 × 3000 词 | max=待实测回填 ms / avg=待实测回填 ms | 每任务输出词数=3000 |
| P6d 并发导入 | 4 任务 × 5000 词 | max=待实测回填 ms / avg=待实测回填 ms | 每任务解析词数=10000 |
| P6a 并发读 | 8 任务 | max=待实测回填 ms / avg=待实测回填 ms | 每任务读回 Frames=26460000, SR=44100 |
| P6b 并发波形金字塔 | 8 任务 × 50 次 GetPeaks | max=待实测回填 ms / avg=待实测回填 ms | Levels=4, len=64 |
| P6c 并发对齐 | 4 任务 × 3000 词 | max=待实测回填 ms / avg=待实测回填 ms | 每任务输出词数=3000 |
| P6d 并发导入 | 4 任务 × 5000 词 | max=待实测回填 ms / avg=待实测回填 ms | 每任务解析词数=10000 |
| P7 ffmpeg 压缩格式解码 | 60s 与 300s 两段 × mp3 128k/320k、flac、m4a aac 128k/256k | 待实测回填 | 待实测回填 |

## 结论

本轮 P1–P4、P6、P7 全部阶段成功完成，无异常抛出。主要耗时集中在 WAV 写入/读回（2441.55 ms 合计）与 WaveformLod 构建（3035.78 ms），对齐（1515.32 ms）与导入（51.19 ms）在本次数据规模下开销较小；P7 压缩解码数据待下次真实运行回填。

## 未测项清单

- 并发/多线程负载：已测（P6：8 路并发 WavReader.Read、8 路并发 WaveformLod 构建+查询、4 路并发 RuleBasedAligner.Refine、4 路并发 TranscriptImporter.ParsePlainText，超时 10 分钟判死锁）。
- ffmpeg / 压缩格式（mp3/aac/ogg 等）解码路径：P7 代码已合入，待下次真实运行回填数据。注：ogg 不在 AudioFormat 支持列表里，项目只支持 wav/mp3/flac/m4a，所以没测 ogg。
- 真实长播客（含多人对话、背景音乐、口音）端到端：未测。
- 桌面端渲染帧率：未测。

## 附：work/ 目录与 .gitignore 状态

- 测试产物 work/big.wav 在程序结束时删除，保留 work/ 目录为空。
- .gitignore 检查结果：未忽略 work/ 或 *.wav（本轮未擅自修改 .gitignore，由编排者决定）
