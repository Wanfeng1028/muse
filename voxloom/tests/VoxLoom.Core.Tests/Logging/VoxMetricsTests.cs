using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using VoxLoom.Core.Logging;
using Xunit;

namespace VoxLoom.Core.Tests.Logging;

[Collection("MetricsSerial")]
public class VoxMetricsTests
{
    // 每个用例独立临时目录，命名规则遵循约定。
    private static string NewTempDir()
    {
        return Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N")[..8]);
    }

    // 读取目录下唯一的 metrics-*.jsonl 文件的全部行；不存在则返回空数组。
    private static string[] ReadAllLines(string dir)
    {
        if (!Directory.Exists(dir)) return Array.Empty<string>();
        var files = Directory.GetFiles(dir, "metrics-*.jsonl");
        if (files.Length == 0) return Array.Empty<string>();
        return File.ReadAllLines(files[0]);
    }

    private static string[] ReadAllLinesOfFile(string filePath)
    {
        return File.ReadAllLines(filePath);
    }

    // 从若干行里拼出一个字符串，方便做 Contains 断言。
    private static string JoinLines(string dir)
    {
        return string.Join("\n", ReadAllLines(dir));
    }

    [Fact]
    public void Record_WritesJsonlLine()
    {
        var dir = NewTempDir();
        try
        {
            VoxMetrics.Initialize(dir);
            VoxMetrics.Record("op.a", TimeSpan.FromMilliseconds(12.5), true, items: 7);

            var files = Directory.GetFiles(dir, "metrics-*.jsonl");
            Assert.Single(files);

            var lines = ReadAllLinesOfFile(files[0]);
            Assert.Single(lines);

            var line = lines[0];
            Assert.Contains("\"op\":\"op.a\"", line);
            Assert.Contains("\"success\":true", line);
            Assert.Contains("\"items\":7", line);
            Assert.Contains("\"duration_ms\":12.5", line);
        }
        finally
        {
            VoxMetrics.Shutdown();
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void Timed_ReturnsValueAndRecordsSuccess()
    {
        var dir = NewTempDir();
        try
        {
            VoxMetrics.Initialize(dir);
            var r = VoxMetrics.Timed("op.b", () => 42, items: 3);
            Assert.Equal(42, r);

            var joined = JoinLines(dir);
            Assert.Contains("\"op\":\"op.b\"", joined);
            Assert.Contains("\"success\":true", joined);
        }
        finally
        {
            VoxMetrics.Shutdown();
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void Timed_OnException_RecordsFailureAndRethrows()
    {
        var dir = NewTempDir();
        try
        {
            VoxMetrics.Initialize(dir);

            Assert.Throws<InvalidOperationException>(() =>
                VoxMetrics.Timed("op.c", () => throw new InvalidOperationException("boom")));

            var joined = JoinLines(dir);
            Assert.Contains("\"success\":false", joined);
            Assert.Contains("\"error_type\":\"InvalidOperationException\"", joined);
        }
        finally
        {
            VoxMetrics.Shutdown();
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void Timed_VoidOverload_Works()
    {
        var dir = NewTempDir();
        try
        {
            VoxMetrics.Initialize(dir);
            // 不应抛异常。
            VoxMetrics.Timed("op.d", () => { });

            var joined = JoinLines(dir);
            Assert.Contains("\"op\":\"op.d\"", joined);
        }
        finally
        {
            VoxMetrics.Shutdown();
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void ReadSummary_Aggregates()
    {
        var dir = NewTempDir();
        try
        {
            VoxMetrics.Initialize(dir);

            // op.x：两次成功（10ms、20ms），一次失败（30ms，error_type=E1）。
            VoxMetrics.Record("op.x", TimeSpan.FromMilliseconds(10), true);
            VoxMetrics.Record("op.x", TimeSpan.FromMilliseconds(20), true);
            VoxMetrics.Record("op.x", TimeSpan.FromMilliseconds(30), false, errorType: "E1");

            // op.y：一次成功（5ms）。
            VoxMetrics.Record("op.y", TimeSpan.FromMilliseconds(5), true);

            var summaries = VoxMetrics.ReadSummary(dir, null);

            // 按 Op 字母序：op.x 在前，op.y 在后。
            Assert.Equal(2, summaries.Count);

            var sx = summaries[0];
            Assert.Equal("op.x", sx.Op);
            Assert.Equal(3, sx.Count);
            Assert.Equal(1, sx.Failures);
            // (10+20+30)/3 == 20.0
            Assert.Equal(20.0, sx.AvgMs, 3);
            // 2/3 ≈ 0.6667
            Assert.True(Math.Abs(sx.SuccessRate - 0.6667) < 0.0001,
                $"期望 SuccessRate≈0.6667，实际 {sx.SuccessRate}");

            var sy = summaries[1];
            Assert.Equal("op.y", sy.Op);
            Assert.Equal(1, sy.Count);
            Assert.Equal(0, sy.Failures);
            Assert.Equal(1.0, sy.SuccessRate, 3);
        }
        finally
        {
            VoxMetrics.Shutdown();
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void ReadSummary_SinceUtc_Filters()
    {
        var dir = NewTempDir();
        try
        {
            VoxMetrics.Initialize(dir);

            VoxMetrics.Record("op.s", TimeSpan.FromMilliseconds(1), true);
            VoxMetrics.Record("op.s", TimeSpan.FromMilliseconds(2), true);

            // sinceUtc 在未来 -> 应过滤掉全部记录。
            var future = VoxMetrics.ReadSummary(dir, DateTime.UtcNow.AddMinutes(5));
            var futureTotal = future.Sum(s => s.Count);
            Assert.Equal(0, futureTotal);

            // sinceUtc 在一小时前 -> 应包含全部记录。
            var past = VoxMetrics.ReadSummary(dir, DateTime.UtcNow.AddHours(-1));
            var pastTotal = past.Sum(s => s.Count);
            Assert.Equal(2, pastTotal);
        }
        finally
        {
            VoxMetrics.Shutdown();
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void Rotation_CapsRetainedFiles()
    {
        var dir = NewTempDir();
        try
        {
            VoxMetrics.MaxFileBytes = 200;
            VoxMetrics.MaxRetainedFiles = 3;

            VoxMetrics.Initialize(dir);

            for (int i = 0; i < 20; i++)
            {
                VoxMetrics.Record("op.r" + (i % 4), TimeSpan.FromMilliseconds(1), true);
            }

            // 触发一次显式 Shutdown 以释放 writer，保证磁盘上的文件计数稳定。
            VoxMetrics.Shutdown();

            var files = Directory.GetFiles(dir, "metrics-*.jsonl");
            Assert.True(files.Length <= 3,
                $"期望保留文件数 ≤ 3，实际 {files.Length}（{string.Join(",", files.Select(Path.GetFileName))}）");
        }
        finally
        {
            VoxMetrics.Shutdown();
            VoxMetrics.MaxFileBytes = 5 * 1024 * 1024;
            VoxMetrics.MaxRetainedFiles = 10;
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void Record_BeforeInitialize_DropsSilently()
    {
        var dir = NewTempDir();
        try
        {
            // 未 Initialize，直接写：不应抛异常。
            VoxMetrics.Record("op.z", TimeSpan.FromMilliseconds(1), true);
            var r = VoxMetrics.Timed("op.z", () => 1);
            Assert.Equal(1, r);

            // 目录可能不存在；若存在，也不应有 metrics-*.jsonl 文件。
            if (Directory.Exists(dir))
            {
                var files = Directory.GetFiles(dir, "metrics-*.jsonl");
                Assert.Empty(files);
            }
        }
        finally
        {
            VoxMetrics.Shutdown();
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }
}
