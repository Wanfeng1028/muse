using System;
using System.Collections.Generic;
using Xunit;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2StereoTests
{
    [Fact]
    public void Refine_StereoClip_Aligns()
    {
        const int sampleRate = 8000;
        const int channels = 2;
        double durationSec = 2.0;
        int frames = (int)(sampleRate * durationSec);
        var samples = new float[frames * channels];

        for (int f = 0; f < frames; f++)
        {
            double t = (double)f / sampleRate;
            float value = 0f;
            if (t >= 0.5 && t < 1.0)
            {
                value = (float)(0.5 * Math.Sin(2 * Math.PI * 440 * t));
            }
            samples[f * channels + 0] = value;
            samples[f * channels + 1] = value;
        }

        var clip = new AudioClip(sampleRate, channels, samples);
        Assert.Equal(channels, clip.Channels);
        Assert.Equal(frames, clip.Frames);

        var roughWords = new List<TranscriptWord>
        {
            new TranscriptWord("内容", TimeSpan.FromSeconds(0.1), TimeSpan.FromSeconds(0.2), 1f)
        };
        var rough = new TranscriptDoc(roughWords, TimeSpan.FromSeconds(durationSec));

        var refined = RuleBasedAligner.Refine(clip, rough);

        Assert.NotNull(refined);
        Assert.Single(refined.Words);

        var word = refined.Words[0];
        Assert.Equal("内容", word.Text);
        Assert.InRange(word.Start.TotalSeconds, 0.45, 0.6);
        Assert.InRange(word.End.TotalSeconds, 0.9, 1.1);
    }
}
