using System;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterR2FrameNoCarryTests
{
    [Fact]
    public void Frames_NoCarryStays29()
    {
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.FromSeconds(0.9833), TimeSpan.FromSeconds(2.0)), TimeSpan.Zero)
        };

        string edl = EdlExporter.ExportCmx3600("TAPE01", events, 44100);

        Assert.Contains("00:00:00:29 00:00:02:00", edl, StringComparison.Ordinal);
    }
}
