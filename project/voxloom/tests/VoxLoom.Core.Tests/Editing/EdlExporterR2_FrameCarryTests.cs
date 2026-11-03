using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterR2FrameCarryTests
{
    [Fact]
    public void Frames_RoundUpCarriesSecond()
    {
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.FromSeconds(0.9834), TimeSpan.FromSeconds(1.9834)), TimeSpan.Zero)
        };

        string edl = EdlExporter.ExportCmx3600("DEMO", events, 48000);

        Assert.Contains("00:00:01:00 00:00:02:00", edl);
    }
}
