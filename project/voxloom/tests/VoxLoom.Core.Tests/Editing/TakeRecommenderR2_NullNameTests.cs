using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2NullNameTests
{
    private static TranscriptDoc MakeDoc()
    {
        var words = new List<TranscriptWord>
        {
            new TranscriptWord("你好", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5)),
            new TranscriptWord("世界", TimeSpan.FromSeconds(0.6), TimeSpan.FromSeconds(1.0))
        };
        return new TranscriptDoc(words, TimeSpan.FromSeconds(1.0));
    }

    [Fact]
    public void Rank_NullName_ThrowsArgumentException()
    {
        var doc = MakeDoc();
        var takes = new List<TakeInput>
        {
            new TakeInput(null!, doc)
        };

        Assert.Throws<ArgumentException>(() => TakeRecommender.Rank(takes));
    }
}
