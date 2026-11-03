using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2SingleTakeTests
{
    private static TranscriptDoc BuildTranscript60s()
    {
        var words = new List<TranscriptWord>
        {
            new TranscriptWord("内容", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5))
        };
        return new TranscriptDoc(words, TimeSpan.FromSeconds(60));
    }

    [Fact]
    public void Rank_SingleTake_ReturnsIt()
    {
        var takes = new List<TakeInput>
        {
            new TakeInput("solo", BuildTranscript60s())
        };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.NotNull(ranked);
        Assert.Single(ranked);
        Assert.Equal("solo", ranked[0].Name);
        Assert.True(ranked[0].Score >= 0.0, "Score 应非负");
    }

    [Fact]
    public void RecommendBest_SingleTake_ReturnsIt()
    {
        var takes = new List<TakeInput>
        {
            new TakeInput("solo", BuildTranscript60s())
        };

        TakeScore best = TakeRecommender.RecommendBest(takes);

        Assert.NotNull(best);
        Assert.Equal("solo", best.Name);
    }
}
