using System;
using System.Collections.Generic;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2HangoverTests
{
    private static AudioClip BuildClip(int sampleRate, double seconds, Func<double, float> sampleAt)
    {
        int total = (int)(sampleRate * seconds);
        var samples = new float[total];
        for (int i = 0; i < total; i++)
        {
            double t = (double)i / sampleRate;
            samples[i] = sampleAt(t);
        }
        return new AudioClip(sampleRate, 1, samples);
    }

    private static float BurstAt(double t, double start, double end, double amp)
        => (t >= start && t < end) ? (float)(amp * Math.Sin(2 * Math.PI * 440 * t)) : 0f;

    [Fact]
    public void ShortDip_BridgedByHangover()
    {
        int sampleRate = 8000;
        double seconds = 3.0;

        var clip = BuildClip(sampleRate, seconds, t =>
        {
            if (t >= 0.5 && t < 1.0) return (float)(0.5 * Math.Sin(2 * Math.PI * 440 * t));
            if (t >= 1.0 && t < 1.1) return (float)(0.001 * Math.Sin(2 * Math.PI * 440 * t));
            if (t >= 1.1 && t < 1.5) return (float)(0.5 * Math.Sin(2 * Math.PI * 440 * t));
            return 0f;
        });

        var rough = new TranscriptDoc(new[]
        {
            new TranscriptWord("内容", TimeSpan.FromSeconds(0.6), TimeSpan.FromSeconds(0.7)),
            new TranscriptWord("内容", TimeSpan.FromSeconds(1.2), TimeSpan.FromSeconds(1.3)),
        }, TimeSpan.FromSeconds(3));

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.NotNull(result);
        Assert.Equal(2, result.Words.Count);

        var w0 = result.Words[0];
        var w1 = result.Words[1];

        Assert.InRange(w0.Start.TotalSeconds, 0.45, 0.6);
        Assert.InRange(w1.End.TotalSeconds, 1.4, 1.6);

        Assert.True(w0.End.TotalSeconds >= 0.9,
            $"词0.End 应 >= 0.9，实际 {w0.End.TotalSeconds}");
        Assert.True(w1.Start.TotalSeconds <= 1.2,
            $"词1.Start 应 <= 1.2，实际 {w1.Start.TotalSeconds}");
    }
}
