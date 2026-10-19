using System;
using System.Collections.Generic;
using System.Linq;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderDeepTests
{
    private static TranscriptWord Word(string text, double startSec, double durSec)
        => new TranscriptWord(text, TimeSpan.FromSeconds(startSec), TimeSpan.FromSeconds(startSec + durSec));

    private static TranscriptDoc Doc(double durationSec, params TranscriptWord[] words)
        => new TranscriptDoc(words, TimeSpan.FromSeconds(durationSec));

    [Fact]
    public void Rank_NullTakes_ThrowsArgumentNull()
    {
        Assert.Throws<ArgumentNullException>(() => TakeRecommender.Rank(null!));
    }

    [Fact]
    public void Rank_EmptyTakes_ThrowsArgument()
    {
        Assert.Throws<ArgumentException>(() => TakeRecommender.Rank(new List<TakeInput>()));
    }

    [Fact]
    public void Rank_BlankName_ThrowsArgument()
    {
        var doc = Doc(10.0, Word("嗯", 0.0, 0.5));
        var takes = new List<TakeInput> { new TakeInput("  ", doc) };
        Assert.Throws<ArgumentException>(() => TakeRecommender.Rank(takes));
    }

    [Fact]
    public void Rank_NullTranscript_ThrowsArgumentNull()
    {
        var takes = new List<TakeInput> { new TakeInput("t", null!) };
        Assert.Throws<ArgumentNullException>(() => TakeRecommender.Rank(takes));
    }

    [Fact]
    public void RecommendBest_EmptyTakes_ThrowsArgument()
    {
        Assert.Throws<ArgumentException>(() => TakeRecommender.RecommendBest(new List<TakeInput>()));
    }

    [Fact]
    public void Rank_FewerFillers_RankedFirst()
    {
        var wordsA = new List<TranscriptWord>
        {
            Word("嗯", 0.0, 0.5),
            Word("嗯", 10.0, 0.5),
            Word("嗯", 20.0, 0.5),
            Word("嗯", 30.0, 0.5),
            Word("内容", 40.0, 0.5),
            Word("内容", 50.0, 0.5)
        };
        var wordsB = new List<TranscriptWord>
        {
            Word("嗯", 0.0, 0.5),
            Word("内容", 10.0, 0.5),
            Word("内容", 20.0, 0.5),
            Word("内容", 30.0, 0.5),
            Word("内容", 40.0, 0.5),
            Word("内容", 50.0, 0.5)
        };
        var takes = new List<TakeInput>
        {
            new TakeInput("takeA", new TranscriptDoc(wordsA, TimeSpan.FromSeconds(60))),
            new TakeInput("takeB", new TranscriptDoc(wordsB, TimeSpan.FromSeconds(60)))
        };

        var ranked = TakeRecommender.Rank(takes);

        Assert.Equal("takeB", ranked[0].Name);
        Assert.True(ranked[0].Score < ranked[1].Score);
    }

    [Fact]
    public void Rank_LongPause_Penalized()
    {
        var wordsA = new List<TranscriptWord>
        {
            Word("内容", 0.0, 0.5),
            Word("内容", 2.5, 0.5)
        };
        var wordsB = new List<TranscriptWord>
        {
            Word("内容", 0.0, 0.5),
            Word("内容", 0.5, 0.5)
        };
        var takes = new List<TakeInput>
        {
            new TakeInput("takeA", new TranscriptDoc(wordsA, TimeSpan.FromSeconds(60))),
            new TakeInput("takeB", new TranscriptDoc(wordsB, TimeSpan.FromSeconds(60)))
        };

        var ranked = TakeRecommender.Rank(takes);

        Assert.Equal("takeB", ranked[0].Name);
    }

    [Fact]
    public void Rank_Tie_BrokenByName()
    {
        var words = new List<TranscriptWord>
        {
            Word("内容", 0.0, 0.5),
            Word("内容", 1.0, 0.5)
        };
        var takes = new List<TakeInput>
        {
            new TakeInput("b", new TranscriptDoc(words, TimeSpan.FromSeconds(60))),
            new TakeInput("a", new TranscriptDoc(words, TimeSpan.FromSeconds(60)))
        };

        var ranked = TakeRecommender.Rank(takes);

        Assert.Equal("a", ranked[0].Name);
        Assert.Equal("b", ranked[1].Name);
    }

    [Fact]
    public void Rank_DoesNotMutateInput()
    {
        var badWords = new List<TranscriptWord>
        {
            Word("嗯", 0.0, 0.5),
            Word("嗯", 10.0, 0.5),
            Word("嗯", 20.0, 0.5),
            Word("嗯", 30.0, 0.5),
            Word("内容", 40.0, 0.5)
        };
        var goodWords = new List<TranscriptWord>
        {
            Word("内容", 0.0, 0.5),
            Word("内容", 10.0, 0.5)
        };
        var bad = new TakeInput("bad", new TranscriptDoc(badWords, TimeSpan.FromSeconds(60)));
        var good = new TakeInput("good", new TranscriptDoc(goodWords, TimeSpan.FromSeconds(60)));
        var takes = new List<TakeInput> { bad, good };

        var ranked = TakeRecommender.Rank(takes);

        Assert.Equal(2, takes.Count);
        Assert.Same(bad, takes[0]);
        Assert.Same(good, takes[1]);
        Assert.NotSame(takes, ranked);
        Assert.Equal("good", ranked[0].Name);
    }

    [Fact]
    public void RecommendBest_ReturnsLowestScore()
    {
        var wordsA = new List<TranscriptWord>
        {
            Word("嗯", 0.0, 0.5),
            Word("嗯", 10.0, 0.5),
            Word("嗯", 20.0, 0.5),
            Word("内容", 30.0, 0.5)
        };
        var wordsB = new List<TranscriptWord>
        {
            Word("内容", 0.0, 0.5),
            Word("内容", 10.0, 0.5)
        };
        var wordsC = new List<TranscriptWord>
        {
            Word("嗯", 0.0, 0.5),
            Word("内容", 10.0, 0.5)
        };
        var takes = new List<TakeInput>
        {
            new TakeInput("a", new TranscriptDoc(wordsA, TimeSpan.FromSeconds(60))),
            new TakeInput("b", new TranscriptDoc(wordsB, TimeSpan.FromSeconds(60))),
            new TakeInput("c", new TranscriptDoc(wordsC, TimeSpan.FromSeconds(60)))
        };

        var best = TakeRecommender.RecommendBest(takes);
        var ranked = TakeRecommender.Rank(takes);

        Assert.Equal(ranked[0].Name, best.Name);
    }

    [Fact]
    public void ZeroDuration_NoDivideByZero()
    {
        var doc = new TranscriptDoc(new List<TranscriptWord>(), TimeSpan.FromSeconds(0));
        var takes = new List<TakeInput> { new TakeInput("t", doc) };

        var ranked = TakeRecommender.Rank(takes);

        Assert.Single(ranked);
        Assert.True(double.IsFinite(ranked[0].Score));
    }

    [Fact]
    public void Score_Fields_Correct()
    {
        var words = new List<TranscriptWord>
        {
            Word("嗯", 0.0, 0.5),
            Word("啊", 1.0, 0.5),
            Word("内容", 2.0, 0.5),
            Word("内容", 3.0, 0.5),
            Word("内容", 4.0, 0.5),
            Word("内容", 5.0, 0.5)
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(60));
        var takes = new List<TakeInput> { new TakeInput("t", doc) };

        var ranked = TakeRecommender.Rank(takes);
        var score = ranked[0];

        Assert.Equal(2, score.FillerCount);
        Assert.Equal(1.0, score.FillerSeconds, 9);
        Assert.Equal(6.0, score.WordsPerMinute, 9);
    }

    [Fact]
    public void LongPause_Counting()
    {
        var words = new List<TranscriptWord>
        {
            Word("a", 0.0, 0.5),
            Word("b", 2.0, 0.5),
            Word("c", 4.0001, 0.5)
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(60));
        var takes = new List<TakeInput> { new TakeInput("t", doc) };

        var ranked = TakeRecommender.Rank(takes);

        Assert.Equal(1, ranked[0].LongPauseCount);
    }

    [Fact]
    public void Explain_ContainsKeyInfo()
    {
        var words = new List<TranscriptWord>
        {
            Word("嗯", 0.0, 0.5),
            Word("内容", 10.0, 0.5)
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(60));
        var takes = new List<TakeInput> { new TakeInput("我的take", doc) };

        var ranked = TakeRecommender.Rank(takes);
        var text = TakeRecommender.Explain(ranked[0]);

        Assert.Contains("我的take", text);
        Assert.Contains("语气词", text);
        Assert.DoesNotContain('\uD83D', text);
    }
}
