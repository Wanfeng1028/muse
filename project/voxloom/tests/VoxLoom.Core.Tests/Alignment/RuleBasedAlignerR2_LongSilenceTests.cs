using System;
using System.Collections.Generic;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2LongSilenceTests
{
    private static AudioClip BuildTwoBurstClip(int sampleRate, double totalSeconds)
    {
        int totalSamples = (int)(sampleRate * totalSeconds);
        var samples = new float[totalSamples];

        void FillBurst(double startSec, double endSec, double freq, double amp)
        {
            int s = (int)(startSec * sampleRate);
            int e = (int)(endSec * sampleRate);
            if (s < 0) s = 0;
            if (e > totalSamples) e = totalSamples;
            for (int i = s; i < e; i++)
            {
                double t = (double)i / sampleRate;
                samples[i] = (float)(amp * Math.Sin(2 * Math.PI * freq * t));
            }
        }

        FillBurst(0.5, 1.0, 440.0, 0.5);
        FillBurst(5.5, 6.0, 440.0, 0.5);
        return new AudioClip(sampleRate, 1, samples);
    }

    [Fact]
    public void TwoBurstsSeparated_WordsInRespectiveSegments()
    {
        var clip = BuildTwoBurstClip(8000, 7.0);

        var rough = new TranscriptDoc(
            new List<TranscriptWord>
            {
                new TranscriptWord("内容", TimeSpan.FromSeconds(0.1), TimeSpan.FromSeconds(0.2)),
                new TranscriptWord("内容", TimeSpan.FromSeconds(6.3), TimeSpan.FromSeconds(6.4)),
            },
            TimeSpan.FromSeconds(7.0));

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.Equal(2, result.Words.Count);

        var w1 = result.Words[0];
        var w2 = result.Words[1];

        Assert.True(w1.Start >= TimeSpan.FromSeconds(0.45), $"w1.Start={w1.Start}");
        Assert.True(w1.End <= TimeSpan.FromSeconds(1.05), $"w1.End={w1.End}");

        Assert.True(w2.Start >= TimeSpan.FromSeconds(5.45), $"w2.Start={w2.Start}");
        Assert.True(w2.End <= TimeSpan.FromSeconds(6.05), $"w2.End={w2.End}");

        Assert.True(w1.End <= w2.Start, $"w1.End={w1.End}, w2.Start={w2.Start}");
    }
}
