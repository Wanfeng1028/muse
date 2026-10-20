using System;
using System.Collections.Generic;
using Xunit;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2PauseBoundaryTests
{
    private static TranscriptDoc BuildDoc(params TranscriptWord[] words)
    {
        return new TranscriptDoc(words, TimeSpan.FromSeconds(60));
    }

    [Fact]
    public void Gap_ExactlyThreshold_NotCounted()
    {
        var wordA = new TranscriptWord("甲", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5));
        var wordB = new TranscriptWord("乙", TimeSpan.FromSeconds(2.0), TimeSpan.FromSeconds(2.5));
        var doc = BuildDoc(wordA, wordB);

        var takes = new List<TakeInput> { new TakeInput("take1", doc) };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.Single(ranked);
        Assert.Equal(0, ranked[0].LongPauseCount);
    }

    [Fact]
    public void Gap_JustAboveThreshold_Counted()
    {
        var wordA = new TranscriptWord("甲", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5));
        var wordB = new TranscriptWord("乙", TimeSpan.FromSeconds(2.01), TimeSpan.FromSeconds(2.51));
        var doc = BuildDoc(wordA, wordB);

        var takes = new List<TakeInput> { new TakeInput("take1", doc) };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.Single(ranked);
        Assert.Equal(1, ranked[0].LongPauseCount);
    }
}
