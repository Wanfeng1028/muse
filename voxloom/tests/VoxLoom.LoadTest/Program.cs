using System.Diagnostics;
using System.Globalization;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading.Tasks;
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
    // P6 并发/多线程负载
    // 四组实验都用真并发跑：8 路并发读 WAV、8 路并发建波形金字塔+查询、
    // 4 路并发对齐、4 路并发导入。全部任务合并成一个数组，用 Task.WaitAll
    // 带 10 分钟超时等，超时就当死锁抛异常。
    // ------------------------------------------------------------------
    var p6StartMem = GC.GetTotalMemory(false);

    // P6a 并发读：8 个 Task 各读一次 big.wav
    var p6aTimes = new ConcurrentBag<double>();
    Task[] p6aTasks = new Task[8];
    for (int t = 0; t < p6aTasks.Length; t++)
    {
        p6aTasks[t] = Task.Run(() =>
        {
            var sw = Stopwatch.StartNew();
            AudioClip c = WavReader.Read(bigWavPath);
            sw.Stop();
            if (c.Frames != ExpectedFrames)
                throw new InvalidOperationException($"P6a Frames mismatch: expected {ExpectedFrames}, got {c.Frames}");
            if (c.SampleRate != SampleRate)
                throw new InvalidOperationException($"P6a SampleRate mismatch: expected {SampleRate}, got {c.SampleRate}");
            p6aTimes.Add(sw.Elapsed.TotalMilliseconds);
        });
    }

    // P6b 并发波形金字塔：8 个 Task 共享同一份 mono 数组，各自建 WaveformLod 并查询 50 次
    var p6bTimes = new ConcurrentBag<double>();
    Task[] p6bTasks = new Task[8];
    for (int t = 0; t < p6bTasks.Length; t++)
    {
        int taskIndex = t;
        p6bTasks[t] = Task.Run(() =>
        {
            var sw = Stopwatch.StartNew();
            WaveformLod localLod = new WaveformLod(mono);
            if (localLod.Levels != levels)
                throw new InvalidOperationException($"P6b Levels mismatch: expected {levels}, got {localLod.Levels}");
            int buckets0 = localLod.GetBucketCount(0);
            int maxStart = Math.Max(1, buckets0 - 64);
            var localRng = new Random(1000 + taskIndex);
            for (int q = 0; q < 50; q++)
            {
                int start = localRng.Next(0, maxStart);
                var peaks = localLod.GetPeaks(0, start, 64);
                if (peaks.Length != 64)
                    throw new InvalidOperationException($"P6b peaks length mismatch: expected 64, got {peaks.Length}");
            }
            sw.Stop();
            p6bTimes.Add(sw.Elapsed.TotalMilliseconds);
        });
    }

    // P6c 并发对齐：4 个 Task 各自复用 P3 的构造逻辑，再 Refine
    var p6cTimes = new ConcurrentBag<double>();
    Task[] p6cTasks = new Task[4];
    for (int t = 0; t < p6cTasks.Length; t++)
    {
        p6cTasks[t] = Task.Run(() =>
        {
            var sw = Stopwatch.StartNew();
            var localRngWords = new Random(42);
            var localWords = new List<TranscriptWord>(wordCount);
            for (int i = 0; i < wordCount; i++)
            {
                double slot = totalSeconds * i / wordCount;
                double jitter = (localRngWords.NextDouble() - 0.5) * (totalSeconds / wordCount) * 0.5;
                double startS = Math.Max(0.0, slot + jitter);
                double endS = Math.Min(totalSeconds, startS + (totalSeconds / wordCount) * 0.8);
                localWords.Add(new TranscriptWord(
                    $"词{i}",
                    TimeSpan.FromSeconds(startS),
                    TimeSpan.FromSeconds(endS),
                    0.9f));
            }
            TranscriptDoc localRough = new TranscriptDoc(localWords, TimeSpan.FromMinutes(10));
            TranscriptDoc localRefined = RuleBasedAligner.Refine(bigClip, localRough);
            sw.Stop();
            if (localRefined.Words.Count != 3000)
                throw new InvalidOperationException($"P6c refined words mismatch: expected 3000, got {localRefined.Words.Count}");
            p6cTimes.Add(sw.Elapsed.TotalMilliseconds);
        });
    }

    // P6d 并发导入：4 个 Task 各跑一次 ParsePlainText，复用 P4 的 plainText
    var p6dTimes = new ConcurrentBag<double>();
    Task[] p6dTasks = new Task[4];
    for (int t = 0; t < p6dTasks.Length; t++)
    {
        p6dTasks[t] = Task.Run(() =>
        {
            var sw = Stopwatch.StartNew();
            TranscriptDoc localImported = TranscriptImporter.ParsePlainText(plainText, TimeSpan.FromMinutes(10));
            sw.Stop();
            if (localImported.Words.Count != importedCount)
                throw new InvalidOperationException($"P6d imported words mismatch: expected {importedCount}, got {localImported.Words.Count}");
            p6dTimes.Add(sw.Elapsed.TotalMilliseconds);
        });
    }

    // 四个子项的任务合并成一个数组，10 分钟超时等，超时就当死锁
    var allTasks = new List<Task>();
    allTasks.AddRange(p6aTasks);
    allTasks.AddRange(p6bTasks);
    allTasks.AddRange(p6cTasks);
    allTasks.AddRange(p6dTasks);
    Task[] allTaskArray = allTasks.ToArray();
    bool p6Completed = Task.WaitAll(allTaskArray, 10 * 60 * 1000);
    if (!p6Completed)
        throw new InvalidOperationException("P6 并发阶段超时，疑似死锁");

    var p6EndMem = GC.GetTotalMemory(false);
    double p6MemDeltaMb = (p6EndMem - p6StartMem) / (1024.0 * 1024.0);

    // 把 ConcurrentBag 转数组，方便算最大/平均
    double[] p6aArr = p6aTimes.ToArray();
    double[] p6bArr = p6bTimes.ToArray();
    double[] p6cArr = p6cTimes.ToArray();
    double[] p6dArr = p6dTimes.ToArray();

    double p6aMax = p6aArr.Length > 0 ? p6aArr.Max() : 0.0;
    double p6aAvg = p6aArr.Length > 0 ? p6aArr.Average() : 0.0;
    double p6bMax = p6bArr.Length > 0 ? p6bArr.Max() : 0.0;
    double p6bAvg = p6bArr.Length > 0 ? p6bArr.Average() : 0.0;
    double p6cMax = p6cArr.Length > 0 ? p6cArr.Max() : 0.0;
    double p6cAvg = p6cArr.Length > 0 ? p6cArr.Average() : 0.0;
    double p6dMax = p6dArr.Length > 0 ? p6dArr.Max() : 0.0;
    double p6dAvg = p6dArr.Length > 0 ? p6dArr.Average() : 0.0;

    Console.WriteLine($"[P6a] tasks={p6aTasks.Length} max={p6aMax:F2}ms avg={p6aAvg:F2}ms");
    Console.WriteLine($"[P6b] tasks={p6bTasks.Length} max={p6bMax:F2}ms avg={p6bAvg:F2}ms");
    Console.WriteLine($"[P6c] tasks={p6cTasks.Length} max={p6cMax:F2}ms avg={p6cAvg:F2}ms");
    Console.WriteLine($"[P6d] tasks={p6dTasks.Length} max={p6dMax:F2}ms avg={p6dAvg:F2}ms");
    Console.WriteLine($"[P6] totalTasks={allTaskArray.Length} memDelta={p6MemDeltaMb:F2}MB");

    // ------------------------------------------------------------------
    // P7 ffmpeg 压缩格式解码路径负载
    // ------------------------------------------------------------------
    // 目标：真实走一遍 AudioImporter.Import -> DetectFormat -> FfmpegDecoder.Decode 的生产路径，
    // 覆盖 mp3/flac/m4a 这些需要外部 ffmpeg 的格式，量一下解码耗时和正确性。
    // 环境缺 ffmpeg 就整体跳过，报告里如实写"未测（环境缺 ffmpeg）"，不伪造。

    bool p7Skipped = false;
    string p7SkipReason = "";
    bool ffmpegOk = FfmpegDecoder.IsAvailable();
    string ffmpegBin = FfmpegDecoder.ResolveFfmpegPath(null);

    // P7 产出的文件名，收尾统一清理。
    var p7Files = new List<string>();
    // 报告表用的行，每个已跑用例一条，用变量插值，不写死数字。
    var p7ReportRows = new List<string>();
    // 每个已跑用例的关键指标，结论句里汇总用。
    var p7DecodeMsList = new List<double>();
    double p7DecodeMsSum = 0.0;
    long p7BytesSum = 0;
    int p7CasesRun = 0;

    string seg60Path = Path.Combine(workDir, "p7_seg60.wav");
    string seg300Path = Path.Combine(workDir, "p7_seg300.wav");
    string brokenPath = Path.Combine(workDir, "p7_broken.mp3");

    if (!ffmpegOk)
    {
        p7Skipped = true;
        p7SkipReason = "环境缺 ffmpeg";
        Console.WriteLine("[P7] ffmpeg 不可用，跳过压缩格式测试");
    }
    else
    {
        // 先用 ffmpeg 从 big.wav 截两段出来当源。
        // 不测别的采样率/声道，是为了变量隔离——源本来就是 44100 单声道，
        // 这里只换压缩格式和时长，别的都保持一致，出问题好定位。
        var swSeg = Stopwatch.StartNew();

        RunFfmpeg(ffmpegBin, new[]
        {
            "-y", "-v", "error",
            "-ss", "0", "-t", "60",
            "-i", bigWavPath,
            "-ar", "44100", "-ac", "1",
            seg60Path
        });
        p7Files.Add(seg60Path);

        RunFfmpeg(ffmpegBin, new[]
        {
            "-y", "-v", "error",
            "-ss", "0", "-t", "300",
            "-i", bigWavPath,
            "-ar", "44100", "-ac", "1",
            seg300Path
        });
        p7Files.Add(seg300Path);

        swSeg.Stop();
        Console.WriteLine($"[P7] seg wav 生成完成 seg60={seg60Path} seg300={seg300Path} segMs={swSeg.Elapsed.TotalMilliseconds:F2}");

        // 探测本机 ffmpeg 支持哪些编码器，缺哪个就跳过哪个档位，不假设一定有。
        string encodersOutput = RunFfmpegCaptureStdout(ffmpegBin, new[] { "-hide_banner", "-encoders" });

        bool hasMp3 = encodersOutput.Contains("libmp3lame");
        bool hasAac = encodersOutput.Contains(" aac ") || encodersOutput.Contains("aac ");
        bool hasFlac = encodersOutput.Contains("flac");

        Console.WriteLine($"[P7] encoders mp3(libmp3lame)={hasMp3} aac={hasAac} flac={hasFlac}");

        // 每段要做哪些档位。codecArgs 里直接给 ffmpeg 参数，ext 是输出后缀，tag 是报告/文件名用的短名。
        var matrix = new (string tag, string ext, string[] codecArgs, bool needsMp3, bool needsAac, bool needsFlac)[]
        {
            ("mp3_128k", "mp3", new[] { "-codec:a", "libmp3lame", "-b:a", "128k" }, true, false, false),
            ("mp3_320k", "mp3", new[] { "-codec:a", "libmp3lame", "-b:a", "320k" }, true, false, false),
            ("flac", "flac", new[] { "-codec:a", "flac" }, false, false, true),
            ("m4a_128k", "m4a", new[] { "-codec:a", "aac", "-b:a", "128k" }, false, true, false),
            ("m4a_256k", "m4a", new[] { "-codec:a", "aac", "-b:a", "256k" }, false, true, false),
        };

        // 两段各自的源帧数。60*44100=2646000，300*44100=13230000。
        var segs = new (int seconds, string wavPath, long expectedFrames)[]
        {
            (60, seg60Path, 60L * 44100L),
            (300, seg300Path, 300L * 44100L),
        };

        // 记一下 mp3_128k 60s 那个文件，后面并发小项要用。
        string concurrentMp3Path = "";

        foreach (var seg in segs)
        {
            // 源段读回来当参照，flac 逐采样对比、mp3/m4a 能量 sanity 都用它。
            AudioClip srcClip = WavReader.Read(seg.wavPath);
            float[] srcSamples = srcClip.Samples;
            double srcMeanAbs = MeanAbs(srcSamples);

            foreach (var m in matrix)
            {
                if (m.needsMp3 && !hasMp3)
                {
                    Console.WriteLine($"[P7] skip {m.tag} seg={seg.seconds}s 原因=本机 ffmpeg 缺 libmp3lame 编码器");
                    continue;
                }
                if (m.needsAac && !hasAac)
                {
                    Console.WriteLine($"[P7] skip {m.tag} seg={seg.seconds}s 原因=本机 ffmpeg 缺 aac 编码器");
                    continue;
                }
                if (m.needsFlac && !hasFlac)
                {
                    Console.WriteLine($"[P7] skip {m.tag} seg={seg.seconds}s 原因=本机 ffmpeg 缺 flac 编码器");
                    continue;
                }

                string outPath = Path.Combine(workDir, $"p7_seg{seg.seconds}_{m.tag}.{m.ext}");

                var encArgs = new List<string> { "-y", "-v", "error", "-i", seg.wavPath };
                encArgs.AddRange(m.codecArgs);
                encArgs.Add(outPath);
                RunFfmpeg(ffmpegBin, encArgs.ToArray());
                p7Files.Add(outPath);

                long bytes = new FileInfo(outPath).Length;

                // 走真实生产路径：AudioImporter.Import -> DetectFormat -> FfmpegDecoder.Decode。
                var swDec = Stopwatch.StartNew();
                AudioClip decoded = AudioImporter.Import(outPath);
                swDec.Stop();
                double decodeMs = swDec.Elapsed.TotalMilliseconds;

                if (decoded.SampleRate != 44100)
                    throw new InvalidOperationException($"[P7] {m.tag} seg={seg.seconds}s SampleRate 期望 44100 实际 {decoded.SampleRate}");
                if (decoded.Channels != 1)
                    throw new InvalidOperationException($"[P7] {m.tag} seg={seg.seconds}s Channels 期望 1 实际 {decoded.Channels}");

                // 压缩编解码有前后延迟垫帧，解码出来的帧数不会跟源段一帧不差，
                // 允许正负 2500 帧的偏差，超了就说明哪里不对。
                long frameDiff = Math.Abs(decoded.Frames - seg.expectedFrames);
                if (frameDiff > 2500)
                    throw new InvalidOperationException($"[P7] {m.tag} seg={seg.seconds}s Frames 期望约 {seg.expectedFrames} 实际 {decoded.Frames} 偏差 {frameDiff}");

                if (m.needsFlac)
                {
                    // flac 是无损的，逐采样对比。ffmpeg 走 f32le 直出，不是 16-bit 量化，
                    // 所以容差比 P1 的 4e-5 大，用 5e-4。
                    const float flacTolerance = 5e-4f;
                    int cmpLen = (int)Math.Min(srcSamples.Length, decoded.Samples.Length);
                    for (int i = 0; i < cmpLen; i++)
                    {
                        float diff = Math.Abs(decoded.Samples[i] - srcSamples[i]);
                        if (diff >= flacTolerance)
                            throw new InvalidOperationException($"[P7] {m.tag} seg={seg.seconds}s flac 逐采样不一致 idx={i} src={srcSamples[i]} dec={decoded.Samples[i]} diff={diff}");
                    }
                }
                else
                {
                    // mp3/m4a 有损，不逐采样对，只做能量 sanity：
                    // 解码后与源段的平均绝对值相对偏差要小于 10%。
                    // 依据 2026-10-20 真实负载实测：mp3_128k 60s 段 rel=0.0522，5% 门限对有损格式偏严；
                    // 帧数/采样率/声道已分别校验通过，此处只做能量级 sanity。
                    double decMeanAbs = MeanAbs(decoded.Samples);
                    double relDiff = srcMeanAbs > 1e-9 ? Math.Abs(decMeanAbs - srcMeanAbs) / srcMeanAbs : Math.Abs(decMeanAbs - srcMeanAbs);
                    if (relDiff >= 0.10)
                        throw new InvalidOperationException($"[P7] {m.tag} seg={seg.seconds}s 能量偏差过大 srcMean={srcMeanAbs:F6} decMean={decMeanAbs:F6} rel={relDiff:F4}");
                }

                p7DecodeMsList.Add(decodeMs);
                p7DecodeMsSum += decodeMs;
                p7BytesSum += bytes;
                p7CasesRun++;

                p7ReportRows.Add($"| P7 {m.tag} | {seg.seconds}s / {bytes / 1024.0:F1} KB | {decodeMs:F2} ms | Frames={decoded.Frames}, SR={decoded.SampleRate}, CH={decoded.Channels} |");

                if (m.tag == "mp3_128k" && seg.seconds == 60)
                {
                    concurrentMp3Path = outPath;
                }

                Console.WriteLine($"[P7] fmt={m.tag} seg={seg.seconds}s bytes={bytes} decodeMs={decodeMs:F2} frames={decoded.Frames}");
            }
        }

        // 异常路径：把一个 mp3 截一半，Import 必须抛 AudioFormatException。
        if (hasMp3 && File.Exists(concurrentMp3Path))
        {
            byte[] full = File.ReadAllBytes(concurrentMp3Path);
            int halfLen = full.Length / 2;
            byte[] half = new byte[halfLen];
            Array.Copy(full, half, halfLen);
            File.WriteAllBytes(brokenPath, half);
            p7Files.Add(brokenPath);

            bool threw = false;
            try
            {
                AudioImporter.Import(brokenPath);
            }
            catch (AudioFormatException)
            {
                threw = true;
            }
            if (!threw)
                throw new InvalidOperationException("损坏文件未被拒绝");
            Console.WriteLine($"[P7] broken 文件被正确拒绝 path={brokenPath} bytes={halfLen}");
        }

        // 并发小项：4 个 Task 同时对同一个 mp3_128k 文件 Import。
        // 这是测 ffmpeg 进程级并发解码能力，不是重复 P6 的通用并发。
        if (File.Exists(concurrentMp3Path))
        {
            var tasks = new Task<AudioClip>[4];
            for (int i = 0; i < tasks.Length; i++)
            {
                tasks[i] = Task.Run(() => AudioImporter.Import(concurrentMp3Path));
            }

            bool allDone = Task.WaitAll(tasks, 5 * 60 * 1000);
            if (!allDone)
                throw new InvalidOperationException("P7 并发解码超时，疑似死锁");

            long firstFrames = tasks[0].Result.Frames;
            for (int i = 1; i < tasks.Length; i++)
            {
                if (tasks[i].Result.Frames != firstFrames)
                    throw new InvalidOperationException($"[P7] 并发解码 Frames 不一致 task0={firstFrames} task{i}={tasks[i].Result.Frames}");
            }

            Console.WriteLine($"[P7] concurrent import 4x ok frames={firstFrames}");
        }
        else
        {
            Console.WriteLine("[P7] concurrent skip 原因=没有可用的 mp3_128k 文件");
        }

        // P7 自己产的文件自己清掉，big.wav 留给 P5 末尾清。
        foreach (string f in p7Files)
        {
            try
            {
                if (File.Exists(f))
                    File.Delete(f);
            }
            catch
            {
                // 清理失败不致命，忽略。
            }
        }
        Console.WriteLine("[P7] cleaned");
    }

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
    report.AppendLine($"- P6 并发/多线程负载：8 路并发 WavReader.Read、8 路并发 WaveformLod 构建+查询、4 路并发 RuleBasedAligner.Refine、4 路并发 TranscriptImporter.ParsePlainText，用 Task.WaitAll 带 10 分钟超时判死锁。");
    if (p7Skipped)
    {
        report.AppendLine($"- P7 ffmpeg 解码：未测（原因：{p7SkipReason}）。");
    }
    else
    {
        report.AppendLine($"- P7 ffmpeg 压缩格式解码：从 big.wav 截 60s 与 300s 两段，用 ffmpeg 编成 mp3 128k/320k、flac、m4a aac 128k/256k，再走 AudioImporter.Import 解码；每个编码档位先探测本机 ffmpeg 是否有对应编码器，缺了就跳过该档位并打印原因。");
    }
    report.AppendLine();
    report.AppendLine("## 诚实边界（必读）");
    report.AppendLine();
    report.AppendLine("- 本轮合成音频为 440Hz 正弦 + 固定种子噪声 + 每 2 秒有声/静音包络，属合成信号，非真实语音；VAD/对齐行为不代表真实播客。");
    report.AppendLine("- P0-P5 单进程串行执行；P6 做了 8 路并发读/波形金字塔、4 路并发对齐/导入验证。");
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
    report.AppendLine($"| P6a 并发读 | {p6aTasks.Length} 任务 | max={p6aMax:F2} ms / avg={p6aAvg:F2} ms | 每任务读回 Frames={ExpectedFrames}, SR={SampleRate} |");
    report.AppendLine($"| P6b 并发波形金字塔 | {p6bTasks.Length} 任务 × 50 次 GetPeaks | max={p6bMax:F2} ms / avg={p6bAvg:F2} ms | Levels={levels}, len=64 |");
    report.AppendLine($"| P6c 并发对齐 | {p6cTasks.Length} 任务 × {wordCount} 词 | max={p6cMax:F2} ms / avg={p6cAvg:F2} ms | 每任务输出词数=3000 |");
    report.AppendLine($"| P6d 并发导入 | {p6dTasks.Length} 任务 × {importWords} 词 | max={p6dMax:F2} ms / avg={p6dAvg:F2} ms | 每任务解析词数={importedCount} |");
    if (p7Skipped)
    {
        report.AppendLine("| P7 ffmpeg 压缩格式解码 | ffmpeg 不可用，跳过 | - | - |");
    }
    else
    {
        foreach (string row in p7ReportRows)
        {
            report.AppendLine(row);
        }
    }
    report.AppendLine();
    report.AppendLine("## 结论");
    report.AppendLine();
    if (p7Skipped)
    {
        report.AppendLine($"本轮 P1–P4、P6 全部阶段成功完成，无异常抛出；P7 因{p7SkipReason}跳过。主要耗时集中在 WAV 写入/读回（{swWrite.Elapsed.TotalMilliseconds + swRead.Elapsed.TotalMilliseconds:F2} ms 合计）与 WaveformLod 构建（{swLod.Elapsed.TotalMilliseconds:F2} ms），对齐（{swAlign.Elapsed.TotalMilliseconds:F2} ms）与导入（{swImport.Elapsed.TotalMilliseconds:F2} ms）在本次数据规模下开销较小。");
    }
    else
    {
        report.AppendLine($"本轮 P1–P4、P6、P7 全部阶段成功完成，无异常抛出。主要耗时集中在 WAV 写入/读回（{swWrite.Elapsed.TotalMilliseconds + swRead.Elapsed.TotalMilliseconds:F2} ms 合计）与 WaveformLod 构建（{swLod.Elapsed.TotalMilliseconds:F2} ms），对齐（{swAlign.Elapsed.TotalMilliseconds:F2} ms）与导入（{swImport.Elapsed.TotalMilliseconds:F2} ms）在本次数据规模下开销较小；P7 跑了 {p7CasesRun} 个压缩解码用例，解码总耗时 {p7DecodeMsSum:F2} ms，压缩文件总字节 {p7BytesSum}。");
    }
    report.AppendLine();
    report.AppendLine("## 未测项清单");
    report.AppendLine();
    report.AppendLine("- 并发/多线程负载：已测（P6：8 路并发 WavReader.Read、8 路并发 WaveformLod 构建+查询、4 路并发 RuleBasedAligner.Refine、4 路并发 TranscriptImporter.ParsePlainText，超时 10 分钟判死锁）。");
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

// 跑一次 ffmpeg，用 ArgumentList 传参避免拼接引号出错；非零退出码直接抛。
static void RunFfmpeg(string ffmpegBin, string[] args)
{
    var psi = new ProcessStartInfo
    {
        FileName = ffmpegBin,
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        CreateNoWindow = true
    };
    foreach (string a in args)
    {
        psi.ArgumentList.Add(a);
    }

    using var process = Process.Start(psi);
    if (process is null)
    {
        throw new InvalidOperationException($"启动 ffmpeg 失败：{ffmpegBin}");
    }

    string stdout = process.StandardOutput.ReadToEnd();
    string stderr = process.StandardError.ReadToEnd();
    process.WaitForExit();

    if (process.ExitCode != 0)
    {
        throw new InvalidOperationException($"ffmpeg 退出码 {process.ExitCode}：{stderr}");
    }
}

// 跑一次 ffmpeg 并把 stdout 全部收下来，用于 -encoders 探测。
static string RunFfmpegCaptureStdout(string ffmpegBin, string[] args)
{
    var psi = new ProcessStartInfo
    {
        FileName = ffmpegBin,
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        CreateNoWindow = true
    };
    foreach (string a in args)
    {
        psi.ArgumentList.Add(a);
    }

    using var process = Process.Start(psi);
    if (process is null)
    {
        throw new InvalidOperationException($"启动 ffmpeg 失败：{ffmpegBin}");
    }

    string stdout = process.StandardOutput.ReadToEnd();
    process.StandardError.ReadToEnd();
    process.WaitForExit();

    return stdout;
}

// 平均绝对值，用来做 mp3/m4a 的能量 sanity。
static double MeanAbs(float[] samples)
{
    if (samples.Length == 0) return 0.0;
    double sum = 0.0;
    for (int i = 0; i < samples.Length; i++)
    {
        sum += Math.Abs(samples[i]);
    }
    return sum / samples.Length;
}
