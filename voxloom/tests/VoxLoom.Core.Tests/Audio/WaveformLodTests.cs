using System;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

public class WaveformLodTests
{
    [Fact]
    public void Levels_TopIsSingleBucket()
    {
        var samples = new float[1000];
        for (int i = 0; i < samples.Length; i++) samples[i] = (float)Math.Sin(i * 0.01);

        var lod = new WaveformLod(samples, bucketSize: 16);
        Assert.True(lod.Levels >= 1);
        Assert.Equal(1, lod.GetBucketCount(lod.Levels - 1));
    }

    [Fact]
    public void Level0_MinMaxCorrect()
    {
        // 构造已知波形：交替 -1 与 +1。
        var samples = new float[512];
        for (int i = 0; i < samples.Length; i++)
        {
            samples[i] = (i % 2 == 0) ? -1f : 1f;
        }

        var lod = new WaveformLod(samples, bucketSize: 128);
        var level0 = lod.GetLevel(0);
        Assert.Equal(4, level0.Length);
        foreach (var (min, max) in level0)
        {
            Assert.Equal(-1f, min);
            Assert.Equal(1f, max);
        }
    }

    [Fact]
    public void GetPeaks_ClipsOutOfRange()
    {
        var samples = new float[300];
        for (int i = 0; i < samples.Length; i++) samples[i] = i / 300f;

        var lod = new WaveformLod(samples, bucketSize: 32);
        // 第 0 级应有 10 个桶。
        Assert.Equal(10, lod.GetBucketCount(0));

        var peaks = lod.GetPeaks(0, 8, 10);
        Assert.Equal(2, peaks.Length);
        Assert.True(peaks[0].Min <= peaks[0].Max);
        Assert.True(peaks[1].Min <= peaks[1].Max);
    }

    [Fact]
    public void EmptySamples_ZeroLevels()
    {
        var lod = new WaveformLod(Array.Empty<float>());
        Assert.Equal(0, lod.Levels);
        Assert.Empty(lod.GetLevel(0));
        Assert.Empty(lod.GetPeaks(0, 0, 10));
    }
}
