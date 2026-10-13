using System;
using System.Collections.Generic;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Transcript;

public class TranscriptDocWordTests
{
    private static TranscriptDoc BuildSample()
    {
        var words = new List<TranscriptWord>
        {
            new("你", TimeSpan.FromSeconds(0.0), TimeSpan.FromSeconds(0.5)),
            new("好", TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(1.0)),
            new("world", TimeSpan.FromSeconds(1.0), TimeSpan.FromSeconds(1.6)),
        };
        return new TranscriptDoc(words, TimeSpan.FromSeconds(1.6));
    }

    [Fact]
    public void WordAt_BinarySearch_ReturnsMatchingWord()
    {
        var t = BuildSample();

        Assert.Equal("你", t.WordAt(TimeSpan.FromSeconds(0.25))?.Text);
        Assert.Equal("好", t.WordAt(TimeSpan.FromSeconds(0.5))?.Text);
        Assert.Equal("world", t.WordAt(TimeSpan.FromSeconds(1.59))?.Text);
        Assert.Null(t.WordAt(TimeSpan.FromSeconds(1.6)));
        Assert.Null(t.WordAt(TimeSpan.FromSeconds(-0.1)));
    }

    [Fact]
    public void WordsIn_ReturnsIntersectingWords()
    {
        var t = BuildSample();

        var r1 = t.WordsIn(new TimeRange(TimeSpan.FromSeconds(0.4), TimeSpan.FromSeconds(1.2)));
        Assert.Equal(3, r1.Count);
        Assert.Equal("你", r1[0].Text);
        Assert.Equal("好", r1[1].Text);
        Assert.Equal("world", r1[2].Text);

        var r2 = t.WordsIn(new TimeRange(TimeSpan.FromSeconds(0.6), TimeSpan.FromSeconds(0.9)));
        Assert.Single(r2);
        Assert.Equal("好", r2[0].Text);

        var r3 = t.WordsIn(new TimeRange(TimeSpan.FromSeconds(2.0), TimeSpan.FromSeconds(3.0)));
        Assert.Empty(r3);
    }

    [Fact]
    public void PlainText_ChineseNoSpace_EnglishWithSpace()
    {
        var words = new List<TranscriptWord>
        {
            new("你", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.2)),
            new("好", TimeSpan.FromSeconds(0.2), TimeSpan.FromSeconds(0.4)),
            new("hello", TimeSpan.FromSeconds(0.4), TimeSpan.FromSeconds(0.8)),
            new("world", TimeSpan.FromSeconds(0.8), TimeSpan.FromSeconds(1.2)),
        };
        var t = new TranscriptDoc(words, TimeSpan.FromSeconds(1.2));

        Assert.Equal("你好 hello world", t.PlainText);
    }

    [Fact]
    public void Constructor_RejectsStartAfterEnd()
    {
        Assert.Throws<ArgumentException>(() =>
            new TranscriptWord("x", TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(0.5)));
    }
}
