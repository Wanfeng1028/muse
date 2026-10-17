using System;
using System.Linq;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public sealed class RuleBasedAlignerDeepTests
{
    private const int SampleRate = 16000;

    private static float[] Silence(double seconds)
    {
        int n = (int)Math.Round(seconds * SampleRate);
        return new float[n];
    }

    private static float[] Sine(double seconds, double freq = 400.0, double amp = 0.5)
    {
        int n = (int)Math.Round(seconds * SampleRate);
        var buf = new float[n];
        for (int i = 0; i < n; i++)
        {
            buf[i] = (float)(amp * Math.Sin(2.0 * Math.PI * freq * i / SampleRate));
        }
        return buf;
    }

    private static float[] Concat(params float[][] parts)
    {
        int total = 0;
        foreach (var p in parts) total += p.Length;
        var result = new float[total];
        int off = 0;
        foreach (var p in parts)
        {
            Array.Copy(p, 0, result, off, p.Length);
            off += p.Length;
        }
        return result;
    }

    private static TranscriptWord W(string text, double startSec, double endSec, float conf = 1f)
        => new TranscriptWord(text, TimeSpan.FromSeconds(startSec), TimeSpan.FromSeconds(endSec), conf);

    private static AudioClip Clip(float[] samples) => new AudioClip(SampleRate, 1, samples);

    // 1. clip/rough 为 null 抛 ArgumentNullException。
    [Fact]
    public void Refine_NullArguments_Throw()
    {
        var clip = Clip(Sine(0.5));
        var rough = new TranscriptDoc(new[] { W("a", 0, 0.5) }, TimeSpan.FromSeconds(0.5));

        Assert.Throws<ArgumentNullException>(() => RuleBasedAligner.Refine(null!, rough));
        Assert.Throws<ArgumentNullException>(() => RuleBasedAligner.Refine(clip, null!));
    }

    // 2. 零帧 clip → 返回 rough 原样（词表相同）。
    [Fact]
    public void Refine_ZeroFrameClip_ReturnsRough()
    {
        var clip = Clip(new float[0]);
        var rough = new TranscriptDoc(new[] { W("a", 0, 0.4), W("b", 0.4, 0.8) }, TimeSpan.FromSeconds(0.8));

        var result = RuleBasedAligner.Refine(clip, rough);
        Assert.Equal(rough.Words.Count, result.Words.Count);
        for (int i = 0; i < rough.Words.Count; i++)
        {
            Assert.Equal(rough.Words[i].Text, result.Words[i].Text);
            Assert.Equal(rough.Words[i].Start, result.Words[i].Start);
            Assert.Equal(rough.Words[i].End, result.Words[i].End);
        }
    }

    // 3. 50ms 爆音小于最小段长 100ms → 无语音段 → 返回 rough 原样。
    [Fact]
    public void Refine_ShortBurstBelowMinSegment_ReturnsRough()
    {
        // 2 秒音频：前 1 秒静音 + 50ms 正弦 + 剩余静音。
        var samples = Concat(Silence(1.0), Sine(0.05), Silence(0.95));
        var clip = Clip(samples);
        var rough = new TranscriptDoc(new[] { W("hello", 0.2, 1.0) }, TimeSpan.FromSeconds(2));

        var result = RuleBasedAligner.Refine(clip, rough);
        Assert.Single(result.Words);
        Assert.Equal(TimeSpan.FromSeconds(0.2), result.Words[0].Start);
        Assert.Equal(TimeSpan.FromSeconds(1.0), result.Words[0].End);
    }

    // 4. 两段语音：词按段分配，前两词落入第一段，后两词落入第二段。
    [Fact]
    public void Refine_TwoSegments_WordsAssignedToRespectiveSegments()
    {
        // 4 秒：[0,0.5)静音, [0.5,1.5)语音, [1.5,2.5)静音, [2.5,3.5)语音, [3.5,4)静音。
        var samples = Concat(Silence(0.5), Sine(1.0), Silence(1.0), Sine(1.0), Silence(0.5));
        var clip = Clip(samples);
        var rough = new TranscriptDoc(new[]
        {
            W("a", 0.0, 1.0),
            W("b", 1.0, 2.0),
            W("c", 2.0, 3.0),
            W("d", 3.0, 4.0),
        }, TimeSpan.FromSeconds(4));

        var result = RuleBasedAligner.Refine(clip, rough);
        Assert.Equal(4, result.Words.Count);

        var seg1Start = TimeSpan.FromSeconds(0.5);
        var seg1End = TimeSpan.FromSeconds(1.5);
        var seg2Start = TimeSpan.FromSeconds(2.5);
        var seg2End = TimeSpan.FromSeconds(3.5);

        // 前两词中心位于第一段内
        Assert.True(result.Words[0].Start >= seg1Start && result.Words[0].End <= seg1End);
        Assert.True(result.Words[1].Start >= seg1Start && result.Words[1].End <= seg1End);
        // 后两词中心位于第二段内
        Assert.True(result.Words[2].Start >= seg2Start && result.Words[2].End <= seg2End);
        Assert.True(result.Words[3].Start >= seg2Start && result.Words[3].End <= seg2End);
    }

    // 5. 段合并：两段间隔 100ms < 200ms 合并为一段；词重映射后单调且覆盖合并后段。
    [Fact]
    public void Refine_MergeSegmentsWithin200ms()
    {
        // 3 秒：[0,0.5)静音, [0.5,1.0)语音, [1.0,1.1)静音(100ms), [1.1,1.6)语音, 其余静音。
        var samples = Concat(Silence(0.5), Sine(0.5), Silence(0.1), Sine(0.5), Silence(1.4));
        var clip = Clip(samples);
        var rough = new TranscriptDoc(new[]
        {
            W("a", 0.5, 1.0),
            W("b", 1.0, 1.5),
        }, TimeSpan.FromSeconds(3));

        var result = RuleBasedAligner.Refine(clip, rough);
        Assert.Equal(2, result.Words.Count);
        // 单调
        Assert.True(result.Words[1].Start >= result.Words[0].Start);
        Assert.True(result.Words[0].End <= result.Words[1].Start + TimeSpan.FromMilliseconds(1));
        // 两词都落在合并段 [0.5,1.6) 附近
        Assert.True(result.Words[0].Start >= TimeSpan.FromSeconds(0.5 - 0.05));
        Assert.True(result.Words[1].End <= TimeSpan.FromSeconds(1.6 + 0.05));
    }

    // 6. 全片语音按字符权重 2:4 分配，第一词约 [0, 0.667s)，第二词约 [0.667s, 2s)。
    [Fact]
    public void Refine_FullCoverage_WeightedByTextLength()
    {
        var clip = Clip(Sine(2.0));
        var rough = new TranscriptDoc(new[]
        {
            W("ab", 0.0, 1.0),
            W("cdef", 1.0, 2.0),
        }, TimeSpan.FromSeconds(2));

        var result = RuleBasedAligner.Refine(clip, rough);
        Assert.Equal(2, result.Words.Count);

        // 权重 2:4，总 6；第一词占比 1/3 → 约 0.6667s。
        Assert.Equal(0.0, result.Words[0].Start.TotalSeconds, 2);
        Assert.InRange(result.Words[0].End.TotalSeconds, 0.6667 - 0.05, 0.6667 + 0.05);
        Assert.InRange(result.Words[1].Start.TotalSeconds, 0.6667 - 0.05, 0.6667 + 0.05);
        Assert.Equal(2.0, result.Words[1].End.TotalSeconds, 2);
    }

    // 7. 置信度保留：Refine 后新词 Confidence 与原词一致。
    [Fact]
    public void Refine_PreservesConfidence()
    {
        var clip = Clip(Sine(2.0));
        var rough = new TranscriptDoc(new[]
        {
            W("hello", 0.0, 1.0, 0.42f),
            W("world", 1.0, 2.0, 0.87f),
        }, TimeSpan.FromSeconds(2));

        var result = RuleBasedAligner.Refine(clip, rough);
        Assert.Equal(2, result.Words.Count);
        Assert.Equal(0.42f, result.Words[0].Confidence, 6);
        Assert.Equal(0.87f, result.Words[1].Confidence, 6);
    }

    // 8. 结果单调：多词多段场景下 Words 按 Start 非递减。
    [Fact]
    public void Refine_WordsMonotonic()
    {
        var samples = Concat(Silence(0.2), Sine(1.0), Silence(0.5), Sine(1.0), Silence(0.3));
        var clip = Clip(samples);
        var rough = new TranscriptDoc(new[]
        {
            W("a", 0.0, 0.5),
            W("b", 0.5, 1.0),
            W("c", 1.0, 1.5),
            W("d", 1.5, 2.0),
            W("e", 2.0, 2.5),
        }, TimeSpan.FromSeconds(3));

        var result = RuleBasedAligner.Refine(clip, rough);
        for (int i = 1; i < result.Words.Count; i++)
        {
            Assert.True(result.Words[i].Start >= result.Words[i - 1].Start,
                $"词 {i} 的 Start {result.Words[i].Start} 应 >= 词 {i - 1} 的 Start {result.Words[i - 1].Start}");
        }
    }

    // 9. 单词独占一段：1 秒全片正弦，1 个词 → 新词约 [0, 1s)。
    [Fact]
    public void Refine_SingleWordFullClip()
    {
        var clip = Clip(Sine(1.0));
        var rough = new TranscriptDoc(new[] { W("hello", 0.0, 1.0) }, TimeSpan.FromSeconds(1));

        var result = RuleBasedAligner.Refine(clip, rough);
        Assert.Single(result.Words);
        Assert.InRange(result.Words[0].Start.TotalSeconds, 0.0 - 0.05, 0.0 + 0.05);
        Assert.InRange(result.Words[0].End.TotalSeconds, 1.0 - 0.05, 1.0 + 0.05);
    }

    // 10. 全静音音频 + 非零粗估时间 → 无语音段 → 返回 rough 原样，词时间不被改动。
    [Fact]
    public void Refine_AllSilence_ReturnsRoughUnchanged()
    {
        var clip = Clip(Silence(2.0));
        var rough = new TranscriptDoc(new[]
        {
            W("hello", 0.3, 1.1),
            W("world", 1.1, 1.9),
        }, TimeSpan.FromSeconds(2));

        var result = RuleBasedAligner.Refine(clip, rough);
        Assert.Equal(2, result.Words.Count);
        Assert.Equal(TimeSpan.FromSeconds(0.3), result.Words[0].Start);
        Assert.Equal(TimeSpan.FromSeconds(1.1), result.Words[0].End);
        Assert.Equal(TimeSpan.FromSeconds(1.1), result.Words[1].Start);
        Assert.Equal(TimeSpan.FromSeconds(1.9), result.Words[1].End);
    }
}
