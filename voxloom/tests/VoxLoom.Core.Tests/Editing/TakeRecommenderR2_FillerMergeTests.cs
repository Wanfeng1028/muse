using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2FillerMergeTests
{
    private static TranscriptDoc MakeDoc(params TranscriptWord[] words)
    {
        return new TranscriptDoc(words, TimeSpan.Zero);
    }

    [Fact]
    public void AdjacentFillersMerged_CountAndSeconds()
    {
        var doc = new TranscriptDoc(new[]
        {
            new TranscriptWord("嗯", TimeSpan.FromSeconds(0.0), TimeSpan.FromSeconds(0.5)),
            new TranscriptWord("嗯", TimeSpan.FromSeconds(0.6), TimeSpan.FromSeconds(1.0)),
            new TranscriptWord("内容", TimeSpan.FromSeconds(10.0), TimeSpan.FromSeconds(10.5)),
        }, TimeSpan.FromSeconds(60));

        var input = new TakeInput("take1", doc);
        var ranked = TakeRecommender.Rank(new[] { input });

        Assert.Single(ranked);
        var score = ranked[0];

        Assert.Equal(1, score.FillerCount);
        Assert.Equal(1.0, score.FillerSeconds, 9);
        Assert.Equal(1, score.LongPauseCount);
    }
}
