using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterTests
{
    [Fact]
    public void ExportCmx3600_ProducesExpectedFormat()
    {
        var events = new List<(TimeRange, TimeSpan)>
        {
            (new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(5)),
             TimeSpan.Zero)
        };

        string edl = EdlExporter.ExportCmx3600("TAPE01", events, 16000);

        Assert.Contains("TITLE: TAPE01", edl);
        Assert.Contains("FCM: NON-DROP FRAME", edl);
        // 事件行：源 1s→5s，录制 0s→4s
        Assert.Contains("001  TAPE01 V C 00:00:01:00 00:00:05:00 00:00:00:00 00:00:04:00", edl);
        Assert.Contains("* FROM CLIP NAME: TAPE01", edl);
    }

    [Fact]
    public void ExportCmx3600_TwoEvents_HasTwoEventLines()
    {
        var events = new List<(TimeRange, TimeSpan)>
        {
            (new TimeRange(TimeSpan.FromSeconds(0), TimeSpan.FromSeconds(2)),
             TimeSpan.Zero),
            (new TimeRange(TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(5)),
             TimeSpan.FromSeconds(2))
        };

        string edl = EdlExporter.ExportCmx3600("CLIP", events, 44100);

        var lines = edl.Split('\n');
        int eventLineCount = 0;
        foreach (var line in lines)
        {
            string trimmed = line.TrimEnd('\r');
            if (trimmed.Length > 4 && char.IsDigit(trimmed[0]) && trimmed.Contains(" V C "))
            {
                eventLineCount++;
            }
        }

        Assert.Equal(2, eventLineCount);
    }

    [Fact]
    public void ExportCmx3600_FramePrecision()
    {
        // 1.5 秒 = 1 秒 15 帧（30fps）
        var events = new List<(TimeRange, TimeSpan)>
        {
            (new TimeRange(TimeSpan.FromSeconds(1.5), TimeSpan.FromSeconds(2.5)),
             TimeSpan.Zero)
        };

        string edl = EdlExporter.ExportCmx3600("X", events, 16000);

        Assert.Contains("00:00:01:15", edl); // 1.5s → 1s 15帧
        Assert.Contains("00:00:02:15", edl); // 2.5s → 2s 15帧
    }
}
