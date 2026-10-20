using System;
using System.Collections.Generic;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public class RuleBasedAlignerR2OutOfRangeTests
{
    private static AudioClip MakeBurstClip(int sampleRate, double seconds, double burstStartSec, double burstEndSec, double amp = 0.8)
    {
        int totalSamples = (int)Math.Round(sampleRate * seconds);
        var samples = new float[totalSamples];
        for (int i = 0; i < totalSamples; i++)
        {
            double t = (double)i / sampleRate;
            if (t >= burstStartSec && t < burstEndSec)
            {
                samples[i] = (float)(amp * Math.Sin(2 * Math.PI * 440 * t));
            }
            else
            {
                samples[i] = 0f;
            }
        }
        return new AudioClip(sampleRate, 1, samples);
    }

    [Fact]
    public void WordsBeyondClip_ClampedIntoSegment()
    {
        var clip = MakeBurstClip(8000, 2.0, 0.2, 1.8);

        var words = new List<TranscriptWord>
        {
            new TranscriptWord("内容", TimeSpan.FromSeconds(10.0), TimeSpan.FromSeconds(10.5)),
            new TranscriptWord("内容", TimeSpan.FromSeconds(11.0), TimeSpan.FromSeconds(11.5)),
        };
        var rough = new TranscriptDoc(words, TimeSpan.FromSeconds(12));

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.Equal(2, result.Words.Count);

        var lower = TimeSpan.FromSeconds(0.15);
        var upper = TimeSpan.FromSeconds(1.85);

        foreach (var w in result.Words)
        {
            Assert.True(w.Start >= lower, "词起点应位于语音段范围内。");
            Assert.True(w.End <= upper, "词终点应位于语音段范围内。");
        }

        Assert.True(result.Words[0].End <= result.Words[1].Start, "词序应单调递增且不重叠。");
        Assert.Equal(TimeSpan.FromSeconds(2), result.Duration);
    }
}
