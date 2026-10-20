using Xunit;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterR2NegativeRecordTests
{
    [Fact]
    public void NegativeRecordStart_ClampedToZero()
    {
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(10)), TimeSpan.FromSeconds(-5))
        };

        string edl = EdlExporter.ExportCmx3600("TEST TAPE", events, 48000);

        Assert.Contains(
            "001  TAPE01 V C 00:00:00:00 00:00:10:00 00:00:00:00 00:00:05:00",
            edl);
    }
}

