using System;
using System.Collections.Generic;
using System.Linq;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2FillerDurationTests
{
    private static TranscriptDoc MakeDoc(TimeSpan duration, params TranscriptWord[] words)
    {
        return new TranscriptDoc(words, duration);
    }

    [Fact]
    public void SameCountLongerFillerDuration_Worse()
    {
        var wordsA = new[]
        {
            new TranscriptWord("嗯", TimeSpan.Zero, TimeSpan.FromSeconds(1.0))
        };
        var docA = MakeDoc(TimeSpan.FromSeconds(60), wordsA);

        var wordsB = new[]
        {
            new TranscriptWord("嗯", TimeSpan.Zero, TimeSpan.FromSeconds(0.2))
        };
        var docB = MakeDoc(TimeSpan.FromSeconds(60), wordsB);

        var takes = new List<TakeInput>
        {
            new TakeInput("A", docA),
            new TakeInput("B", docB)
        };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.Equal("B", ranked[0].Name);
        Assert.Equal("A", ranked[1].Name);

        Assert.Equal(1, ranked[0].FillerCount);
        Assert.Equal(1, ranked[1].FillerCount);
        Assert.Equal(0, ranked[0].LongPauseCount);
        Assert.Equal(0, ranked[1].LongPauseCount);

        double expectedScoreA = 1.8333333333333333;
        double expectedScoreB = 1.1666666666666667;

        TakeScore scoreA = ranked.Single(s => s.Name == "A");
        TakeScore scoreB = ranked.Single(s => s.Name == "B");

        Assert.Equal(expectedScoreA, scoreA.Score, 9);
        Assert.Equal(expectedScoreB, scoreB.Score, 9);

        Assert.Equal(1.0, scoreA.FillerSeconds, 9);
        Assert.Equal(0.2, scoreB.FillerSeconds, 9);
    }
}
