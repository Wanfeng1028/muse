using System;
using Xunit;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterR2EmptyEventsTests
{
    [Fact]
    public void EmptyEvents_HeaderOnly()
    {
        IReadOnlyList<(TimeRange SourceRange, TimeSpan RecordStart)> events = Array.Empty<(TimeRange SourceRange, TimeSpan RecordStart)>();

        string actual = EdlExporter.ExportCmx3600("T", events, 44100);

        Assert.Equal("TITLE: T\nFCM: NON-DROP FRAME\n", actual);
    }
}
