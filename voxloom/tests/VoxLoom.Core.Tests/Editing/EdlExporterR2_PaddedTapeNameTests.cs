using Xunit;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterR2PaddedTapeNameTests
{
    [Fact]
    public void TapeName_WithSpaces_Preserved()
    {
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)), TimeSpan.Zero)
        };

        var actual = EdlExporter.ExportCmx3600("  My Tape  ", events, 48000);

        Assert.StartsWith("TITLE:   My Tape  \n", actual);
    }
}
