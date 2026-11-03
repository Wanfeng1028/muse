using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EdlExporterDeepTests
{
    private static string FirstLine(string s)
    {
        int idx = s.IndexOf('\n');
        return idx >= 0 ? s.Substring(0, idx) : s;
    }

    [Fact]
    public void TapeName_Null_ProducesUntitledTitle()
    {
        // 依据：tapeName 为 null → 首行 "TITLE: UNTITLED"
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)), TimeSpan.Zero)
        };
        string edl = EdlExporter.ExportCmx3600(null!, events, 16000);
        Assert.Equal("TITLE: UNTITLED", FirstLine(edl));
    }

    [Fact]
    public void TapeName_Empty_ProducesUntitledTitle()
    {
        // 依据：tapeName 为空字符串 → "TITLE: UNTITLED"
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)), TimeSpan.Zero)
        };
        string edl = EdlExporter.ExportCmx3600("", events, 16000);
        Assert.Equal("TITLE: UNTITLED", FirstLine(edl));
    }

    [Fact]
    public void Events_Null_ThrowsArgumentNullException()
    {
        // 依据：events 为 null 抛 ArgumentNullException
        Assert.Throws<ArgumentNullException>(() => EdlExporter.ExportCmx3600("T", null!, 16000));
    }

    [Fact]
    public void NegativeSourceStart_ClampedToZeroTimecode()
    {
        // 依据：负时间钳位到零 → srcIn 时间码为 00:00:00:00
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.FromSeconds(-1), TimeSpan.FromSeconds(2)), TimeSpan.Zero)
        };
        string edl = EdlExporter.ExportCmx3600("Tape", events, 16000);
        // 事件行格式：{index:000}  TAPE01 V C {srcIn} {srcOut} {recIn} {recOut}
        Assert.Contains(" C 00:00:00:00 ", edl);
    }

    [Fact]
    public void FractionalFrames_RoundUpToNextSecond()
    {
        // 依据：时长 1.99999 秒的事件终点 → 时间码 00:00:02:00（fractional*30 四舍五入得 30 帧进位）
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1.99999)), TimeSpan.Zero)
        };
        string edl = EdlExporter.ExportCmx3600("Tape", events, 16000);
        Assert.Contains("00:00:02:00", edl);
    }

    [Fact]
    public void ZeroDurationEvent_EmitsLineWithEqualInOut()
    {
        // 依据：零时长事件（srcIn==srcOut）行仍输出且两端时间码相同
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(2)), TimeSpan.FromSeconds(5))
        };
        string edl = EdlExporter.ExportCmx3600("Tape", events, 16000);
        // srcIn=srcOut=00:00:02:00
        Assert.Contains("00:00:02:00 00:00:02:00", edl);
    }

    [Fact]
    public void TwoEvents_IndicesIncrement_AndRecStartPreserved()
    {
        // 依据：index 递增 001、002；第二事件 recIn 等于传入的 recordStart（不自动连续）
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)), TimeSpan.Zero),
            (new TimeRange(TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(6)), TimeSpan.FromSeconds(10))
        };
        string edl = EdlExporter.ExportCmx3600("Tape", events, 16000);
        Assert.Contains("001", edl);
        Assert.Contains("002", edl);
        // 第二事件 recIn 应为 00:00:10:00
        Assert.Contains("00:00:10:00", edl);
    }

    [Fact]
    public void OverOneHour_ProducesCorrectTimecode()
    {
        // 依据：3723.5 秒 → 时间码 01:02:03:15
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(3723.5)), TimeSpan.Zero)
        };
        string edl = EdlExporter.ExportCmx3600("Tape", events, 16000);
        Assert.Contains("01:02:03:15", edl);
    }

    [Fact]
    public void BasicFormat_ContainsFcmAndClipName()
    {
        // 依据：单事件输出包含 "FCM: NON-DROP FRAME" 与 "* FROM CLIP NAME: "
        var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>
        {
            (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)), TimeSpan.Zero)
        };
        string edl = EdlExporter.ExportCmx3600("Tape", events, 16000);
        Assert.Contains("FCM: NON-DROP FRAME", edl);
        Assert.Contains("* FROM CLIP NAME: ", edl);
    }
}
