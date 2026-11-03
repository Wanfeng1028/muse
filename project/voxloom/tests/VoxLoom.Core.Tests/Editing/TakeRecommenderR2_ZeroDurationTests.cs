using System;
using System.Collections.Generic;
using Xunit;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2ZeroDurationTests
{
    [Fact]
    public void ZeroDurationMinutesFloor_NoDivideByZero()
    {
        var words = new List<TranscriptWord>
        {
            new TranscriptWord("嗯", TimeSpan.Zero, TimeSpan.FromSeconds(0.5))
        };

        var doc = new TranscriptDoc(words, TimeSpan.Zero);

        Assert.Equal(TimeSpan.FromSeconds(0.5), doc.Duration);

        var takes = new List<TakeInput>
        {
            new TakeInput("take1", doc)
        };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.Single(ranked);

        TakeScore score = ranked[0];

        Assert.Equal("take1", score.Name);
        Assert.Equal(110.0, score.Score, 6);
        Assert.Equal(1, score.FillerCount);
        Assert.Equal(0.5, score.FillerSeconds, 6);
        Assert.Equal(0, score.LongPauseCount);
        Assert.Equal(60.0, score.WordsPerMinute, 6);
    }
}
