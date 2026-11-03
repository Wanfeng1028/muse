using System;
using System.Collections.Generic;
using Xunit;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2RecommendBestTests
{
    private static TranscriptWord W(string text, double startSec, double endSec)
        => new TranscriptWord(text, TimeSpan.FromSeconds(startSec), TimeSpan.FromSeconds(endSec));

    [Fact]
    public void RecommendBest_EqualsRankFirst()
    {
        var dirty = new TranscriptDoc(new[]
        {
            W("嗯", 0.0, 0.4),
            W("我", 0.4, 0.8),
            W("觉得", 0.8, 1.2),
            W("那个", 3.5, 4.0),
            W("这个", 4.0, 4.5),
            W("方案", 4.5, 5.0),
            W("不错", 5.0, 5.6)
        }, TimeSpan.FromSeconds(5.6));

        var clean = new TranscriptDoc(new[]
        {
            W("我", 0.0, 0.4),
            W("觉得", 0.4, 0.8),
            W("方案", 0.8, 1.2),
            W("不错", 1.2, 1.7)
        }, TimeSpan.FromSeconds(1.7));

        var takes = new List<TakeInput>
        {
            new TakeInput("dirty", dirty),
            new TakeInput("clean", clean)
        };

        TakeScore best = TakeRecommender.RecommendBest(takes);
        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.Equal(ranked[0].Name, best.Name);
        Assert.Equal(ranked[0].Score, best.Score, 12);
        Assert.Equal("clean", best.Name);
    }
}
