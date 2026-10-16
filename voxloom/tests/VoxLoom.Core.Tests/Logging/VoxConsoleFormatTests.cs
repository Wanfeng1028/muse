using System;
using System.Linq;
using VoxLoom.Core.Logging;
using Xunit;

namespace VoxLoom.Core.Tests.Logging;

public class VoxConsoleFormatTests
{
    [Fact]
    public void FormatDuration_Humanizes()
    {
        Assert.Equal("0ms", VoxConsoleFormat.FormatDuration(TimeSpan.Zero));
        Assert.Equal("320ms", VoxConsoleFormat.FormatDuration(TimeSpan.FromMilliseconds(320)));
        Assert.Equal("3.2s", VoxConsoleFormat.FormatDuration(TimeSpan.FromSeconds(3.2)));
        Assert.Equal("1m30s", VoxConsoleFormat.FormatDuration(TimeSpan.FromSeconds(90)));
        Assert.Equal("2h5m", VoxConsoleFormat.FormatDuration(TimeSpan.FromHours(2) + TimeSpan.FromMinutes(5)));
    }

    [Fact]
    public void FormatBytes_Humanizes()
    {
        Assert.Equal("0 B", VoxConsoleFormat.FormatBytes(0));
        Assert.Equal("7 B", VoxConsoleFormat.FormatBytes(7));
        Assert.Equal("1.5 KB", VoxConsoleFormat.FormatBytes(1536));
        Assert.Equal("3.2 MB", VoxConsoleFormat.FormatBytes(3_400_000));
    }

    [Fact]
    public void RenderLine_Shape()
    {
        var line = VoxConsoleFormat.RenderLine(
            VoxLogLevel.Info,
            "备份完成",
            "backup",
            "a1b2c3d4",
            "{\"bytes\":1536}",
            new DateTime(2026, 10, 16, 6, 32, 5, DateTimeKind.Utc));

        Assert.StartsWith("[", line);
        Assert.Contains("] INFO  备份完成", line);
        Assert.Contains("op=backup", line);
        Assert.Contains("id=a1b2c3d4", line);
        Assert.Contains("bytes=1.5 KB", line);
    }

    [Fact]
    public void RenderTable_AlignsCjk()
    {
        var headers = new[] { "文件", "大小" };
        var rows = new[]
        {
            new[] { "a.txt", "7 B" },
            new[] { "中文文件.txt", "1.5 KB" }
        };

        var table = VoxConsoleFormat.RenderTable(headers, rows);
        var lines = table.Split('\n');

        Assert.True(lines.Length >= 4);
        var expected = VoxConsoleFormat.DisplayWidth(lines[0]);
        foreach (var l in lines)
        {
            Assert.Equal(expected, VoxConsoleFormat.DisplayWidth(l));
        }

        Assert.Contains("文件", lines[0]);
        Assert.Contains("大小", lines[0]);
        Assert.Contains("---", lines[1]);
    }

    [Fact]
    public void RenderProgressBar_Shapes()
    {
        var zero = VoxConsoleFormat.RenderProgressBar(0);
        Assert.EndsWith("0%", zero);
        Assert.DoesNotContain("█", zero);

        Assert.Equal("█████░░░░░ 50%", VoxConsoleFormat.RenderProgressBar(0.5, 10));

        var full = VoxConsoleFormat.RenderProgressBar(1);
        Assert.EndsWith("100%", full);
        Assert.DoesNotContain("░", full);

        var clamped = VoxConsoleFormat.RenderProgressBar(2);
        Assert.EndsWith("100%", clamped);
        Assert.DoesNotContain("░", clamped);
    }

    [Fact]
    public void RenderLine_RedactsSecrets()
    {
        var line = VoxConsoleFormat.RenderLine(
            VoxLogLevel.Info,
            "用户登录",
            null,
            null,
            "{\"password\":\"***\",\"user\":\"bob\"}",
            new DateTime(2026, 10, 16, 6, 32, 5, DateTimeKind.Utc));

        Assert.Contains("***", line);
        Assert.Contains("user=bob", line);
    }

    [Fact]
    public void ColorFor_MapsLevels()
    {
        Assert.Equal(ConsoleColor.Red, VoxConsoleFormat.ColorFor(VoxLogLevel.Error));
        Assert.Equal(ConsoleColor.Yellow, VoxConsoleFormat.ColorFor(VoxLogLevel.Warning));
        Assert.Null(VoxConsoleFormat.ColorFor(VoxLogLevel.Info));
        Assert.Equal(ConsoleColor.Gray, VoxConsoleFormat.ColorFor(VoxLogLevel.Debug));
    }
}
