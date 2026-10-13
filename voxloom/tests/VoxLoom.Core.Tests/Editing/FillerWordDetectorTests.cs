using System;
using System.Collections.Generic;
using System.Linq;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class FillerWordDetectorTests
{
    private static TranscriptWord W(string text, double start, double end, double conf = 0.9)
        => new TranscriptWord(text, TimeSpan.FromSeconds(start), TimeSpan.FromSeconds(end), (float)conf);

    [Fact]
    public void Detect_FindsSingleFiller()
    {
        var words = new List<TranscriptWord>
        {
            W("嗯", 0.0, 0.3),
            W("你好", 0.4, 0.8),
            W("世界", 0.9, 1.2)
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(1.5));

        var ranges = FillerWordDetector.Detect(doc);

        Assert.Single(ranges);
        Assert.Equal(0.0, ranges[0].Start.TotalSeconds, 3);
        Assert.Equal(0.3, ranges[0].End.TotalSeconds, 3);
    }

    [Fact]
    public void Detect_MergesAdjacentHits()
    {
        // 「嗯」「那个」间隔 200ms < 300ms 应合并
        var words = new List<TranscriptWord>
        {
            W("嗯", 0.0, 0.3),
            W("那个", 0.5, 0.8),
            W("你好", 1.0, 1.5)
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(2.0));

        var ranges = FillerWordDetector.Detect(doc);

        Assert.Single(ranges);
        Assert.Equal(0.0, ranges[0].Start.TotalSeconds, 3);
        Assert.Equal(0.8, ranges[0].End.TotalSeconds, 3);
    }

    [Fact]
    public void Detect_DoesNotMergeFarHits()
    {
        // 间隔 1s > 300ms，不合并
        var words = new List<TranscriptWord>
        {
            W("嗯", 0.0, 0.3),
            W("你好", 0.5, 1.0),
            W("那个", 1.5, 1.8)
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(2.0));

        var ranges = FillerWordDetector.Detect(doc);

        Assert.Equal(2, ranges.Count);
    }

    [Fact]
    public void Detect_ThenOnlyAtSentenceStart()
    {
        var words = new List<TranscriptWord>
        {
            W("你好。", 0.0, 0.5),
            W("然后", 0.6, 0.9),   // 句首 → 命中
            W("我们", 1.0, 1.3),
            W("然后", 1.4, 1.7)    // 非句首 → 不命中
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(2.0));

        var ranges = FillerWordDetector.Detect(doc);

        Assert.Single(ranges);
        Assert.Equal(0.6, ranges[0].Start.TotalSeconds, 3);
    }

    [Fact]
    public void Detect_IgnoresPunctuation()
    {
        // 带标点的语气词仍应命中
        var words = new List<TranscriptWord>
        {
            W("嗯，", 0.0, 0.3),
            W("你好", 0.5, 1.0)
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(1.5));

        var ranges = FillerWordDetector.Detect(doc);

        Assert.Single(ranges);
    }

    [Fact]
    public void Detect_CustomFillers()
    {
        var words = new List<TranscriptWord>
        {
            W("呃", 0.0, 0.3),
            W("你好", 0.5, 1.0)
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(1.5));

        var ranges = FillerWordDetector.Detect(doc, new[] { "呃" });

        Assert.Single(ranges);
        Assert.Equal(0.0, ranges[0].Start.TotalSeconds, 3);
    }

    [Fact]
    public void ToAttenuateOps_ProducesOps()
    {
        var ranges = new List<TimeRange>
        {
            new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)),
            new TimeRange(TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(4))
        };

        var ops = FillerWordDetector.ToAttenuateOps(ranges, -12f);

        Assert.Equal(2, ops.Length);
        Assert.All(ops, op => Assert.IsType<AttenuateOp>(op));
        Assert.All(ops, op => Assert.Equal(-12f, ((AttenuateOp)op).Db));
    }
}
