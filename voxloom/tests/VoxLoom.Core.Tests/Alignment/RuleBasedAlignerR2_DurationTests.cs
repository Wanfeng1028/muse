using System;
using System.Collections.Generic;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2DurationTests
{
    private static AudioClip MakeBurst(int sampleRate, double seconds, double amp = 0.8, double freq = 440.0)
    {
        int total = (int)Math.Round(sampleRate * seconds);
        var samples = new float[total];
        for (int i = 0; i < total; i++)
        {
            double t = (double)i / sampleRate;
            samples[i] = (float)(amp * Math.Sin(2 * Math.PI * freq * t));
        }
        return new AudioClip(sampleRate, 1, samples);
    }

    [Fact]
    public void Refine_ResultDuration_EqualsClipDuration()
    {
        var clip = MakeBurst(8000, 2.0);

        var words = new List<TranscriptWord>
        {
            new TranscriptWord("你好", TimeSpan.FromSeconds(0.0), TimeSpan.FromSeconds(0.5), 0.9f),
            new TranscriptWord("世界", TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(1.0), 0.9f)
        };
        var rough = new TranscriptDoc(words, TimeSpan.FromSeconds(10));

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.NotNull(result);
        Assert.Equal(TimeSpan.FromSeconds(2), result.Duration);
    }
}
