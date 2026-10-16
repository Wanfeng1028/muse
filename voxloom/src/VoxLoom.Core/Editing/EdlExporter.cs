using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using VoxLoom.Core.Transcript;

using VoxLoom.Core.Logging;
namespace VoxLoom.Core.Editing;

/// <summary>
/// EDL 导出器：输出简化版 CMX3600 时间码，供 Premiere / Reaper 等非线性编辑软件导入。
/// </summary>
public static class EdlExporter
{
    private const int DefaultFrameRate = 30;
    private const string DefaultReelName = "TAPE01";

    /// <summary>
    /// 导出 CMX3600 格式 EDL 文本。
    /// </summary>
    /// <param name="tapeName">磁带名/素材名，用于 EDL 首行标题。</param>
    /// <param name="events">事件列表：每个事件包含源时间区间与录制起点。</param>
    /// <param name="sampleRate">源音频采样率（保留供扩展；当前时间码按秒换算）。</param>
    public static string ExportCmx3600(
        string tapeName,
        IReadOnlyList<(TimeRange SourceRange, TimeSpan RecordStart)> events,
        int sampleRate)
        => VoxMetrics.Timed("export.edl", () => ExportCmx3600Core(tapeName, events, sampleRate));

    private static string ExportCmx3600Core(
        string tapeName,
        IReadOnlyList<(TimeRange SourceRange, TimeSpan RecordStart)> events,
        int sampleRate)
    {
        ArgumentNullException.ThrowIfNull(events);

        string title = string.IsNullOrWhiteSpace(tapeName) ? "UNTITLED" : tapeName;

        var sb = new StringBuilder();
        sb.Append("TITLE: ").Append(title).Append('\n');
        sb.Append("FCM: NON-DROP FRAME\n");

        int index = 1;
        foreach (var (sourceRange, recordStart) in events)
        {
            string reel = DefaultReelName;
            string srcIn = ToTimecode(sourceRange.Start);
            string srcOut = ToTimecode(sourceRange.End);

            // 录制起点 = recordStart；录制终点 = recordStart + 源区间时长
            var duration = sourceRange.End - sourceRange.Start;
            var recordEnd = recordStart + duration;

            string recIn = ToTimecode(recordStart);
            string recOut = ToTimecode(recordEnd);

            string line = string.Format(
                CultureInfo.InvariantCulture,
                "{0:000}  {1} V C {2} {3} {4} {5}",
                index, reel, srcIn, srcOut, recIn, recOut);

            sb.Append(line).Append('\n');
            sb.Append("* FROM CLIP NAME: ").Append(title).Append('\n');

            index++;
        }

        return sb.ToString();
    }

    /// <summary>
    /// 将 TimeSpan 转换为 HH:MM:SS:FF 时间码（30fps）。
    /// </summary>
    private static string ToTimecode(TimeSpan t)
    {
        if (t < TimeSpan.Zero) t = TimeSpan.Zero;

        int totalSeconds = (int)t.TotalSeconds;
        // 剩余小数部分换算为帧（四舍五入到最接近的帧）
        double fractional = t.TotalSeconds - totalSeconds;
        int frames = (int)Math.Round(fractional * DefaultFrameRate);

        // 处理进位
        if (frames >= DefaultFrameRate)
        {
            frames -= DefaultFrameRate;
            totalSeconds += 1;
        }

        int hours = totalSeconds / 3600;
        int minutes = (totalSeconds % 3600) / 60;
        int seconds = totalSeconds % 60;

        return string.Format(
            CultureInfo.InvariantCulture,
            "{0:00}:{1:00}:{2:00}:{3:00}",
            hours, minutes, seconds, frames);
    }
}
