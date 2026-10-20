using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public sealed class TakeRecommenderR2DuplicateNameTests
{
    private static TranscriptDoc CleanTranscript()
    {
        var words = new List<TranscriptWord>
        {
            new TranscriptWord("内容", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5))
        };
        return new TranscriptDoc(words, TimeSpan.FromSeconds(60));
    }

    private static TranscriptDoc DirtyTranscript()
    {
        var words = new List<TranscriptWord>
        {
            new TranscriptWord("嗯", TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(0.5)),
            new TranscriptWord("嗯", TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(10.5)),
            new TranscriptWord("嗯", TimeSpan.FromSeconds(20), TimeSpan.FromSeconds(20.5))
        };
        return new TranscriptDoc(words, TimeSpan.FromSeconds(60));
    }

    [Fact]
    public void DuplicateNames_BothReturned_OrderedByScore()
    {
        var takes = new List<TakeInput>
        {
            new TakeInput("x", CleanTranscript()),
            new TakeInput("x", DirtyTranscript())
        };

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(takes);

        Assert.Equal(2, ranked.Count);
        Assert.True(ranked[0].FillerCount < ranked[1].FillerCount);
        Assert.Equal("x", ranked[0].Name);
        Assert.Equal("x", ranked[1].Name);
        Assert.Equal(0, ranked[0].FillerCount);
        Assert.Equal(3, ranked[1].FillerCount);
    }
}
