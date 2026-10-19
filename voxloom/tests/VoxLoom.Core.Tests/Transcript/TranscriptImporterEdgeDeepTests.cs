using System;
using Xunit;

using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Transcript;

public class TranscriptImporterEdgeDeepTests
{
    // 事实来源：ParseWhisperJsonCore 中 foreach (var seg in segments.EnumerateArray()) 对空数组直接跳过，返回空 doc。
    [Fact]
    public void ParseWhisperJson_EmptySegmentsArray_ReturnsEmptyDoc()
    {
        var doc = TranscriptImporter.ParseWhisperJson("{\"segments\": []}");
        Assert.Empty(doc.Words);
    }

    // 事实来源：ParseWhisperJsonCore 中 if (weTs < wsTs) weTs = wsTs; 将词 end 钳制为 start。
    [Fact]
    public void ParseWhisperJson_WordEndBeforeStart_ClampedToStart()
    {
        var json = "{\"segments\":[{\"start\":0,\"end\":3,\"text\":\"hi\",\"words\":[{\"word\":\"hi\",\"start\":2.0,\"end\":1.0}]}]}";
        var doc = TranscriptImporter.ParseWhisperJson(json);
        var word = Assert.Single(doc.Words);
        Assert.Equal(TimeSpan.FromSeconds(2), word.Start);
        Assert.Equal(TimeSpan.FromSeconds(2), word.End);
    }

    // 事实来源：ReadDouble 的 JsonValueKind.String 分支使用 double.TryParse 解析字符串数字。
    [Fact]
    public void ParseWhisperJson_NumericStringStart_Parsed()
    {
        var json = "{\"segments\":[{\"start\":\"1.5\",\"end\":\"2.5\",\"text\":\"hi\",\"words\":[{\"word\":\"hi\",\"start\":\"1.5\",\"end\":\"2.5\"}]}]}";
        var doc = TranscriptImporter.ParseWhisperJson(json);
        var word = Assert.Single(doc.Words);
        Assert.Equal(TimeSpan.FromSeconds(1.5), word.Start);
    }

    // 事实来源：ParseWhisperJsonCore 中 if (segEndTs < segStartTs) segEndTs = segStartTs; 段 end 钳制后按字均分，首词 Start == 5 秒。
    [Fact]
    public void ParseWhisperJson_SegmentEndBeforeStart_ClampedToStart()
    {
        var json = "{\"segments\":[{\"start\":5.0,\"end\":3.0,\"text\":\"你好\"}]}";
        var doc = TranscriptImporter.ParseWhisperJson(json);
        Assert.Equal(2, doc.Words.Count);
        Assert.Equal(TimeSpan.FromSeconds(5), doc.Words[0].Start);
    }

    // 事实来源：SplitByCharWeight 中 IsCjk(c) 时逐字成词，"你好" 拆为 "你" "好"。
    [Fact]
    public void ParseWhisperJson_NoWordsArray_CjkSplitPerChar()
    {
        var json = "{\"segments\":[{\"start\":0,\"end\":2.0,\"text\":\"你好\"}]}";
        var doc = TranscriptImporter.ParseWhisperJson(json);
        Assert.Equal(2, doc.Words.Count);
        Assert.Equal("你", doc.Words[0].Text);
        Assert.Equal("好", doc.Words[1].Text);
    }

    // 事实来源：ParseWhisperJsonCore 中 if (seg.ValueKind != JsonValueKind.Object) continue; 跳过非对象元素。
    [Fact]
    public void ParseWhisperJson_NonObjectSegmentElement_Skipped()
    {
        var json = "{\"segments\":[123]}";
        var doc = TranscriptImporter.ParseWhisperJson(json);
        Assert.Empty(doc.Words);
    }

    // 事实来源：ParseWhisperJsonCore 中 if (root.ValueKind != JsonValueKind.Object) throw TranscriptFormatException。
    [Fact]
    public void ParseWhisperJson_TopLevelArray_Throws()
    {
        Assert.Throws<TranscriptFormatException>(() => TranscriptImporter.ParseWhisperJson("[1,2]"));
    }

    // 事实来源：ParseWhisperJsonCore 中 if (string.IsNullOrWhiteSpace(json)) throw TranscriptFormatException("Whisper JSON 内容为空。")。
    [Fact]
    public void ParseWhisperJson_Whitespace_ThrowsTranscriptFormatException()
    {
        var ex = Assert.Throws<TranscriptFormatException>(() => TranscriptImporter.ParseWhisperJson("   "));
        Assert.Contains("为空", ex.Message);
    }

    // 事实来源：ParseLrcCore 中 foreach (Match m in matches) 每个 tag 都生成一个条目；
    // 每个条目文本 "你好" 经 SplitByCharWeight 拆成 2 个 CJK 词，故共 4 个词。
    [Fact]
    public void ParseLrc_MultipleTagsOnOneLine_YieldsTwoEntries()
    {
        var doc = TranscriptImporter.ParseLrc("[00:01.00][00:02.00]你好");
        Assert.Equal(4, doc.Words.Count);
        Assert.Equal(TimeSpan.FromSeconds(1), doc.Words[0].Start);
        Assert.Equal(TimeSpan.FromSeconds(2), doc.Words[2].Start);
    }

    // 事实来源：ParseLrcCore 中 if (cs.Length == 1) centis = int.Parse(cs) * 10; 1 位厘秒 *10。
    [Fact]
    public void ParseLrc_SingleDigitCentiseconds_StartIs1Point5Seconds()
    {
        var doc = TranscriptImporter.ParseLrc("[00:01.5]hi");
        Assert.Equal(TimeSpan.FromSeconds(1.5), doc.Words[0].Start);
    }

    // 事实来源：ParseLrcCore 中 else centis = int.Parse(cs[..2]); 3 位厘秒取前两位。
    [Fact]
    public void ParseLrc_ThreeDigitCentiseconds_TakesFirstTwo()
    {
        var doc = TranscriptImporter.ParseLrc("[00:01.234]hi");
        Assert.Equal(TimeSpan.FromSeconds(1.23), doc.Words[0].Start);
    }

    // 事实来源：ParseLrcCore 中 lrc.Replace("\r\n", "\n") 将 CRLF 统一后按 '\n' 分割。
    [Fact]
    public void ParseLrc_CrlfLineEndings_ParsesTwoLines()
    {
        var doc = TranscriptImporter.ParseLrc("[00:01.00]a\r\n[00:02.00]b");
        Assert.Equal(2, doc.Words.Count);
    }

    // 事实来源：ParseLrcCore 中 entries.Sort(static (a, b) => a.Start.CompareTo(b.Start)); 乱序行按时间排序。
    [Fact]
    public void ParseLrc_OutOfOrderLines_SortedByStart()
    {
        var doc = TranscriptImporter.ParseLrc("[00:05.00]b\n[00:01.00]a");
        Assert.Equal("a", doc.Words[0].Text);
    }

    // 事实来源：ParsePlainTextCore 中 if (text is null) throw new TranscriptFormatException("纯文本内容为 null。")。
    [Fact]
    public void ParsePlainText_Null_ThrowsTranscriptFormatException()
    {
        Assert.Throws<TranscriptFormatException>(() => TranscriptImporter.ParsePlainText(null!, TimeSpan.FromSeconds(1)));
    }

    // 事实来源：ParsePlainTextCore 中 if (totalDuration < TimeSpan.Zero) throw new TranscriptFormatException("总时长不能为负。")。
    [Fact]
    public void ParsePlainText_NegativeDuration_ThrowsTranscriptFormatException()
    {
        Assert.Throws<TranscriptFormatException>(() => TranscriptImporter.ParsePlainText("hi", TimeSpan.FromSeconds(-1)));
    }

    // 事实来源：ParsePlainTextCore 中 TimeSpan end = i == pieces.Count - 1 ? totalDuration : ...; 最后一片精确结束于 totalDuration。
    [Fact]
    public void ParsePlainText_LastPieceEndsExactlyAtTotalDuration()
    {
        var doc = TranscriptImporter.ParsePlainText("abcd", TimeSpan.FromSeconds(4));
        Assert.Equal(TimeSpan.FromSeconds(4), doc.Words[^1].End);
    }

    // 事实来源：SplitByCharWeight 中 IsPunctuation(c) 时标点附着到前一个词，"hello," 为第一词。
    [Fact]
    public void ParsePlainText_PunctuationAttachesToPreviousWord()
    {
        var doc = TranscriptImporter.ParsePlainText("hello, world", TimeSpan.FromSeconds(4));
        Assert.Equal(2, doc.Words.Count);
        Assert.Equal("hello,", doc.Words[0].Text);
    }
}