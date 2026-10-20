using System;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2NoiseFloorTests
{
    [Fact]
    public void QuietBackground_BurstDetected()
    {
        const int sampleRate = 8000;
        const double durationSec = 4.0;
        int totalSamples = (int)(sampleRate * durationSec);
        var samples = new float[totalSamples];

        for (int i = 0; i < totalSamples; i++)
        {
            double t = (double)i / sampleRate;
            if (t >= 1.0 && t < 2.0)
            {
                samples[i] = (float)(0.5 * Math.Sin(2 * Math.PI * 440 * t));
            }
            else
            {
                samples[i] = (float)(0.01 * Math.Sin(2 * Math.PI * 440 * t));
            }
        }

        var clip = new AudioClip(sampleRate, 1, samples);
        var roughWords = new[]
        {
            new TranscriptWord("词", TimeSpan.FromSeconds(0.2), TimeSpan.FromSeconds(0.3), 1f)
        };
        var rough = new TranscriptDoc(roughWords, TimeSpan.FromSeconds(durationSec));

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.Single(result.Words);
        var w = result.Words[0];
        Assert.True(w.Start.TotalSeconds >= 0.95, $"Start was {w.Start.TotalSeconds}");
        Assert.True(w.Start.TotalSeconds <= 1.1, $"Start was {w.Start.TotalSeconds}");
        Assert.True(w.End.TotalSeconds >= 1.9, $"End was {w.End.TotalSeconds}");
        Assert.True(w.End.TotalSeconds <= 2.1, $"End was {w.End.TotalSeconds}");
    }
}
