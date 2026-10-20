using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterR2LongProgramTests
{
    [Fact]
    public void Hours_100_FormatsThreeDigitHours()
    {
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromHours(100)), TimeSpan.Zero)
        };

        var edl = EdlExporter.ExportCmx3600("LONG", events, 44100);

        Assert.Contains("100:00:00:00", edl);
    }
}
