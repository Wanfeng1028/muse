using System;
using Xunit;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Transcript;

public class TranscriptWordEdgeDeepTests
{
    // 事实来源：ToString() => $"{Start:mm\\:ss\\.fff}-{End:mm\\:ss\\.fff} {Text} ({Confidence:F2})" 的格式化行为。
    [Fact]
    public void ToString_FormatsTimesTextAndConfidence()
    {
        var word = new TranscriptWord("hi", TimeSpan.FromSeconds(61.5), TimeSpan.FromSeconds(62.25), 0.9f);

        Assert.Equal("01:01.500-01:02.250 hi (0.90)", word.ToString());
    }

    // 事实来源：Duration => End - Start。
    [Fact]
    public void Duration_EqualsEndMinusStart()
    {
        var word = new TranscriptWord("w", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2.5));

        Assert.Equal(TimeSpan.FromSeconds(1.5), word.Duration);
    }

    // 事实来源：Confidence = float.IsNaN(confidence) ? 0f : Math.Clamp(confidence, 0f, 1f)。
    [Fact]
    public void Confidence_NaN_BecomesZero()
    {
        var word = new TranscriptWord("w", TimeSpan.Zero, TimeSpan.FromSeconds(1), float.NaN);

        Assert.Equal(0f, word.Confidence);
    }

    // 事实来源：Confidence = Math.Clamp(confidence, 0f, 1f) 的上界裁剪。
    [Fact]
    public void Confidence_AboveOne_ClampedToOne()
    {
        var word = new TranscriptWord("w", TimeSpan.Zero, TimeSpan.FromSeconds(1), 1.5f);

        Assert.Equal(1f, word.Confidence);
    }

    // 事实来源：Confidence = Math.Clamp(confidence, 0f, 1f) 的下界裁剪。
    [Fact]
    public void Confidence_BelowZero_ClampedToZero()
    {
        var word = new TranscriptWord("w", TimeSpan.Zero, TimeSpan.FromSeconds(1), -0.5f);

        Assert.Equal(0f, word.Confidence);
    }

    // 事实来源：仅检查 if (start > end)，故 start == end 允许且 Duration => End - Start 为零。
    [Fact]
    public void StartEqualsEnd_Allowed_AndDurationZero()
    {
        var word = new TranscriptWord("w", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1));

        Assert.Equal(TimeSpan.Zero, word.Duration);
    }

    // 事实来源：if (start > end) throw new ArgumentException(..., nameof(start))。
    [Fact]
    public void StartGreaterThanEnd_ThrowsArgumentException_WithParamNameStart()
    {
        var ex = Assert.Throws<ArgumentException>(() =>
            new TranscriptWord("w", TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(1)));

        Assert.Equal("start", ex.ParamName);
    }

    // 事实来源：if (text is null) throw new ArgumentNullException(nameof(text))。
    [Fact]
    public void NullText_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(() =>
            new TranscriptWord(null!, TimeSpan.Zero, TimeSpan.FromSeconds(1)));
    }

    // 事实来源：sealed record 的值相等性。
    [Fact]
    public void RecordEquality_SameValues_AreEqual()
    {
        var a = new TranscriptWord("hi", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2), 0.5f);
        var b = new TranscriptWord("hi", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2), 0.5f);

        Assert.Equal(a, b);
    }

    // 事实来源：sealed record 的值相等性中 Text 参与比较。
    [Fact]
    public void RecordEquality_DifferentText_AreNotEqual()
    {
        var a = new TranscriptWord("hi", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2), 0.5f);
        var b = new TranscriptWord("bye", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2), 0.5f);

        Assert.NotEqual(a, b);
    }

    // 事实来源：Contains(t) => t >= Start && t < End 的左闭右开语义（含左端点）。
    [Fact]
    public void Contains_LeftBoundary_ReturnsTrue()
    {
        var word = new TranscriptWord("w", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2));

        Assert.True(word.Contains(TimeSpan.FromSeconds(1)));
    }

    // 事实来源：Contains(t) => t >= Start && t < End 的左闭右开语义（不含右端点）。
    [Fact]
    public void Contains_RightBoundary_ReturnsFalse()
    {
        var word = new TranscriptWord("w", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2));

        Assert.False(word.Contains(TimeSpan.FromSeconds(2)));
    }

    // 事实来源：Contains(t) => t >= Start && t < End 的区间外语义。
    [Fact]
    public void Contains_BeforeStart_ReturnsFalse()
    {
        var word = new TranscriptWord("w", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2));

        Assert.False(word.Contains(TimeSpan.FromSeconds(0.5)));
    }

    // 事实来源：构造函数签名 confidence = 1f 的默认值。
    [Fact]
    public void DefaultConfidence_IsOne()
    {
        var word = new TranscriptWord("w", TimeSpan.Zero, TimeSpan.FromSeconds(1));

        Assert.Equal(1f, word.Confidence);
    }
}