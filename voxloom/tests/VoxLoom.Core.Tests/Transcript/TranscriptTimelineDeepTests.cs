using System;
using System.Collections.Generic;
using System.Linq;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Transcript;

public sealed class TranscriptTimelineDeepTests
{
    private static TranscriptWord W(string text, double startSec, double endSec, float conf = 1f)
        => new TranscriptWord(text, TimeSpan.FromSeconds(startSec), TimeSpan.FromSeconds(endSec), conf);

    // 1. Confidence 裁剪规则：NaN→0；>1→1；<0→0；边界值保持。
    [Fact]
    public void TranscriptWord_ConfidenceClamping()
    {
        var nan = new TranscriptWord("a", TimeSpan.Zero, TimeSpan.FromSeconds(1), float.NaN);
        var high = new TranscriptWord("a", TimeSpan.Zero, TimeSpan.FromSeconds(1), 1.5f);
        var low = new TranscriptWord("a", TimeSpan.Zero, TimeSpan.FromSeconds(1), -0.3f);
        var zero = new TranscriptWord("a", TimeSpan.Zero, TimeSpan.FromSeconds(1), 0f);
        var one = new TranscriptWord("a", TimeSpan.Zero, TimeSpan.FromSeconds(1), 1f);

        Assert.Equal(0f, nan.Confidence, 6);
        Assert.Equal(1f, high.Confidence, 6);
        Assert.Equal(0f, low.Confidence, 6);
        Assert.Equal(0f, zero.Confidence, 6);
        Assert.Equal(1f, one.Confidence, 6);
    }

    // 2. start==end 允许，Duration 为 0。
    [Fact]
    public void TranscriptWord_ZeroDurationAllowed()
    {
        var w = new TranscriptWord("x", TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(3));
        Assert.Equal(TimeSpan.Zero, w.Duration);
    }

    // 3. text 为 null 抛 ArgumentNullException。
    [Fact]
    public void TranscriptWord_NullText_Throws()
    {
        Assert.Throws<ArgumentNullException>(() =>
            new TranscriptWord(null!, TimeSpan.Zero, TimeSpan.FromSeconds(1)));
    }

    // 4. Contains 左闭右开：t==Start 命中，t==End 不命中，区间内命中。
    [Fact]
    public void TranscriptWord_Contains_LeftClosedRightOpen()
    {
        var w = new TranscriptWord("x", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2));
        Assert.True(w.Contains(TimeSpan.FromSeconds(1)));
        Assert.False(w.Contains(TimeSpan.FromSeconds(2)));
        Assert.True(w.Contains(TimeSpan.FromSeconds(1.5)));
    }

    // 5. ToString 格式："mm:ss.fff-mm:ss.fff text (C.F2)"，61.5s → 01:01.500。
    [Fact]
    public void TranscriptWord_ToString_Format()
    {
        var w = new TranscriptWord("hello", TimeSpan.FromSeconds(61.5), TimeSpan.FromSeconds(62.25), 0.95f);
        Assert.Equal("01:01.500-01:02.250 hello (0.95)", w.ToString());
    }

    // 6. TimeRange.Duration 为 End-Start；Contains 左闭右开，t==End 不包含。
    [Fact]
    public void TimeRange_Duration_And_Contains()
    {
        var r = new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(3));
        Assert.Equal(TimeSpan.FromSeconds(2), r.Duration);
        Assert.True(r.Contains(TimeSpan.FromSeconds(1)));
        Assert.True(r.Contains(TimeSpan.FromSeconds(2.999)));
        Assert.False(r.Contains(TimeSpan.FromSeconds(3)));
    }

    // 7. 乱序输入按 Start 升序排序。
    [Fact]
    public void TranscriptDoc_SortsWordsByStart()
    {
        var words = new[]
        {
            W("c", 1.0, 2.0),
            W("a", 0.0, 0.5),
            W("b", 0.5, 1.0),
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(2));
        Assert.Equal(3, doc.Words.Count);
        Assert.Equal(TimeSpan.Zero, doc.Words[0].Start);
        Assert.Equal(TimeSpan.FromSeconds(0.5), doc.Words[1].Start);
        Assert.Equal(TimeSpan.FromSeconds(1.0), doc.Words[2].Start);
    }

    // 8. duration 为负 → Duration 钳位为 0（词表为空）。
    [Fact]
    public void TranscriptDoc_NegativeDuration_ClampedToZero()
    {
        var doc = new TranscriptDoc(Array.Empty<TranscriptWord>(), TimeSpan.FromSeconds(-5));
        Assert.Equal(TimeSpan.Zero, doc.Duration);
    }

    // 9. 末词 End > duration 时 Duration 拉长至末词 End。
    [Fact]
    public void TranscriptDoc_LastWordEnd_ExtendsDuration()
    {
        var words = new[] { W("x", 1.0, 3.0) };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(2));
        Assert.Equal(TimeSpan.FromSeconds(3), doc.Duration);
    }

    // 10. WordAt 边界与未命中。
    [Fact]
    public void TranscriptDoc_WordAt_Boundaries()
    {
        // 相邻词：t 恰为前词词尾 → 命中下一个词（左闭右开）
        var doc = new TranscriptDoc(new[] { W("a", 0.0, 1.0), W("b", 1.0, 2.0) }, TimeSpan.FromSeconds(3));
        var atEnd = doc.WordAt(TimeSpan.FromSeconds(1.0));
        Assert.NotNull(atEnd);
        Assert.Equal("b", atEnd!.Text);

        // 有间隙：t 落在间隙 → null；t 恰为前词词尾但后词尚未开始 → null
        var gapped = new TranscriptDoc(new[] { W("a", 0.0, 1.0), W("b", 2.0, 3.0) }, TimeSpan.FromSeconds(4));
        Assert.Null(gapped.WordAt(TimeSpan.FromSeconds(1.5)));
        Assert.Null(gapped.WordAt(TimeSpan.FromSeconds(1.0)));

        // t < 首词 Start → null
        Assert.Null(doc.WordAt(TimeSpan.FromSeconds(-0.5)));

        // t >= 末词 End → null
        Assert.Null(doc.WordAt(TimeSpan.FromSeconds(2.0)));

        // 空文档 → null
        Assert.Null(TranscriptDoc.Empty.WordAt(TimeSpan.Zero));
    }

    // 11. WordsIn 空区间或空词表 → 空列表。
    [Fact]
    public void TranscriptDoc_WordsIn_EmptyRangeOrEmptyDoc()
    {
        var words = new[] { W("a", 0.0, 1.0), W("b", 1.0, 2.0) };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(3));

        var empty1 = doc.WordsIn(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1)));
        Assert.Empty(empty1);

        var empty2 = doc.WordsIn(new TimeRange(TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(1)));
        Assert.Empty(empty2);

        var empty3 = TranscriptDoc.Empty.WordsIn(new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)));
        Assert.Empty(empty3);
    }

    // 12. WordsIn 边界不计入：word.End==range.Start 与 word.Start==range.End 均不计入。
    [Fact]
    public void TranscriptDoc_WordsIn_ExclusiveBoundaries()
    {
        var words = new[] { W("a", 0.0, 1.0), W("b", 1.0, 2.0), W("c", 2.0, 3.0) };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(4));

        // range [1.0, 2.0)：a.End==1.0 不计入，c.Start==2.0 不计入；b 真正重叠。
        var res = doc.WordsIn(new TimeRange(TimeSpan.FromSeconds(1.0), TimeSpan.FromSeconds(2.0)));
        Assert.Single(res);
        Assert.Equal("b", res[0].Text);

        // 保持原序：范围 [0.5, 2.5) 覆盖 a、b、c。
        var res2 = doc.WordsIn(new TimeRange(TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(2.5)));
        Assert.Equal(3, res2.Count);
        Assert.Equal("a", res2[0].Text);
        Assert.Equal("b", res2[1].Text);
        Assert.Equal("c", res2[2].Text);
    }

    // 13. PlainText：空文档 → ""；单中文词 → 原样。
    [Fact]
    public void TranscriptDoc_PlainText_EmptyAndSingleCjk()
    {
        Assert.Equal(string.Empty, TranscriptDoc.Empty.PlainText);

        var doc = new TranscriptDoc(new[] { W("你好", 0, 1) }, TimeSpan.FromSeconds(1));
        Assert.Equal("你好", doc.PlainText);
    }

    // 14. PlainText 中英混排加空格。
    [Fact]
    public void TranscriptDoc_PlainText_MixedCjkLatin()
    {
        var doc1 = new TranscriptDoc(new[] { W("你好", 0, 0.5), W("world", 0.5, 1) }, TimeSpan.FromSeconds(1));
        Assert.Equal("你好 world", doc1.PlainText);

        var doc2 = new TranscriptDoc(new[] { W("world", 0, 0.5), W("你好", 0.5, 1) }, TimeSpan.FromSeconds(1));
        Assert.Equal("world 你好", doc2.PlainText);
    }

    // 15. PlainText 标点：句号（U+3002）属于 \u3000-\u303F，与 CJK 相邻不加空格。
    [Fact]
    public void TranscriptDoc_PlainText_PunctuationWithCjk()
    {
        var doc = new TranscriptDoc(new[]
        {
            W("今天", 0.0, 0.3),
            W("。", 0.3, 0.4),
            W("天气好", 0.4, 1.0),
        }, TimeSpan.FromSeconds(1));
        Assert.Equal("今天。天气好", doc.PlainText);
    }

    // 16. Empty 单例：0 词、Duration 为 0。
    [Fact]
    public void TranscriptDoc_Empty_Singleton()
    {
        Assert.Empty(TranscriptDoc.Empty.Words);
        Assert.Equal(TimeSpan.Zero, TranscriptDoc.Empty.Duration);
    }

    // 17. 构造 words 为 null 抛 ArgumentNullException。
    [Fact]
    public void TranscriptDoc_NullWords_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new TranscriptDoc(null!, TimeSpan.Zero));
    }

    // 18. WordsIn 跨多词：5 个每词 1 秒连续词，range [1.5s, 3.5s) → 索引 1、2、3。
    [Fact]
    public void TranscriptDoc_WordsIn_SpanningMultiple()
    {
        var words = Enumerable.Range(0, 5)
            .Select(i => W("w" + i, i, i + 1))
            .ToArray();
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(5));

        var res = doc.WordsIn(new TimeRange(TimeSpan.FromSeconds(1.5), TimeSpan.FromSeconds(3.5)));
        Assert.Equal(3, res.Count);
        Assert.Equal("w1", res[0].Text);
        Assert.Equal("w2", res[1].Text);
        Assert.Equal("w3", res[2].Text);
    }
}
