using System;
using Xunit;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterR2ManyEventsTests
{
    [Fact]
    public void Events_999_LastIndexIs999()
    {
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>();
        for (int i = 0; i < 999; i++)
        {
            var start = TimeSpan.FromSeconds(i * 10);
            var end = TimeSpan.FromSeconds(i * 10 + 5);
            events.Add((new TimeRange(start, end), start));
        }

        var edl = EdlExporter.ExportCmx3600("TAPE", events, 44100);

        Assert.Contains("\n999  TAPE01 V C", edl);
    }
}
