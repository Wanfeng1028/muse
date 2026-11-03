using System;
using System.Collections.Generic;
using VoxLoom.Core.Transcript;
using VoxLoom.Core.Editing;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2UnicodeNameTests
{
    [Fact]
    public void Explain_ChineseName_ExactPrefix()
    {
        var words = new List<TranscriptWord>
        {
            new TranscriptWord("内容", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5))
        };
        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(60));
        var take = new TakeInput("第一版", doc);

        TakeScore score = TakeRecommender.RecommendBest(new[] { take });

        string explanation = TakeRecommender.Explain(score);

        Assert.Equal("第一版：综合 0.00（语气词 0 个/0.0 秒，长停顿 0 个，语速 1 词/分）", explanation);
    }
}
