using System;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Editing;

/// <summary>
/// 编辑操作基类。所有 op 描述一个作用于源音频时间轴上的区间变换。
/// </summary>
public abstract record EditOp
{
    /// <summary>
    /// 本操作影响的源音频时间区间。
    /// </summary>
    public abstract TimeRange AffectedRange { get; }
}

/// <summary>
/// 删除指定时间区间。
/// </summary>
public sealed record DeleteOp(TimeRange Range) : EditOp
{
    public override TimeRange AffectedRange => Range;
}

/// <summary>
/// 用替换音频覆盖指定区间。
/// 注意：Replacement 的时长可与原区间不同，按 Replacement 的实际时长处理。
/// </summary>
public sealed record ReplaceOp(TimeRange Range, AudioClip Replacement) : EditOp
{
    public override TimeRange AffectedRange => Range;
}

/// <summary>
/// 在指定区间上叠加衰减增益（Db 为负值，例如 -12）。
/// 首尾各 50ms 使用 raised-cosine 过渡，避免增益突变。
/// </summary>
public sealed record AttenuateOp(TimeRange Range, float Db) : EditOp
{
    public override TimeRange AffectedRange => Range;

    /// <summary>
    /// 线性增益系数（0..1）。
    /// </summary>
    public float LinearGain => (float)Math.Pow(10.0, Db / 20.0);
}
