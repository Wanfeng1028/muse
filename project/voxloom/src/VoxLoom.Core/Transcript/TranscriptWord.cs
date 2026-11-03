using System;

namespace VoxLoom.Core.Transcript;

/// <summary>
/// 转写词条：文本、起止时间、置信度。
/// </summary>
public sealed record TranscriptWord
{
    /// <summary>词文本。</summary>
    public string Text { get; }

    /// <summary>起始时间。</summary>
    public TimeSpan Start { get; }

    /// <summary>结束时间。</summary>
    public TimeSpan End { get; }

    /// <summary>置信度，范围 [0, 1]。</summary>
    public float Confidence { get; }

    /// <summary>构造词条，Start 必须早于 End，置信度会被裁剪到 [0, 1]。</summary>
    public TranscriptWord(string text, TimeSpan start, TimeSpan end, float confidence = 1f)
    {
        if (text is null)
        {
            throw new ArgumentNullException(nameof(text));
        }

        if (start > end)
        {
            throw new ArgumentException($"词条起始时间({start})不能晚于结束时间({end})。", nameof(start));
        }

        Text = text;
        Start = start;
        End = end;
        Confidence = float.IsNaN(confidence) ? 0f : Math.Clamp(confidence, 0f, 1f);
    }

    /// <summary>词持续时间。</summary>
    public TimeSpan Duration => End - Start;

    /// <summary>该词时间区间内是否包含给定时刻（左闭右开）。</summary>
    public bool Contains(TimeSpan t) => t >= Start && t < End;

    /// <inheritdoc />
    public override string ToString() => $"{Start:mm\\:ss\\.fff}-{End:mm\\:ss\\.fff} {Text} ({Confidence:F2})";
}
