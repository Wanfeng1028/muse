using System;
using System.Collections.Generic;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2BoundaryBurstTests
{
    private static AudioClip BuildClip(int sampleRate, double seconds, double burstStartSec, double burstEndSec, double amp = 0.8, double freq = 440.0)
    {
        int total = (int)Math.Round(sampleRate * seconds);
        var samples = new float[total];
        int startIdx = (int)Math.Round(sampleRate * burstStartSec);
        int endIdx = (int)Math.Round(sampleRate * burstEndSec);
        if (startIdx < 0) startIdx = 0;
        if (endIdx > total) endIdx = total;
        for (int i = startIdx; i < endIdx; i++)
        {
            double t = (double)i / sampleRate;
            samples[i] = (float)(amp * Math.Sin(2.0 * Math.PI * freq * t));
        }
        return new AudioClip(sampleRate, 1, samples);
    }

    [Fact]
    public void BurstAtClipStart_Aligned()
    {
        var clip = BuildClip(8000, 2.0, 0.0, 0.5);

        var words = new List<TranscriptWord>
        {
            new TranscriptWord("内容", TimeSpan.FromSeconds(1.5), TimeSpan.FromSeconds(1.6), 1f)
        };
        var rough = new TranscriptDoc(words, TimeSpan.FromSeconds(2.0));

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.NotNull(result);
        Assert.Single(result.Words);

        var w = result.Words[0];
        Assert.Equal("内容", w.Text);
        Assert.InRange(w.Start.TotalSeconds, 0.0, 0.1);
        Assert.InRange(w.End.TotalSeconds, 0.4, 0.6);
        Assert.True(w.End >= w.Start);
    }
}
