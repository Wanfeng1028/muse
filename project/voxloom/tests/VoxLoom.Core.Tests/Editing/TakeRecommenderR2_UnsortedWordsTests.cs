using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class TakeRecommenderR2UnsortedWordsTests
{
    [Fact]
    public void UnsortedInput_SortedBeforePauseCount()
    {
        var words = new List<TranscriptWord>
        {
            new TranscriptWord("内容", TimeSpan.FromSeconds(12.0), TimeSpan.FromSeconds(12.5)),
            new TranscriptWord("内容", TimeSpan.FromSeconds(0.0), TimeSpan.FromSeconds(0.5)),
            new TranscriptWord("内容", TimeSpan.FromSeconds(6.0), TimeSpan.FromSeconds(6.5)),
        };

        var transcript = new TranscriptDoc(words, TimeSpan.FromSeconds(60));
        var take = new TakeInput("take1", transcript);

        IReadOnlyList<TakeScore> ranked = TakeRecommender.Rank(new[] { take });

        Assert.Single(ranked);
        Assert.Equal(2, ranked[0].LongPauseCount);
    }
}
