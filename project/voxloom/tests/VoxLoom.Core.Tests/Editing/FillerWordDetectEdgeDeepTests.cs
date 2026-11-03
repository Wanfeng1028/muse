using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class FillerWordDetectEdgeDeepTests
{
    [Fact]
    public void Detect_SkipsPunctuationOnlyWord()
    {
        // 依据：词文本 "，" 经 StripPunctuation 后（去空白、去标点、去符号）为空串，
        // 循环中 text.Length == 0 触发 continue，hits 保持空 → MergeAdjacent 返回空数组。
        var doc = new TranscriptDoc(
            new[]
            {
                new TranscriptWord("，", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5))
            },
            TimeSpan.FromSeconds(0.5));

        var result = FillerWordDetector.Detect(doc);

        Assert.Empty(result);
    }

    [Fact]
    public void Detect_NullTranscript_ThrowsArgumentNull()
    {
        // 依据：方法首行 ArgumentNullException.ThrowIfNull(transcript)，传 null 必抛。
        Assert.Throws<ArgumentNullException>(() =>
            FillerWordDetector.Detect(null!, FillerWordDetector.DefaultFillers));
    }

    [Fact]
    public void Detect_NullFillers_ThrowsArgumentNull()
    {
        // 依据：ArgumentNullException.ThrowIfNull(fillers)，传 null 必抛。
        var doc = new TranscriptDoc(
            new[]
            {
                new TranscriptWord("嗯", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5))
            },
            TimeSpan.FromSeconds(0.5));

        Assert.Throws<ArgumentNullException>(() =>
            FillerWordDetector.Detect(doc, null!));
    }

    [Fact]
    public void Detect_EmptyFillerList_ReturnsEmpty()
    {
        // 依据：fillers 为空集合 → normalized 为空 HashSet → normalized.Count == 0 → 直接返回 Array.Empty<TimeRange>()。
        var doc = new TranscriptDoc(
            new[]
            {
                new TranscriptWord("嗯", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5))
            },
            TimeSpan.FromSeconds(0.5));

        var result = FillerWordDetector.Detect(doc, new List<string>());

        Assert.Empty(result);
    }

    [Fact]
    public void Detect_WhitespaceOnlyFiller_Ignored()
    {
        // 依据：fillers = { " ", "嗯" }，" " 被 !string.IsNullOrWhiteSpace 过滤掉，
        // 剩余 normalized = { "嗯" }。词 "嗯" 命中一次，hits = [ [0, 0.5s] ]，
        // 单条无需合并，返回 1 个区间 [0, 0.5s]。
        var doc = new TranscriptDoc(
            new[]
            {
                new TranscriptWord("嗯", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5))
            },
            TimeSpan.FromSeconds(0.5));

        var result = FillerWordDetector.Detect(doc, new List<string> { " ", "嗯" });

        var range = Assert.Single(result);
        Assert.Equal(TimeSpan.FromSeconds(0), range.Start);
        Assert.Equal(TimeSpan.FromSeconds(0.5), range.End);
    }

    [Fact]
    public void Detect_OverlappingCustomFillers_SingleHitPerWord()
    {
        // 依据：fillers = { "嗯", "嗯啊" }，词文本 "嗯啊" 经 StripPunctuation 后为 "嗯啊"，
        // normalized 中恰好含 "嗯啊"，Contains 命中一次；循环每词最多 Add 一次，
        // 故 hits 只有一条 → 返回 1 个区间 [0, 0.5s]。
        var doc = new TranscriptDoc(
            new[]
            {
                new TranscriptWord("嗯啊", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5))
            },
            TimeSpan.FromSeconds(0.5));

        var result = FillerWordDetector.Detect(doc, new List<string> { "嗯", "嗯啊" });

        Assert.Single(result);
    }

    [Fact]
    public void Detect_Then_MidSentence_Skipped()
    {
        // 依据：i=1 词 "然后" 命中 normalized，但 text == "然后" 需 IsSentenceStart 为真；
        // 前词 "好" 末字符 '好' 不是 IsSentenceEndPunct 中的任一字符 → 返回 false → continue，
        // hits 为空 → 返回空数组。
        var doc = new TranscriptDoc(
            new[]
            {
                new TranscriptWord("好", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5)),
                new TranscriptWord("然后", TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(1.0))
            },
            TimeSpan.FromSeconds(1.0));

        var result = FillerWordDetector.Detect(doc);

        Assert.Empty(result);
    }

    [Fact]
    public void Detect_Then_AfterPeriod_Hits()
    {
        // 依据：i=1 词 "然后" 命中 normalized，前词 "好。" 末字符 '。' 属于 IsSentenceEndPunct
        // → IsSentenceStart 为真 → Add([0.5s, 1.0s])。单条 → 返回 1 个区间 [0.5s, 1.0s]。
        var doc = new TranscriptDoc(
            new[]
            {
                new TranscriptWord("好。", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5)),
                new TranscriptWord("然后", TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(1.0))
            },
            TimeSpan.FromSeconds(1.0));

        var result = FillerWordDetector.Detect(doc);

        var range = Assert.Single(result);
        Assert.Equal(TimeSpan.FromSeconds(0.5), range.Start);
        Assert.Equal(TimeSpan.FromSeconds(1.0), range.End);
    }

    [Fact]
    public void Detect_MergeGapBoundary_NotMerged()
    {
        // 依据：hits = [ [0, 0.5s], [0.8s, 1.0s] ]，ordered 按 Start 排序后不变。
        // gap = (0.8s - 0.5s).TotalSeconds = 0.3；合并条件为 gap < 0.300，
        // 0.3 < 0.300 为 false → 不合并 → merged 含两条 → 返回 2 个区间。
        var doc = new TranscriptDoc(
            new[]
            {
                new TranscriptWord("嗯", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5)),
                new TranscriptWord("啊", TimeSpan.FromSeconds(0.8), TimeSpan.FromSeconds(1.0))
            },
            TimeSpan.FromSeconds(1.0));

        var result = FillerWordDetector.Detect(doc);

        Assert.Equal(2, result.Count);
        Assert.Equal(TimeSpan.FromSeconds(0), result[0].Start);
        Assert.Equal(TimeSpan.FromSeconds(0.5), result[0].End);
        Assert.Equal(TimeSpan.FromSeconds(0.8), result[1].Start);
        Assert.Equal(TimeSpan.FromSeconds(1.0), result[1].End);
    }
}
