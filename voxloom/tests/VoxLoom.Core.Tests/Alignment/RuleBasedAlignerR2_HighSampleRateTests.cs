using System;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2HighSampleRateTests
{
    private static AudioClip BuildClip(int sampleRate, int channels, double durationSec, double burstStartSec, double burstEndSec, double amp)
    {
        int frames = (int)Math.Round(sampleRate * durationSec);
        var samples = new float[frames * channels];
        for (int f = 0; f < frames; f++)
        {
            double t = (double)f / sampleRate;
            float v = 0f;
            if (t >= burstStartSec && t < burstEndSec)
            {
                v = (float)(amp * Math.Sin(2.0 * Math.PI * 440.0 * t));
            }
            for (int c = 0; c < channels; c++)
            {
                samples[f * channels + c] = v;
            }
        }
        return new AudioClip(sampleRate, channels, samples);
    }

    [Fact]
    public void Refine_44100Hz_Aligns()
    {
        var clip = BuildClip(44100, 1, 2.0, 0.2, 0.5, 0.5);

        var words = new[]
        {
            new TranscriptWord("内容", TimeSpan.FromSeconds(0.05), TimeSpan.FromSeconds(0.1), 1f)
        };
        var rough = new TranscriptDoc(words, TimeSpan.FromSeconds(2.0));

        var refined = RuleBasedAligner.Refine(clip, rough);

        Assert.NotNull(refined);
        Assert.Single(refined.Words);

        var w = refined.Words[0];
        Assert.Equal("内容", w.Text);

        double startSec = w.Start.TotalSeconds;
        double endSec = w.End.TotalSeconds;

        Assert.True(startSec >= 0.15 && startSec <= 0.3, $"Start was {startSec}");
        Assert.True(endSec >= 0.4 && endSec <= 0.6, $"End was {endSec}");
        Assert.True(endSec > startSec, "End must be after Start");
    }
}
