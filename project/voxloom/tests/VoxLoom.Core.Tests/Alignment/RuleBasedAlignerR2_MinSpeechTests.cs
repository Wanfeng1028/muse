using System;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Alignment;

public sealed class RuleBasedAlignerR2MinSpeechTests
{
    private static AudioClip BuildBurstClip(int sampleRate, double totalSeconds, double burstStartSec, double burstEndSec, double amp)
    {
        int totalSamples = (int)Math.Round(sampleRate * totalSeconds);
        var samples = new float[totalSamples];
        int startIdx = (int)Math.Round(sampleRate * burstStartSec);
        int endIdx = (int)Math.Round(sampleRate * burstEndSec);
        if (startIdx < 0) startIdx = 0;
        if (endIdx > totalSamples) endIdx = totalSamples;
        for (int i = startIdx; i < endIdx; i++)
        {
            double t = (double)i / sampleRate;
            samples[i] = (float)(amp * Math.Sin(2 * Math.PI * 440 * t));
        }
        return new AudioClip(sampleRate, 1, samples);
    }

    [Fact]
    public void Burst100ms_Kept_WordRemapped()
    {
        var clip = BuildBurstClip(8000, 2.0, 1.0, 1.1, 0.5);
        var word = new TranscriptWord("你好", TimeSpan.FromSeconds(0.2), TimeSpan.FromSeconds(0.3), 1f);
        var rough = new TranscriptDoc(new[] { word }, TimeSpan.FromSeconds(2.0));

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.Single(result.Words);
        var rw = result.Words[0];
        Assert.Equal("你好", rw.Text);
        Assert.True(rw.Start.TotalSeconds >= 0.95 && rw.Start.TotalSeconds <= 1.05,
            $"Start={rw.Start.TotalSeconds}");
        Assert.True(rw.End.TotalSeconds >= 1.05 && rw.End.TotalSeconds <= 1.15,
            $"End={rw.End.TotalSeconds}");
    }

    [Fact]
    public void Burst80ms_Dropped_RoughUnchanged()
    {
        var clip = BuildBurstClip(8000, 2.0, 1.0, 1.08, 0.5);
        var word = new TranscriptWord("你好", TimeSpan.FromSeconds(0.2), TimeSpan.FromSeconds(0.3), 1f);
        var rough = new TranscriptDoc(new[] { word }, TimeSpan.FromSeconds(2.0));

        var result = RuleBasedAligner.Refine(clip, rough);

        Assert.Single(result.Words);
        var rw = result.Words[0];
        Assert.Equal(TimeSpan.FromSeconds(0.2), rw.Start);
        Assert.Equal(TimeSpan.FromSeconds(0.3), rw.End);
        Assert.Equal("你好", rw.Text);
    }
}
