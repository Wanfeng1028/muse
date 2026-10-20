using System;
using System.Collections.Generic;
using Xunit;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2ContinuousSpeechTests
{
    [Fact]
    public void ContinuousBurst_SingleSegment_FullCoverage()
    {
        const int sampleRate = 8000;
        const double durationSec = 3.0;
        const double freq = 440.0;
        const double amp = 0.5;

        int totalSamples = (int)(sampleRate * durationSec);
        var samples = new float[totalSamples];
        for (int i = 0; i < totalSamples; i++)
        {
            double t = (double)i / sampleRate;
            samples[i] = (float)(amp * Math.Sin(2 * Math.PI * freq * t));
        }

        var clip = new AudioClip(sampleRate, 1, samples);

        var words = new List<TranscriptWord>
        {
            new TranscriptWord("甲", TimeSpan.FromSeconds(0.1), TimeSpan.FromSeconds(0.2)),
            new TranscriptWord("乙", TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(0.6)),
            new TranscriptWord("丙", TimeSpan.FromSeconds(2.5), TimeSpan.FromSeconds(2.6)),
        };
        var rough = new TranscriptDoc(words, TimeSpan.FromSeconds(durationSec));

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.NotNull(result);
        Assert.Equal(3, result.Words.Count);

        var w0 = result.Words[0];
        var w1 = result.Words[1];
        var w2 = result.Words[2];

        Assert.InRange(w0.Start.TotalSeconds, -0.05, 0.05);

        Assert.InRange(w2.End.TotalSeconds, 2.95, 3.0);

        Assert.True(w0.Start <= w0.End, "首词 Start 应不大于 End");
        Assert.True(w0.End <= w1.Start, "词序应单调：w0.End <= w1.Start");
        Assert.True(w1.Start <= w1.End, "次词 Start 应不大于 End");
        Assert.True(w1.End <= w2.Start, "词序应单调：w1.End <= w2.Start");
        Assert.True(w2.Start <= w2.End, "末词 Start 应不大于 End");

        Assert.InRange(w0.Start.TotalSeconds, 0.0, 3.0);
        Assert.InRange(w0.End.TotalSeconds, 0.0, 3.0);
        Assert.InRange(w1.Start.TotalSeconds, 0.0, 3.0);
        Assert.InRange(w1.End.TotalSeconds, 0.0, 3.0);
        Assert.InRange(w2.Start.TotalSeconds, 0.0, 3.0);
        Assert.InRange(w2.End.TotalSeconds, 0.0, 3.0);
    }
}
