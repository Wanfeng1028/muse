using System;
using System.Collections.Generic;
using VoxLoom.Core.Transcript;
using VoxLoom.Core.Editing;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterR2SpecialTapeNameTests
{
    [Fact]
    public void TapeName_SpecialChars_PassedThrough()
    {
        // Arrange
        string tapeName = "第1期·采访/张三";
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(10)), TimeSpan.Zero)
        };

        // Act
        string result = EdlExporter.ExportCmx3600(tapeName, events, 44100);

        // Assert
        Assert.Contains("TITLE: 第1期·采访/张三\n", result);
        Assert.Contains("* FROM CLIP NAME: 第1期·采访/张三", result);
    }
}
