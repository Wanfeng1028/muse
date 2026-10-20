using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterR2MinuteCarryTests
{
    [Fact]
    public void Seconds_CarryToMinute()
    {
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.FromSeconds(59.9999), TimeSpan.FromSeconds(60.9999)), TimeSpan.Zero)
        };

        var edl = EdlExporter.ExportCmx3600("CarryTest", events, 48000);

        Assert.Contains("00:01:00:00 00:01:01:00", edl);
        Assert.Contains("001  TAPE01 V C", edl);
    }
}
