using System;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2AllZeroTests
{
    [Fact]
    public void Refine_AllZeroClip_ReturnsRough()
    {
        int sampleRate = 8000;
        float[] samples = new float[sampleRate * 2];
        var clip = new AudioClip(sampleRate, 1, samples);

        var word1 = new TranscriptWord("内容", TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(0.6));
        var word2 = new TranscriptWord("内容", TimeSpan.FromSeconds(1.0), TimeSpan.FromSeconds(1.1));
        var rough = new TranscriptDoc(new[] { word1, word2 }, clip.Duration);

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.Equal(2, result.Words.Count);
        Assert.Equal(word1.Start, result.Words[0].Start);
        Assert.Equal(word1.End, result.Words[0].End);
        Assert.Equal(word2.Start, result.Words[1].Start);
        Assert.Equal(word2.End, result.Words[1].End);
    }
}
