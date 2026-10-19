using System;
using System.Collections.Generic;
using Xunit;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class EditPlanConflictDeepTests
{
    private static AudioClip MakeSrc() => new AudioClip(16000, 1, new float[16000 * 4]);

    private static AudioClip MakeRep() => new AudioClip(16000, 1, new float[16000]);

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——ordered 后 prev=[1s,3s)、curr=[2s,4s)，
    // curr.Start(2s) < prev.End(3s) 为 true，抛 EditConflictException。
    [Fact]
    public void Constructor_ReplaceVsAttenuate_CrossingOverlap_Throws()
    {
        var src = MakeSrc();
        var repClip = MakeRep();
        var ops = new List<EditOp>
        {
            new ReplaceOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(3)), repClip),
            new AttenuateOp(new TimeRange(TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(4)), -12f)
        };

        Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——prev=[0s,4s)、curr=[1s,2s)，
    // curr.Start(1s) < prev.End(4s) 为 true，抛 EditConflictException。
    [Fact]
    public void Constructor_AttenuateContainsDelete_Throws()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new AttenuateOp(new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(4)), -12f),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)))
        };

        Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——三个 [1s,2s) 同区间，
    // 第二与第一比较 curr.Start(1s) < prev.End(2s) 为 true，抛 EditConflictException。
    [Fact]
    public void Constructor_ThreeIdenticalRanges_Throws()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)))
        };

        Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——零时长区间 [1s,1s] 与 [1s,2s) 相邻，
    // curr.Start(1s) < prev.End(1s) 为 false，不抛，构造成功。
    [Fact]
    public void Constructor_ZeroDurationAtBoundary_Allowed()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)))
        };

        var plan = new EditPlan(src, ops);

        Assert.Equal(2, plan.Ops.Count);
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——prev=[0s,2s)、curr=[1s,1s]，
    // curr.Start(1s) < prev.End(2s) 为 true，抛 EditConflictException。
    [Fact]
    public void Constructor_ZeroDurationInsideRange_Throws()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(2))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1)))
        };

        Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——ordered 为 [0s,1s)、[1s,2s)、[1.5s,2.5s)，
    // 第三与第二比较 curr.Start(1.5s) < prev.End(2s) 为 true，抛 EditConflictException。
    [Fact]
    public void Constructor_ChainOverlap_ThirdThrows()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(1))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1.5), TimeSpan.FromSeconds(2.5)))
        };

        Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——[0s,1s)、[1s,2s)、[2s,3s) 全相邻，
    // 每次比较 curr.Start < prev.End 均为 false，不抛；构造成功且 Ops.Count == 3。
    [Fact]
    public void Constructor_ThreeAdjacent_Allowed()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(1))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(3)))
        };

        var plan = new EditPlan(src, ops);

        Assert.Equal(3, plan.Ops.Count);
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——OrderBy(Start) 排序为 [1s,2s)、[4s,5.5s)、[5s,6s)，
    // 第三与第二比较 curr.Start(5s) < prev.End(5.5s) 为 true，抛 EditConflictException。
    [Fact]
    public void Constructor_UnsortedWithConflict_Throws()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(6))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(4), TimeSpan.FromSeconds(5.5)))
        };

        Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——OrderBy 为稳定排序，同 Start(1s) 保持输入顺序，
    // prev=[1s,2s)、curr=[1s,3s)，curr.Start(1s) < prev.End(2s) 为 true，抛 EditConflictException。
    [Fact]
    public void Constructor_SameStartDifferentEnd_Throws()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(3)))
        };

        Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——[0s,1s) 与 [1s,2s) 相邻，
    // curr.Start(1s) < prev.End(1s) 为 false，跨类型也不抛，构造成功。
    [Fact]
    public void Constructor_AttenuateAdjacentToDelete_Allowed()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(1))),
            new AttenuateOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)), -12f)
        };

        var plan = new EditPlan(src, ops);

        Assert.Equal(2, plan.Ops.Count);
    }

    // 事实来源：EditPlan.ValidateNoOverlap 原文逻辑——prev=[0s,1s)、curr=[1s-1tick,2s)，
    // curr.Start(1s-1tick) < prev.End(1s) 为 true，相差 1 tick 即抛 EditConflictException。
    [Fact]
    public void Constructor_OneTickOverlap_Throws()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(1))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1) - TimeSpan.FromTicks(1), TimeSpan.FromSeconds(2)))
        };

        Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));
    }

    // 事实来源：EditConflictException 消息正文包含"编辑计划存在区间重叠"；
    // [0s,2s) 与 [1s,3s) 触发 ValidateNoOverlap 抛出后，Message 应包含"区间重叠"。
    [Fact]
    public void Constructor_ExceptionMessage_ContainsOverlapKeyword()
    {
        var src = MakeSrc();
        var ops = new List<EditOp>
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(2))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(3)))
        };

        var ex = Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));

        Assert.Contains("区间重叠", ex.Message);
    }
}