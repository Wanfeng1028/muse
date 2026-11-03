using System;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Transcript;

public class TranscriptDocImporterTests
{
    [Fact]
    public void ParseWhisperJson_WithWordLevel()
    {
        const string json = """
        {
          "segments": [
            {
              "start": 0.0, "end": 1.0, "text": "hello world",
              "words": [
                { "word": "hello", "start": 0.0, "end": 0.5, "probability": 0.9 },
                { "word": "world", "start": 0.5, "end": 1.0, "probability": 0.8 }
              ]
            }
          ]
        }
        """;

        var t = TranscriptImporter.ParseWhisperJson(json);
        Assert.Equal(2, t.Words.Count);
        Assert.Equal("hello", t.Words[0].Text);
        Assert.Equal(0.9f, t.Words[0].Confidence, 3);
        Assert.Equal("world", t.Words[1].Text);
        Assert.True(t.Duration >= TimeSpan.FromSeconds(1.0));
    }

    [Fact]
    public void ParseWhisperJson_FallbackToSegment()
    {
        const string json = """
        {
          "segments": [
            { "start": 0.0, "end": 1.0, "text": "你好世界" }
          ]
        }
        """;

        var t = TranscriptImporter.ParseWhisperJson(json);
        Assert.Equal(4, t.Words.Count);
        Assert.Equal("你", t.Words[0].Text);
        Assert.Equal("好", t.Words[1].Text);
        Assert.Equal("世", t.Words[2].Text);
        Assert.Equal("界", t.Words[3].Text);
    }

    [Fact]
    public void ParseLrc_Simple()
    {
        const string lrc = """
        [00:00.00] hello world
        [00:01.00] 你好世界
        """;

        var t = TranscriptImporter.ParseLrc(lrc);
        Assert.NotEmpty(t.Words);
        Assert.Equal("hello", t.Words[0].Text);
        Assert.Equal(TimeSpan.Zero, t.Words[0].Start);
    }

    [Fact]
    public void ParsePlainText_EvenSplit()
    {
        var t = TranscriptImporter.ParsePlainText("hello world 你好", TimeSpan.FromSeconds(4));
        Assert.NotEmpty(t.Words);
        Assert.Equal(TimeSpan.Zero, t.Words[0].Start);
        Assert.Equal(TimeSpan.FromSeconds(4), t.Words[^1].End);
    }

    [Fact]
    public void ParseWhisperJson_InvalidJson_Throws()
    {
        Assert.Throws<TranscriptFormatException>(() =>
            TranscriptImporter.ParseWhisperJson("{ not valid json"));
    }

    [Fact]
    public void ParseWhisperJson_MissingSegments_Throws()
    {
        Assert.Throws<TranscriptFormatException>(() =>
            TranscriptImporter.ParseWhisperJson("{\"foo\":1}"));
    }

    [Fact]
    public void ParseLrc_NoTags_Throws()
    {
        Assert.Throws<TranscriptFormatException>(() =>
            TranscriptImporter.ParseLrc("just some text without tags"));
    }

    [Fact]
    public void ParsePlainText_Empty_Throws()
    {
        Assert.Throws<TranscriptFormatException>(() =>
            TranscriptImporter.ParsePlainText("   ", TimeSpan.FromSeconds(1)));
    }
}
