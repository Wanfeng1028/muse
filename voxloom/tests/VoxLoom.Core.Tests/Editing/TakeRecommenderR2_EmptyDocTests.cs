using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2EmptyDocTests
{
    [Fact]
    public void EmptyWords_ZeroScore_ExactExplain()
    {
        var doc = new TranscriptDoc(Array.Empty<TranscriptWord>(), TimeSpan.FromSeconds(30));
        var takes = new List<TakeInput> { new TakeInput("t", doc) };

        TakeScore best = TakeRecommender.RecommendBest(takes);

        Assert.Equal("t", best.Name);
        Assert.Equal(0.0, best.Score, 10);
        Assert.Equal(0.0, best.WordsPerMinute, 10);
        Assert.Equal(0, best.FillerCount);
        Assert.Equal(0, best.LongPauseCount);
        Assert.Equal(0.0, best.FillerSeconds, 10);

        string explain = TakeRecommender.Explain(best);
        Assert.Equal("t：综合 0.00（语气词 0 个/0.0 秒，长停顿 0 个，语速 0 词/分）", explain);
    }
}
