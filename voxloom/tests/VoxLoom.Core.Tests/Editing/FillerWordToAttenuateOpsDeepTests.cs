using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class FillerWordToAttenuateOpsDeepTests
{
    // 依据：ToAttenuateOps 源码 `ops[i] = new AttenuateOp(ranges[i], db);`，
    // 默认参数 db = -12f；AttenuateOp 是 record，AffectedRange => Range。
    [Fact]
    public void ToAttenuateOps_RangeAlignsWithSingleHit()
    {
        var ranges = new List<TimeRange>
        {
            new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(0.5))
        };

        var ops = FillerWordDetector.ToAttenuateOps(ranges);

        Assert.Single(ops);
        var op = Assert.IsType<AttenuateOp>(ops[0]);
        Assert.Equal(TimeSpan.Zero, op.AffectedRange.Start);
        Assert.Equal(TimeSpan.FromSeconds(0.5), op.AffectedRange.End);
        Assert.Equal(-12f, op.Db);
    }

    // 依据：循环 `for (int i = 0; i < ranges.Count; i++)` 按索引顺序写入 ops[i]，
    // 每个 ops[i] 的 Range 即 ranges[i]，顺序与数量一一对应。
    [Fact]
    public void ToAttenuateOps_PreservesOrderAndCount()
    {
        var r0 = new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(0.5));
        var r1 = new TimeRange(TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(5.5));
        var r2 = new TimeRange(TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(11));
        var ranges = new List<TimeRange> { r0, r1, r2 };

        var ops = FillerWordDetector.ToAttenuateOps(ranges);

        Assert.Equal(3, ops.Length);
        Assert.Equal(r0, ((AttenuateOp)ops[0]).AffectedRange);
        Assert.Equal(r1, ((AttenuateOp)ops[1]).AffectedRange);
        Assert.Equal(r2, ((AttenuateOp)ops[2]).AffectedRange);
    }

    // 依据：ToAttenuateOps(ranges, db) 把 db 直接传给 AttenuateOp 构造器；
    // LinearGain => 10^(Db/20)；Db=-6 时 10^(-0.3) ≈ 0.501187...，落在 [0.50118, 0.50120]。
    [Fact]
    public void ToAttenuateOps_DbPassthrough()
    {
        var ranges = new List<TimeRange>
        {
            new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(0.5))
        };

        var ops = FillerWordDetector.ToAttenuateOps(ranges, -6f);

        var op = Assert.IsType<AttenuateOp>(ops[0]);
        Assert.Equal(-6f, op.Db);
        Assert.InRange(op.LinearGain, 0.50118f, 0.50120f);
    }

    // 依据：签名 `float db = -12f`，不传时默认值为 -12f，直接写入 AttenuateOp。
    [Fact]
    public void ToAttenuateOps_DefaultDb_IsMinusTwelve()
    {
        var ranges = new List<TimeRange>
        {
            new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1.5))
        };

        var ops = FillerWordDetector.ToAttenuateOps(ranges);

        Assert.Equal(-12f, ((AttenuateOp)ops[0]).Db);
    }

    // 依据：`var ops = new EditOp[ranges.Count];`，Count==0 时数组长度 0；
    // 源码未返回 null（无 early-return null 分支），返回的是空数组实例。
    [Fact]
    public void ToAttenuateOps_EmptyRanges_ReturnsEmpty()
    {
        var ranges = new List<TimeRange>();

        var ops = FillerWordDetector.ToAttenuateOps(ranges);

        Assert.NotNull(ops);
        Assert.Empty(ops);
        Assert.Equal(0, ops.Length);
    }

    // 依据：源码首行 `ArgumentNullException.ThrowIfNull(ranges);`，null 时抛出。
    [Fact]
    public void ToAttenuateOps_NullRanges_ThrowsArgumentNull()
    {
        Assert.Throws<ArgumentNullException>(() => FillerWordDetector.ToAttenuateOps(null!));
    }

    // 依据：AttenuateOp 是 record，AffectedRange 直接返回构造传入的 Range；
    // 两个不同 Range 构造的 op，其 AffectedRange 不相等（record struct 值语义比较）。
    [Fact]
    public void ToAttenuateOps_EachOpIsIndependentRecord()
    {
        var ranges = new List<TimeRange>
        {
            new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(0.5)),
            new TimeRange(TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(5.5))
        };

        var ops = FillerWordDetector.ToAttenuateOps(ranges);

        Assert.NotEqual(
            ((AttenuateOp)ops[0]).AffectedRange,
            ((AttenuateOp)ops[1]).AffectedRange);
    }

    // 依据：LinearGain => 10^(Db/20)；Db=0 时 10^0 = 1.0；
    // 用 4 位小数精度断言 Equal(1.0f, gain, 4)。
    [Fact]
    public void ToAttenuateOps_ZeroDb_NoAttenuation()
    {
        var ranges = new List<TimeRange>
        {
            new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(0.25))
        };

        var ops = FillerWordDetector.ToAttenuateOps(ranges, 0f);

        var op = Assert.IsType<AttenuateOp>(ops[0]);
        Assert.Equal(0f, op.Db);
        Assert.Equal(1.0f, op.LinearGain, 4);
    }
}
