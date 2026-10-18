using System;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EditOpRecordDeepTests
{
    // 构造一个满足 AudioClip 约束的最小合法实例：sampleRate=1、channels=1、samples 长度 1（1 的整数倍）。
    private static AudioClip MakeClip()
    {
        return new AudioClip(1, 1, new float[] { 0.5f });
    }

    [Fact]
    public void DeleteOp_AffectedRange_ReturnsRange()
    {
        // 事实来源：DeleteOp(TimeRange Range) 的 AffectedRange => Range，故 AffectedRange 即构造传入区间。
        var range = new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2));
        var op = new DeleteOp(range);

        // Start/End 逐项断言，机械对应 TimeRange.Start/End。
        Assert.Equal(TimeSpan.FromSeconds(1), op.AffectedRange.Start);
        Assert.Equal(TimeSpan.FromSeconds(2), op.AffectedRange.End);
    }

    [Fact]
    public void ReplaceOp_AffectedRange_And_ReplacementPreserved()
    {
        // 事实来源：ReplaceOp(TimeRange Range, AudioClip Replacement) 自动生成 Replacement 属性。
        var range = new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(3));
        var clip = MakeClip();
        var op = new ReplaceOp(range, clip);

        // 引用同一性：record 位置参数生成的属性保存原引用。
        Assert.Same(clip, op.Replacement);

        // AffectedRange => Range，故等于构造区间。
        Assert.Equal(TimeSpan.FromSeconds(0), op.AffectedRange.Start);
        Assert.Equal(TimeSpan.FromSeconds(3), op.AffectedRange.End);
    }

    [Fact]
    public void AttenuateOp_AffectedRange_And_DbPreserved()
    {
        // 事实来源：AttenuateOp(TimeRange Range, float Db) 保存 Db 原值，AffectedRange => Range。
        var range = new TimeRange(TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(7));
        var op = new AttenuateOp(range, -12f);

        Assert.Equal(-12f, op.Db);
        Assert.Equal(TimeSpan.FromSeconds(5), op.AffectedRange.Start);
        Assert.Equal(TimeSpan.FromSeconds(7), op.AffectedRange.End);
    }

    [Fact]
    public void AttenuateOp_PositiveDb_GainAboveOne()
    {
        // 事实来源：LinearGain = 10^(Db/20)。Db=6 → 10^(0.3)。
        // 10^0.3 ≈ 1.9952623149688795，取 4 位小数精度比较 1.9953。
        var range = new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(1));
        var op = new AttenuateOp(range, 6f);

        float gain = op.LinearGain;

        Assert.True(gain > 1f);
        Assert.Equal(1.9953f, gain, 4);
    }

    [Fact]
    public void AttenuateOp_LinearGain_Monotonic()
    {
        // 事实来源：LinearGain = 10^(Db/20) 关于 Db 单调递增。
        // 故 Db=-12 的增益严格小于 Db=-6 的增益。
        var range = new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(1));
        float g12 = new AttenuateOp(range, -12f).LinearGain;
        float g6 = new AttenuateOp(range, -6f).LinearGain;

        Assert.True(g12 < g6);
    }

    [Fact]
    public void Record_ValueEquality()
    {
        // 事实来源：EditOp 系列均为 record，值相等性由位置参数与属性决定。
        var r1 = new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2));
        var r2 = new TimeRange(TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(4));

        var a = new DeleteOp(r1);
        var b = new DeleteOp(r1);
        var c = new DeleteOp(r2);

        Assert.Equal(a, b);
        Assert.NotEqual(a, c);
    }

    [Fact]
    public void Record_WithExpression()
    {
        // 事实来源：record 支持 with 表达式，仅替换指定属性，其余属性复制。
        var range = new TimeRange(TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(6));
        var op1 = new AttenuateOp(range, -12f);

        var op2 = op1 with { Db = -6f };

        Assert.Equal(-6f, op2.Db);
        Assert.Equal(op1.Range, op2.Range);
        // 原实例不变。
        Assert.Equal(-12f, op1.Db);
    }

    [Fact]
    public void EditOp_PolymorphicDispatch()
    {
        // 事实来源：三个子类均 override AffectedRange => Range。
        // 通过基类 EditOp 引用访问 AffectedRange，应多态派发到各子类实现。
        var rDel = new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2));
        var rRep = new TimeRange(TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(4));
        var rAtt = new TimeRange(TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(6));

        EditOp[] ops =
        {
            new DeleteOp(rDel),
            new ReplaceOp(rRep, MakeClip()),
            new AttenuateOp(rAtt, -3f),
        };

        Assert.Equal(TimeSpan.FromSeconds(1), ops[0].AffectedRange.Start);
        Assert.Equal(TimeSpan.FromSeconds(3), ops[1].AffectedRange.Start);
        Assert.Equal(TimeSpan.FromSeconds(5), ops[2].AffectedRange.Start);

        // Start 两两互异，验证是三个不同区间被正确派发。
        Assert.NotEqual(ops[0].AffectedRange.Start, ops[1].AffectedRange.Start);
        Assert.NotEqual(ops[1].AffectedRange.Start, ops[2].AffectedRange.Start);
        Assert.NotEqual(ops[0].AffectedRange.Start, ops[2].AffectedRange.Start);
    }
}
