using System;
using VoxLoom.Core.Audio;
using Xunit;

namespace VoxLoom.Core.Tests.Audio;

public class WaveformLodEdgeDeepTests
{
    // 事实来源：构造函数首行 ArgumentNullException.ThrowIfNull(monoSamples)。
    [Fact]
    public void Constructor_NullSamples_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(() => new WaveformLod(null!));
    }

    // 事实来源：构造函数 bucketSize <= 0 抛出 ArgumentOutOfRangeException。
    [Fact]
    public void Constructor_ZeroBucketSize_ThrowsArgumentOutOfRangeException()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => new WaveformLod(new[] { 0.1f }, 0));
    }

    // 事实来源：构造函数 bucketSize <= 0 抛出 ArgumentOutOfRangeException。
    [Fact]
    public void Constructor_NegativeBucketSize_ThrowsArgumentOutOfRangeException()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => new WaveformLod(new[] { 0.1f }, -5));
    }

    // 事实来源：GetLevel 中 level < 0 || level >= Levels 返回 Array.Empty。
    [Fact]
    public void GetLevel_NegativeLevel_ReturnsEmpty()
    {
        var lod = new WaveformLod(new[] { 0.5f, -0.3f, 0.8f }, 2);
        var result = lod.GetLevel(-1);
        Assert.Empty(result);
    }

    // 事实来源：GetLevel 中 level < 0 || level >= Levels 返回 Array.Empty。
    [Fact]
    public void GetLevel_LevelEqualsLevels_ReturnsEmpty()
    {
        var lod = new WaveformLod(new[] { 0.5f, -0.3f, 0.8f }, 2);
        var result = lod.GetLevel(lod.Levels);
        Assert.Empty(result);
    }

    // 事实来源：GetBucketCount 中越界返回 0。
    [Fact]
    public void GetBucketCount_NegativeLevel_ReturnsZero()
    {
        var lod = new WaveformLod(new[] { 0.5f, -0.3f, 0.8f }, 2);
        Assert.Equal(0, lod.GetBucketCount(-1));
    }

    // 事实来源：GetBucketCount 中越界返回 0。
    [Fact]
    public void GetBucketCount_OutOfRangeLevel_ReturnsZero()
    {
        var lod = new WaveformLod(new[] { 0.5f, -0.3f, 0.8f }, 2);
        Assert.Equal(0, lod.GetBucketCount(999));
    }

    // 事实来源：GetPeaks 中 level 越界返回空。
    [Fact]
    public void GetPeaks_LevelOutOfRange_ReturnsEmpty()
    {
        var lod = new WaveformLod(new[] { 0.5f, -0.3f, 0.8f }, 2);
        var result = lod.GetPeaks(999, 0, 1);
        Assert.Empty(result);
    }

    // 事实来源：GetPeaks 中 count <= 0 返回空。
    [Fact]
    public void GetPeaks_ZeroCount_ReturnsEmpty()
    {
        var lod = new WaveformLod(new[] { 0.5f, -0.3f, 0.8f }, 2);
        var result = lod.GetPeaks(0, 0, 0);
        Assert.Empty(result);
    }

    // 事实来源：GetPeaks 中 count <= 0 返回空。
    [Fact]
    public void GetPeaks_NegativeCount_ReturnsEmpty()
    {
        var lod = new WaveformLod(new[] { 0.5f, -0.3f, 0.8f }, 2);
        var result = lod.GetPeaks(0, 5, -2);
        Assert.Empty(result);
    }

    // 事实来源：GetPeaks 中 start < 0 裁为 0，end > total 裁为 total。
    [Fact]
    public void GetPeaks_NegativeStart_ClampsToZeroAndReturnsAll()
    {
        var lod = new WaveformLod(new[] { 0.1f, 0.2f, 0.3f, 0.4f }, 1);
        Assert.Equal(4, lod.GetBucketCount(0));
        var result = lod.GetPeaks(0, -2, 10);
        Assert.Equal(4, result.Length);
    }

    // 事实来源：level0 分桶聚合逻辑（首元素初始化，后续比较 min/max）。
    [Fact]
    public void GetLevel_Level0_MinMaxAggregationIsCorrect()
    {
        var lod = new WaveformLod(new[] { 0.5f, -0.3f, 0.8f }, 2);
        var level0 = lod.GetLevel(0);
        Assert.Equal(2, level0.Length);
        Assert.Equal(-0.3f, level0[0].Min);
        Assert.Equal(0.5f, level0[0].Max);
        Assert.Equal(0.8f, level0[1].Min);
        Assert.Equal(0.8f, level0[1].Max);
    }

    // 事实来源：while 循环逐级聚合直到顶级只剩 1 个桶。
    [Fact]
    public void Levels_512Samples_BucketSize256_ProducesTwoLevels()
    {
        var samples = new float[512];
        for (int i = 0; i < samples.Length; i++) samples[i] = (i % 2 == 0) ? 0.1f : -0.1f;
        var lod = new WaveformLod(samples, 256);
        Assert.Equal(2, lod.Levels);
        Assert.Equal(2, lod.GetBucketCount(0));
        Assert.Equal(1, lod.GetBucketCount(1));
    }

    // 事实来源：level0Count = (monoSamples.Length + bucketSize - 1) / bucketSize。
    [Fact]
    public void GetBucketCount_NonDivisibleLength_RoundsUp()
    {
        var lod = new WaveformLod(new[] { 0.1f, 0.2f, 0.3f }, 2);
        Assert.Equal(2, lod.GetBucketCount(0));
    }

    // 事实来源：GetLevel 每次 new 新数组返回，修改返回值不影响内部状态。
    [Fact]
    public void GetLevel_ReturnsNewArray_ModificationDoesNotAffectInternalState()
    {
        var lod = new WaveformLod(new[] { 0.5f, -0.3f, 0.8f }, 2);
        var first = lod.GetLevel(0);
        first[0] = (99f, 99f);
        var second = lod.GetLevel(0);
        Assert.Equal(-0.3f, second[0].Min);
        Assert.Equal(0.5f, second[0].Max);
    }

    // 事实来源：单样本时 level0 桶初始化并 Levels == 1。
    [Fact]
    public void SingleSample_ProducesOneLevelWithSameMinMax()
    {
        var lod = new WaveformLod(new[] { 0.7f }, 256);
        Assert.Equal(1, lod.Levels);
        var level0 = lod.GetLevel(0);
        Assert.Equal(1, level0.Length);
        Assert.Equal(0.7f, level0[0].Min);
        Assert.Equal(0.7f, level0[0].Max);
    }

    // 事实来源：level0 分桶聚合逻辑对全负样本仍取正确 min/max。
    [Fact]
    public void GetLevel_AllNegativeSamples_MinMaxIsCorrect()
    {
        var lod = new WaveformLod(new[] { -0.9f, -0.1f }, 2);
        var level0 = lod.GetLevel(0);
        Assert.Equal(1, level0.Length);
        Assert.Equal(-0.9f, level0[0].Min);
        Assert.Equal(-0.1f, level0[0].Max);
    }
}