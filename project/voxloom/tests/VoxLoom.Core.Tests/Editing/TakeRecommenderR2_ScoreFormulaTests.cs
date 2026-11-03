using System;
using System.Collections.Generic;
using Xunit;
using VoxLoom.Core.Transcript;
using VoxLoom.Core.Editing;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2ScoreFormulaTests
{
    [Fact]
    public void Score_ExactFormula_AllComponents()
    {
        var words = new List<TranscriptWord>
        {
            new TranscriptWord("啊", TimeSpan.FromSeconds(0.0), TimeSpan.FromSeconds(1.0)),
            new TranscriptWord("内容一", TimeSpan.FromSeconds(5.0), TimeSpan.FromSeconds(5.5)),
            new TranscriptWord("内容二", TimeSpan.FromSeconds(12.0), TimeSpan.FromSeconds(12.5)),
        };

        var doc = new TranscriptDoc(words, TimeSpan.FromSeconds(120));

        var takes = new List<TakeInput>
        {
            new TakeInput("take1", doc),
        };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.Single(ranked);
        TakeScore s = ranked[0];

        Assert.Equal("take1", s.Name);
        Assert.Equal(1, s.FillerCount);
        Assert.Equal(1.0, s.FillerSeconds, 9);
        Assert.Equal(2, s.LongPauseCount);
        Assert.Equal(1.5, s.WordsPerMinute, 9);
        Assert.Equal(2.9166666666666665, s.Score, 12);
    }
}
