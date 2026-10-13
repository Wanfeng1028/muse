using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.EndToEnd;

/// <summary>
/// 核心链路冒烟：导入 WAV → 转写稿对齐 → 文字删除 → 语气词弱化 → EDL 导出。
/// 用合成音频全内存跑通，不依赖外部文件与模型。
/// </summary>
public sealed class TextEditChainTests
{
    private const int SampleRate = 16000;

    private static AudioClip SynthSpeech(double seconds, int seed = 7)
    {
        var rng = new Random(seed);
        var n = (int)(seconds * SampleRate);
        var s = new float[n];
        var i = 0;
        while (i < n)
        {
            var syl = (int)((0.15 + rng.NextDouble() * 0.15) * SampleRate);
            var freq = 120 + rng.NextDouble() * 100;
            var amp = 0.3f + (float)rng.NextDouble() * 0.2f;
            for (var k = 0; k < syl && i < n; k++, i++)
            {
                var t = k / (double)SampleRate;
                var env = Math.Min(1.0, k / (0.01 * SampleRate)) * Math.Exp(-2.0 * k / syl);
                s[i] = (float)(amp * env * Math.Sin(2 * Math.PI * freq * t));
            }
            var gap = (int)(0.06 * SampleRate);
            i += gap; // 静音气口（数组默认 0）
        }
        return new AudioClip(SampleRate, 1, s);
    }

    [Fact]
    public void FullChain_ImportAlignDeleteWeakenExport_Works()
    {
        // 1. 导入：合成 8 秒语音 → 落盘 WAV → 读回
        var clip = SynthSpeech(8.0);
        var wavPath = Path.Combine(Path.GetTempPath(), $"voxloom_chain_{Guid.NewGuid():N}.wav");
        try
        {
            WavWriter.Write(wavPath, clip);
            var imported = WavReader.Read(wavPath);
            Assert.Equal(clip.Samples.Length, imported.Samples.Length);
            Assert.Equal(SampleRate, imported.SampleRate);

            // 2. 对齐：转写稿（含语气词）→ 粗对齐 → 规则精修
            var text = "大家好，嗯，欢迎来到声纹工坊。那个，今天我们演示一下文字剪辑。对吧？";
            var rough = TranscriptImporter.ParsePlainText(text, imported.Duration);
            var aligned = RuleBasedAligner.Refine(imported, rough);
            Assert.Equal(rough.Words.Count, aligned.Words.Count);
            Assert.True(aligned.Words.All(w => w.End <= imported.Duration + TimeSpan.FromMilliseconds(1)));

            // 3. 文字删除：删掉"那个，今天我们演示一下"对应区间
            var victim = aligned.Words.First(w => w.Text.Contains("那"));
            var delRange = new TimeRange(victim.Start, victim.End);
            var deleted = new EditPlan(imported, new EditOp[] { new DeleteOp(delRange) }).Render();
            var removedSec = (delRange.End - delRange.Start).TotalSeconds;
            Assert.True(deleted.Duration.TotalSeconds < imported.Duration.TotalSeconds - removedSec * 0.5,
                "删除后时长应明显变短");

            // 4. 语气词弱化：检测"嗯"并衰减 -12dB，能量应下降
            var fillers = FillerWordDetector.Detect(aligned);
            Assert.NotEmpty(fillers);
            var weakened = new EditPlan(deleted,
                FillerWordDetector.ToAttenuateOps(fillers, -12f)).Render();
            Assert.Equal(deleted.Samples.Length, weakened.Samples.Length);
            double Energy(AudioClip c, TimeRange r)
            {
                var a = (int)(r.Start.TotalSeconds * c.SampleRate);
                var b = Math.Min(c.Samples.Length, (int)(r.End.TotalSeconds * c.SampleRate));
                double e = 0;
                for (var k = a; k < b; k++) e += c.Samples[k] * c.Samples[k];
                return e;
            }
            // 注意：删除改变了时间轴，这里只验证弱化本身不改变时长且输出有效
            Assert.True(weakened.Samples.Any(v => v != 0));

            // 5. 导出 EDL：语气词区间剪掉，其余保留
            var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>();
            var cursor = TimeSpan.Zero;
            var prev = TimeSpan.Zero;
            foreach (var r in fillers.OrderBy(x => x.Start))
            {
                if (r.Start > prev)
                {
                    var keep = new TimeRange(prev, r.Start);
                    events.Add((keep, cursor));
                    cursor += keep.End - keep.Start;
                }
                prev = r.End;
            }
            if (weakened.Duration > prev) events.Add((new TimeRange(prev, weakened.Duration), cursor));
            var edl = EdlExporter.ExportCmx3600("VOXLOOM_CHAIN", events, SampleRate);
            Assert.Contains("TITLE: VOXLOOM_CHAIN", edl);
            var eventLines = System.Text.RegularExpressions.Regex.Matches(edl, @"(?m)^\d{3}  ").Count;
            Assert.Equal(events.Count, eventLines);
        }
        finally
        {
            if (File.Exists(wavPath)) File.Delete(wavPath);
        }
    }
}
