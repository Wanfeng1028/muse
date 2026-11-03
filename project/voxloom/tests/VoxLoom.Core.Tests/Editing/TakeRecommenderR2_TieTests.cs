using System;
using System.Collections.Generic;
using Xunit;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2TieTests
{
    private static TranscriptDoc MakeDoc()
    {
        var words = new[]
        {
            new TranscriptWord("内容", TimeSpan.Zero, TimeSpan.FromSeconds(0.5))
        };
        return new TranscriptDoc(words, TimeSpan.FromSeconds(60));
    }

    [Fact]
    public void Tie_ThreeTakes_OrderedByNameOrdinal()
    {
        var takes = new List<TakeInput>
        {
            new TakeInput("take-c", MakeDoc()),
            new TakeInput("take-a", MakeDoc()),
            new TakeInput("take-b", MakeDoc())
        };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.Equal(3, ranked.Count);
        Assert.Equal("take-a", ranked[0].Name);
        Assert.Equal("take-b", ranked[1].Name);
        Assert.Equal("take-c", ranked[2].Name);

        Assert.Equal(ranked[0].Score, ranked[1].Score, 10);
        Assert.Equal(ranked[1].Score, ranked[2].Score, 10);

        TakeScore best = TakeRecommender.RecommendBest(takes);
        Assert.Equal("take-a", best.Name);
    }

    [Fact]
    public void Tie_CaseSensitiveOrdinal()
    {
        var takes = new List<TakeInput>
        {
            new TakeInput("a", MakeDoc()),
            new TakeInput("B", MakeDoc())
        };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.Equal(2, ranked.Count);
        Assert.Equal("B", ranked[0].Name);
        Assert.Equal("a", ranked[1].Name);
    }
}
