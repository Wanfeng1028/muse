using System;
using System.Collections.Generic;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerTests
{
    private const int SampleRate = 16000;

    private static AudioClip BuildClip()
    {
        // 前 1s 静音 + 2s 正弦"语音" + 1s 静音。
        int total = SampleRate * 4;
        var samples = new float[total];
        int speechStart = SampleRate * 1;
        int speechEnd = SampleRate * 3;

        for (int i = speechStart; i < speechEnd; i++)
        {
            samples[i] = (float)(0.5 * Math.Sin(2 * Math.PI * 440.0 * (i - speechStart) / SampleRate));
        }

        return new AudioClip(SampleRate, 1, samples);
    }

    [Fact]
    public void Refine_WordsFallWithinSpeechAndAreMonotonic()
    {
        var clip = BuildClip();

        // 粗估词表：4 个词，时间粗略均匀分布在整个 4s。
        var rough = new List<TranscriptWord>
        {
            new("你好", TimeSpan.FromSeconds(0.0), TimeSpan.FromSeconds(1.0)),
            new("世界", TimeSpan.FromSeconds(1.0), TimeSpan.FromSeconds(2.0)),
            new("这是", TimeSpan.FromSeconds(2.0), TimeSpan.FromSeconds(3.0)),
            new("测试", TimeSpan.FromSeconds(3.0), TimeSpan.FromSeconds(4.0)),
        };
        var roughTranscript = new TranscriptDoc(rough, TimeSpan.FromSeconds(4));

        var refined = RuleBasedAligner.Refine(clip, roughTranscript);

        Assert.Equal(4, refined.Words.Count);

        // 语音段大致在 1s ~ 3s 之间，允许 VAD 边界的少量误差。
        var speechStart = TimeSpan.FromSeconds(0.9);
        var speechEnd = TimeSpan.FromSeconds(3.1);

        foreach (var w in refined.Words)
        {
            Assert.True(w.Start >= speechStart, $"词 {w.Text} 起始 {w.Start} 早于语音段。");
            Assert.True(w.End <= speechEnd, $"词 {w.Text} 结束 {w.End} 晚于语音段。");
        }

        // 单调不减。
        for (int i = 1; i < refined.Words.Count; i++)
        {
            Assert.True(refined.Words[i].Start >= refined.Words[i - 1].Start,
                $"词序非单调：{refined.Words[i - 1].Text} -> {refined.Words[i].Text}");
            Assert.True(refined.Words[i].Start >= refined.Words[i - 1].End,
                $"词间时间重叠：{refined.Words[i - 1].Text} -> {refined.Words[i].Text}");
        }
    }

    [Fact]
    public void Refine_EmptyTranscript_ReturnsSame()
    {
        var clip = BuildClip();
        var empty = TranscriptDoc.Empty;
        var refined = RuleBasedAligner.Refine(clip, empty);
        Assert.Empty(refined.Words);
    }

    [Fact]
    public void Refine_AllSilence_KeepsRough()
    {
        // 全静音。
        var samples = new float[SampleRate * 4];
        var clip = new AudioClip(SampleRate, 1, samples);

        var rough = new List<TranscriptWord>
        {
            new("a", TimeSpan.FromSeconds(0.0), TimeSpan.FromSeconds(1.0)),
            new("b", TimeSpan.FromSeconds(1.0), TimeSpan.FromSeconds(2.0)),
        };
        var roughTranscript = new TranscriptDoc(rough, TimeSpan.FromSeconds(4));

        var refined = RuleBasedAligner.Refine(clip, roughTranscript);
        Assert.Equal(2, refined.Words.Count);
        Assert.Equal(TimeSpan.FromSeconds(0.0), refined.Words[0].Start);
    }
}
