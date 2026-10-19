using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;

const int SampleRate = 44100;
const int Channels = 1;
const int DurationSeconds = 600;
const long ExpectedFrames = 26_460_000L;
const int EnvelopePeriodSeconds = 2;

string workDir = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "tests", "VoxLoom.LoadTest", "work"));
// Fallback: resolve relative to current directory if BaseDirectory layout differs.
string repoRootGuess = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory()));
string altWork = Path.Combine(repoRootGuess, "tests", "VoxLoom.LoadTest", "work");
if (!Directory.Exists(Path.GetDirectoryName(workDir)))
{
    workDir = altWork;
}
Directory.CreateDirectory(workDir);

string bigWavPath = Path.Combine(workDir, "big.wav");
string reportPath = Path.GetFullPath(Path.Combine(workDir, "..", "..", "..", "docs", "LOADTEST.md"));
Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);

var report = new StringBuilder();

try
{
    // ------------------------------------------------------------------
    // P0 环境
    // ------------------------------------------------------------------
    var p0StartMem = GC.GetTotalMemory(false);
    DateTime runTime = DateTime.Now;
    var osVersion = Environment.OSVersion;
    int procCount = Environment.ProcessorCount;
    long totalAvailableMem = GC.GetGCMemoryInfo().TotalAvailableMemoryBytes;
    string frameworkDesc = RuntimeInformation.FrameworkDescription;
    var p0EndMem = GC.GetTotalMemory(false);

    Console.WriteLine($"[P0] runTime={runTime:O} os={osVersion} procs={procCount} mem={totalAvailableMem} fw={frameworkDesc}");

    // ------------------------------------------------------------------
    // P1 大音频文件
    // ------------------------------------------------------------------
    var rng = new Random(42);
    float[] samples = new float[ExpectedFrames];
    const double twoPi = Math.PI * 2.0;
    double freq = 440.0;
    double phase = 0.0;
    double phaseStep = twoPi * freq / SampleRate;
    long envPeriodFrames = (long)EnvelopePeriodSeconds * SampleRate;

    for (long i = 0; i < ExpectedFrames; i++)
    {
        double noise = rng.NextDouble() * 2.0 - 1.0;
        double sine = Math.Sin(phase);
        phase += phaseStep;
        if (phase > twoPi) phase -= twoPi;

        long posInPeriod = i % envPeriodFrames;
        double envelope = posInPeriod < envPeriodFrames / 2 ? 1.0 : 0.0;

        samples[i] = (float)((0.7 * sine + 0.3 * noise) * envelope * 0.9);
    }

    AudioClip bigClip = new AudioClip(SampleRate, Channels, samples);

    var p1WriteStartMem = GC.GetTotalMemory(false);
    var swWrite = Stopwatch.StartNew();
    WavWriter.Write(bigWavPath, bigClip);
    swWrite.Stop();
    var p1WriteEndMem = GC.GetTotalMemory(false);

    long fileBytes = new FileInfo(bigWavPath).Length;
    double fileMb = fileBytes / (1024.0 * 1024.0);
    double writeThroughputMbps = fileMb / swWrite.Elapsed.TotalSeconds;

    var p1ReadStartMem = GC.GetTotalMemory(false);
    var swRead = Stopwatch.StartNew();
    AudioClip readBack = WavReader.Read(bigWavPath);
    swRead.Stop();
    var p1ReadEndMem = GC.GetTotalMemory(false);

    if (readBack.Frames != ExpectedFrames)
        throw new InvalidOperationException($"Frames mismatch: expected {ExpectedFrames}, got {readBack.Frames}");
    if (readBack.SampleRate != SampleRate)
        throw new InvalidOperationException($"SampleRate mismatch: expected {SampleRate}, got {readBack.SampleRate}");

    float[] rb = readBack.Samples;
    int[] checkIdx = new[] { 0, (int)(ExpectedFrames / 2), (int)(ExpectedFrames - 1) };
    // WavWriter 以 16-bit PCM 写出，量化步长 1/32768 ≈ 3.05e-5，roundtrip 按 1 LSB 加余量校验。
    const float pcmTolerance = 4e-5f;
    foreach (int idx in checkIdx)
    {
        float diff = Math.Abs(rb[idx] - samples[idx]);
        if (diff >= pcmTolerance)
            throw new InvalidOperationException($"Sample roundtrip mismatch at idx {idx}: wrote={samples[idx]}, read={rb[idx]}, diff={diff}");
    }

    Console.WriteLine($"[P1] write={swWrite.Elapsed.TotalMilliseconds:F2}ms read={swRead.Elapsed.TotalMilliseconds:F2}ms bytes={fileBytes} throughput={writeThroughputMbps:F2}MB/s");

    // ------------------------------------------------------------------
    // P2 波形金字塔
    // ------------------------------------------------------------------
    float[] mono = bigClip.GetMonoSamples();
    var p2StartMem = GC.GetTotalMemory(false);
    var swLod = Stopwatch.StartNew();
    WaveformLod lod = new WaveformLod(mono);
    swLod.Stop();
    var p2EndMem = GC.GetTotalMemory(false);

    int levels = lod.Levels;
    int level0Buckets = lod.GetBucketCount(0);
    double p2MemDeltaMb = (p2EndMem - p2StartMem) / (1024.0 * 1024.0);

    // 200 次随机 GetPeaks(level, start, 64)
    var rngPeaks = new Random(42);
    int queryCount = 200;
    int queryLen = 64;
    var peakTimes = new double[queryCount];
    int maxStart = Math.Max(1, level0Buckets - queryLen);
    for (int q = 0; q < queryCount; q++)
    {
        int start = rngPeaks.Next(0, maxStart);
        var swQ = Stopwatch.StartNew();
        var _ = lod.GetPeaks(0, start, queryLen);
        swQ.Stop();
        peakTimes[q] = swQ.Elapsed.TotalMilliseconds;
    }

    Array.Sort(peakTimes);
    double p50 = Percentile(peakTimes, 0.50);
    double p95 = Percentile(peakTimes, 0.95);

    Console.WriteLine($"[P2] levels={levels} buckets0={level0Buckets} memDelta={p2MemDeltaMb:F2}MB build={swLod.Elapsed.TotalMilliseconds:F2}ms p50={p50:F4}ms p95={p95:F4}ms");

    // ------------------------------------------------------------------
    // P3 批量转写对齐
    // ------------------------------------------------------------------
    int wordCount = 3000;
    double totalSeconds = 600.0;
    var rngWords = new Random(42);
    var words = new List<TranscriptWord>(wordCount);
    for (int i = 0; i < wordCount; i++)
    {
        double slot = totalSeconds * i / wordCount;
        double jitter = (rngWords.NextDouble() - 0.5) * (totalSeconds / wordCount) * 0.5;
        double startS = Math.Max(0.0, slot + jitter);
        double endS = Math.Min(totalSeconds, startS + (totalSeconds / wordCount) * 0.8);
        words.Add(new TranscriptWord(
            $"词{i}",
            TimeSpan.FromSeconds(startS),
            TimeSpan.FromSeconds(endS),
            0.9f));
    }
    TranscriptDoc rough = new TranscriptDoc(words, TimeSpan.FromMinutes(10));

    var swAlign = Stopwatch.StartNew();
    TranscriptDoc refined = RuleBasedAligner.Refine(bigClip, rough);
    swAlign.Stop();

    int refinedCount = refined.Words.Count;

    Console.WriteLine($"[P3] words={refinedCount} align={swAlign.Elapsed.TotalMilliseconds:F2}ms");

    // ------------------------------------------------------------------
    // P4 批量转写导入
    // ------------------------------------------------------------------
    int importWords = 5000;
    var sb = new StringBuilder();
    for (int i = 0; i < importWords; i++)
    {
        if (i > 0) sb.Append(' ');
        sb.Append('词').Append(i);
    }
    string plainText = sb.ToString();

    var swImport = Stopwatch.StartNew();
    TranscriptDoc imported = TranscriptImporter.ParsePlainText(plainText, TimeSpan.FromMinutes(10));
    swImport.Stop();

    int importedCount = imported.Words.Count;

    Console.WriteLine($"[P4] importedWords={importedCount} import={swImport.Elapsed.TotalMilliseconds:F2}ms");

    // ------------------------------------------------------------------
    // P5 写报告
    // ------------------------------------------------------------------
    // 检查 .gitignore
    string gitignorePath = Path.GetFullPath(Path.Combine(workDir, "..", "..", "..", ".gitignore"));
    string gitignoreStatus = "未找到 .gitignore 文件";
    if (File.Exists(gitignorePath))
    {
        string gi = File.ReadAllText(gitignorePath);
        bool ignoresWork = gi.Contains("work/") || gi.Contains("work\\");
        bool ignoresWav = gi.Contains("*.wav");
        if (ignoresWork || ignoresWav)
            gitignoreStatus = $"已忽略（work/={ignoresWork}, *.wav={ignoresWav}）";
        else
            gitignoreStatus = "未忽略 work/ 或 *.wav（本轮未擅自修改 .gitignore，由编排者决定）";
    }

    report.AppendLine("# VoxLoom 真实负载验证报告（2026-10-19）");
    report.AppendLine();
    report.AppendLine("## 测试方法（各阶段数据规模一句话）");
    report.AppendLine();
    report.AppendLine($"- P0 环境：读取运行时/OS/CPU/可用内存/Framework 描述。");
    report.AppendLine($"- P1 大音频文件：合成 {DurationSeconds} 秒 {SampleRate}Hz 单声道（{ExpectedFrames} 采样），WAV 写入 + 读回校验。");
    report.AppendLine($"- P2 波形金字塔：对 {ExpectedFrames} 采样构建 WaveformLod，level 0 随机查询 {queryCount} 次 GetPeaks(len={queryLen})。");
    report.AppendLine($"- P3 批量转写对齐：{wordCount} 个词，RuleBasedAligner.Refine 全量对齐。");
    report.AppendLine($"- P4 批量转写导入：{importWords} 词纯文本，TranscriptImporter.ParsePlainText 解析。");
    report.AppendLine();
    report.AppendLine("## 诚实边界（必读）");
    report.AppendLine();
    report.AppendLine("- 本轮合成音频为 440Hz 正弦 + 固定种子噪声 + 每 2 秒有声/静音包络，属合成信号，非真实语音；VAD/对齐行为不代表真实播客。");
    report.AppendLine("- 单进程串行执行，未做并发验证。");
    report.AppendLine("- 机器配置为本 VM 独有，结果不可直接外推至其他环境。");
    report.AppendLine("- ffmpeg/压缩格式解码路径未测，本轮只走 WAV 纯托管路径。");
    report.AppendLine("- WAV 为 16-bit PCM（WavWriter 写死），roundtrip 存在量化误差（1 LSB ≈ 3.05e-5），校验按 4e-5 容差，非无损。");
    report.AppendLine("- 单数组上限 114MB（约 3000 万 float）为本 VM 内存红线所限。");
    report.AppendLine();
    report.AppendLine("## 机器信息（P0 实测值）");
    report.AppendLine();
    report.AppendLine($"- 运行时间：{runTime:yyyy-MM-dd HH:mm:ss}");
    report.AppendLine($"- OS：{osVersion}");
    report.AppendLine($"- 逻辑处理器数：{procCount}");
    report.AppendLine($"- GC 可用内存：{totalAvailableMem} 字节（{totalAvailableMem / (1024.0 * 1024.0):F2} MB）");
    report.AppendLine($"- Framework：{frameworkDesc}");
    report.AppendLine();
    report.AppendLine("## 各阶段实测");
    report.AppendLine();
    report.AppendLine("| 阶段 | 数据量 | 耗时 | 吞吐/关键指标 |");
    report.AppendLine("| --- | --- | --- | --- |");
    report.AppendLine($"| P1 WAV 写入 | {ExpectedFrames} 采样 / {fileMb:F2} MB | {swWrite.Elapsed.TotalMilliseconds:F2} ms | {writeThroughputMbps:F2} MB/s |");
    report.AppendLine($"| P1 WAV 读回 | {readBack.Frames} 帧 | {swRead.Elapsed.TotalMilliseconds:F2} ms | Frames={readBack.Frames}, SR={readBack.SampleRate} |");
    report.AppendLine($"| P2 波形金字塔构建 | {ExpectedFrames} 采样 | {swLod.Elapsed.TotalMilliseconds:F2} ms | Levels={levels}, Buckets(0)={level0Buckets}, MemDelta={p2MemDeltaMb:F2} MB |");
    report.AppendLine($"| P2 GetPeaks 查询 | {queryCount} 次 × len {queryLen} | p50={p50:F4} ms / p95={p95:F4} ms | level=0 |");
    report.AppendLine($"| P3 对齐 | {wordCount} 词 | {swAlign.Elapsed.TotalMilliseconds:F2} ms | 输出词数={refinedCount} |");
    report.AppendLine($"| P4 导入 | {importWords} 词 | {swImport.Elapsed.TotalMilliseconds:F2} ms | 解析词数={importedCount} |");
    report.AppendLine();
    report.AppendLine("## 结论");
    report.AppendLine();
    report.AppendLine($"本轮 P1–P4 全部阶段成功完成，无异常抛出。主要耗时集中在 WAV 写入/读回（{swWrite.Elapsed.TotalMilliseconds + swRead.Elapsed.TotalMilliseconds:F2} ms 合计）与 WaveformLod 构建（{swLod.Elapsed.TotalMilliseconds:F2} ms），对齐（{swAlign.Elapsed.TotalMilliseconds:F2} ms）与导入（{swImport.Elapsed.TotalMilliseconds:F2} ms）在本次数据规模下开销较小。");
    report.AppendLine();
    report.AppendLine("## 未测项清单");
    report.AppendLine();
    report.AppendLine("- 并发/多线程负载：未测。");
    report.AppendLine("- ffmpeg / 压缩格式（mp3/aac/ogg 等）解码路径：未测。");
    report.AppendLine("- 真实长播客（含多人对话、背景音乐、口音）端到端：未测。");
    report.AppendLine("- 桌面端渲染帧率：未测。");
    report.AppendLine();
    report.AppendLine("## 附：work/ 目录与 .gitignore 状态");
    report.AppendLine();
    report.AppendLine($"- 测试产物 work/big.wav 在程序结束时删除，保留 work/ 目录为空。");
    report.AppendLine($"- .gitignore 检查结果：{gitignoreStatus}");

    File.WriteAllText(reportPath, report.ToString(), new UTF8Encoding(false));
    Console.WriteLine($"[P5] report written: {reportPath}");

    // 清理 big.wav
    if (File.Exists(bigWavPath))
        File.Delete(bigWavPath);
    Console.WriteLine($"[P5] cleaned {bigWavPath}");

    return 0;
}
catch (Exception ex)
{
    Console.Error.WriteLine($"ERROR: {ex}");
    return 3;
}

static double Percentile(double[] sortedAscending, double p)
{
    if (sortedAscending.Length == 0) return 0.0;
    double rank = p * (sortedAscending.Length - 1);
    int lo = (int)Math.Floor(rank);
    int hi = (int)Math.Ceiling(rank);
    if (lo == hi) return sortedAscending[lo];
    double w = rank - lo;
    return sortedAscending[lo] * (1.0 - w) + sortedAscending[hi] * w;
}
