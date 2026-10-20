using System;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2EmptyRoughTests
{
    [Fact]
    public void Refine_EmptyWords_ReturnsRoughInstance()
    {
        int sampleRate = 8000;
        int samplesCount = sampleRate;
        var samples = new float[samplesCount];
        for (int i = 0; i < samplesCount; i++)
        {
            double t = (double)i / sampleRate;
            samples[i] = (float)(0.5 * Math.Sin(2 * Math.PI * 440 * t));
        }

        var clip = new AudioClip(sampleRate, 1, samples);
        var rough = TranscriptDoc.Empty;

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.Same(rough, result);
    }
}
