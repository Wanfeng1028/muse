using System;
using VoxLoom.Core.Editing;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class ZeroCrossingDeepTests
{
    [Fact]
    public void NullInputs_ThrowArgumentNullException()
    {
        // 依据：mono 为 null → FindNearest 抛 ArgumentNullException；ApplyShortFade(null, 0, 1) 抛
        Assert.Throws<ArgumentNullException>(() => ZeroCrossing.FindNearest(null!, 0, 10));
        Assert.Throws<ArgumentNullException>(() => ZeroCrossing.ApplyShortFade(null!, 0, 1));
    }

    [Fact]
    public void EmptyArray_ReturnsZero()
    {
        // 依据：空数组返回 0
        int result = ZeroCrossing.FindNearest(Array.Empty<float>(), 0, 10);
        Assert.Equal(0, result);
    }

    [Fact]
    public void AllZeroArray_ReturnsClampedIndex()
    {
        // 依据：(0,0) 不算过零 → 全零数组 index=50 radius=10 返回 50
        var mono = new float[100];
        int result = ZeroCrossing.FindNearest(mono, 50, 10);
        Assert.Equal(50, result);
    }

    [Fact]
    public void ZeroFollowedByNonZero_IsZeroCrossing()
    {
        // 依据：a==0 且 b!=0 算过零 → {0f, 0.5f}, index=1, radius=10 返回 0
        var mono = new float[] { 0f, 0.5f };
        int result = ZeroCrossing.FindNearest(mono, 1, 10);
        Assert.Equal(0, result);
    }

    [Fact]
    public void MultipleCrossings_ReturnsNearest()
    {
        // 依据：多过零点取距离最近者 → {1,-1,1,-1,1}, index=2, radius=10 返回 2
        var mono = new float[] { 1f, -1f, 1f, -1f, 1f };
        int result = ZeroCrossing.FindNearest(mono, 2, 10);
        Assert.Equal(2, result);
    }

    [Fact]
    public void ZeroSearchRadius_ReturnsClampedIndex()
    {
        // 依据：searchRadius<=0 返回钳位后 index → {1,-1}, index=1, radius=0 → 1
        var mono = new float[] { 1f, -1f };
        int result = ZeroCrossing.FindNearest(mono, 1, 0);
        Assert.Equal(1, result);
    }

    [Fact]
    public void NegativeOutOfRangeIndex_NoCrossing_ReturnsZero()
    {
        // 依据：index 钳位到 [0, Length-1]，无过零返回钳位后 index → {1,1,1}, index=-5, radius=10 → 0
        var mono = new float[] { 1f, 1f, 1f };
        int result = ZeroCrossing.FindNearest(mono, -5, 10);
        Assert.Equal(0, result);
    }

    [Fact]
    public void ApplyShortFade_EvenLength_Deterministic()
    {
        // 依据：half=2，前 half 淡入 gain=0.5*(1-cos(pi*i/2))：i=0→0，i=1→0.5；
        // 后 n-half=2 淡出 gain=0.5*(1+cos(pi*i/(fadeOutLen-1)))，fadeOutLen=2：i=0→1，i=1→0
        // 输入全 1 → {0, 0.5, 1, 0}
        var mono = new float[] { 1f, 1f, 1f, 1f };
        ZeroCrossing.ApplyShortFade(mono, 0, 4);
        Assert.Equal(0f, mono[0], 4);
        Assert.Equal(0.5f, mono[1], 4);
        Assert.Equal(1f, mono[2], 4);
        Assert.Equal(0f, mono[3], 4);
    }

    [Fact]
    public void ApplyShortFade_OddLength_Deterministic()
    {
        // 依据：n=3, half=n/2=1，前 1 淡入 gain i=0 → 0；
        // 后 n-half=2 淡出 fadeOutLen=2：i=0→1，i=1→0 → {0, 1, 0}
        var mono = new float[] { 1f, 1f, 1f };
        ZeroCrossing.ApplyShortFade(mono, 0, 3);
        Assert.Equal(0f, mono[0], 4);
        Assert.Equal(1f, mono[1], 4);
        Assert.Equal(0f, mono[2], 4);
    }

    [Fact]
    public void ApplyShortFade_StartOutOfBounds_NoChange()
    {
        // 依据：start 钳位后 n<=0 无操作 → {1f}, start=5, length=10 → 数组不变
        var mono = new float[] { 1f };
        ZeroCrossing.ApplyShortFade(mono, 5, 10);
        Assert.Equal(1f, mono[0], 4);
    }

    [Fact]
    public void ApplyShortFade_ClampCoverage_OnlyTailProcessed()
    {
        // 依据：start=2 length=10 钳位后覆盖 [2,4)，仅处理后两样本
        var mono = new float[] { 1f, 1f, 1f, 1f };
        ZeroCrossing.ApplyShortFade(mono, 2, 10);
        Assert.Equal(1f, mono[0], 4);
        Assert.Equal(1f, mono[1], 4);
        // 处理窗口 n=2, half=1，前 1 淡入 i=0→0；后 1 淡出 fadeOutLen=1 → t 取 1.0 → gain=0.5*(1+cos(pi))=0
        Assert.Equal(0f, mono[2], 4);
        Assert.Equal(0f, mono[3], 4);
    }
}
