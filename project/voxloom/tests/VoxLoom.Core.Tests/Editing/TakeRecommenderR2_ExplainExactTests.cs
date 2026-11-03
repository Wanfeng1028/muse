using System;
using System.Collections.Generic;
using Xunit;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2ExplainExactTests
{
    [Fact]
    public void Explain_ExactFormat_SingleFiller()
    {
        var words = new List<TranscriptWord>
        {
            new TranscriptWord("嗯", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5))
        };
        var transcript = new TranscriptDoc(words, TimeSpan.FromSeconds(60));

        var takes = new List<TakeInput>
        {
            new TakeInput("t", transcript)
        };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);
        TakeScore score = ranked[0];

        string actual = TakeRecommender.Explain(score);

        Assert.Equal("t：综合 1.42（语气词 1 个/0.5 秒，长停顿 0 个，语速 1 词/分）", actual);
    }
}
