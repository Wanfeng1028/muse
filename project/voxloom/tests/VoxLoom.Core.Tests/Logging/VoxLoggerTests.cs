using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using VoxLoom.Core.Logging;
using Xunit;

namespace VoxLoom.Core.Tests.Logging;

public class VoxLoggerTests
{
    private static string NewTmpDir()
    {
        var dir = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(dir);
        return dir;
    }

    private static string ReadAllLogText(string dir)
    {
        var sb = new StringBuilder();
        foreach (var f in Directory.GetFiles(dir, "voxloom-*.log"))
            sb.Append(File.ReadAllText(f));
        return sb.ToString();
    }

    [Fact]
    public void Log_WritesJsonLineWithOperationId()
    {
        var dir = NewTmpDir();
        try
        {
            var opts = new VoxLoggerOptions { WriteToConsole = false, MinLevel = VoxLogLevel.Trace };
            using var logger = VoxLogger.Create(dir, opts);
            string opId;
            using (logger.BeginOperation("op-a"))
            {
                opId = logger.CurrentOperationId ?? "";
                logger.Info("你好", new { n = 1 });
            }
            Assert.False(string.IsNullOrEmpty(opId));

            var text = ReadAllLogText(dir);
            Assert.Contains("\"msg\":\"你好\"", text);
            Assert.Contains("\"op\":\"op-a\"", text);
            Assert.Contains("\"op_id\":\"" + opId + "\"", text);
            Assert.Matches("\"op_id\":\"[0-9a-fA-F]{8}\"", text);
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Log_RedactsSecretValues()
    {
        var dir = NewTmpDir();
        try
        {
            var opts = new VoxLoggerOptions { WriteToConsole = false, MinLevel = VoxLogLevel.Trace };
            using var logger = VoxLogger.Create(dir, opts);
            var data = new System.Collections.Generic.Dictionary<string, object>
            {
                ["apiKey"] = "sk-123",
                ["user"] = "bob",
                ["nested"] = new System.Collections.Generic.Dictionary<string, object>
                {
                    ["token"] = "t"
                }
            };
            logger.Info("with secret", data);

            var text = ReadAllLogText(dir);
            Assert.Contains("***", text);
            Assert.DoesNotContain("sk-123", text);
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Log_Rotation_RollsOverAndRetains()
    {
        var dir = NewTmpDir();
        try
        {
            var opts = new VoxLoggerOptions
            {
                WriteToConsole = false,
                MinLevel = VoxLogLevel.Trace,
                MaxFileBytes = 2048,
                MaxRetainedFiles = 3
            };
            using var logger = VoxLogger.Create(dir, opts);
            var payload = new string('x', 400);
            for (int i = 0; i < 200; i++)
                logger.Info("rotation-test-" + i, new { blob = payload });

            var files = Directory.GetFiles(dir, "voxloom-*.log");
            Assert.InRange(files.Length, 2, 3);
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Log_BelowMinLevel_Dropped()
    {
        var dir = NewTmpDir();
        try
        {
            var opts = new VoxLoggerOptions { WriteToConsole = false, MinLevel = VoxLogLevel.Warning };
            using var logger = VoxLogger.Create(dir, opts);
            logger.Info("should-not-appear-" + Guid.NewGuid().ToString("N"));

            var files = Directory.GetFiles(dir, "voxloom-*.log");
            if (files.Length > 0)
            {
                var text = ReadAllLogText(dir);
                Assert.DoesNotContain("should-not-appear-", text);
            }
            else
            {
                Assert.Empty(files);
            }
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void BeginOperation_Nesting_Restores()
    {
        var dir = NewTmpDir();
        try
        {
            var opts = new VoxLoggerOptions { WriteToConsole = false, MinLevel = VoxLogLevel.Trace };
            using var logger = VoxLogger.Create(dir, opts);

            using (logger.BeginOperation("outer"))
            {
                var a = logger.CurrentOperationId;
                Assert.False(string.IsNullOrEmpty(a));
                Assert.Equal("outer", logger.CurrentOperation);

                using (logger.BeginOperation("inner"))
                {
                    var b = logger.CurrentOperationId;
                    Assert.False(string.IsNullOrEmpty(b));
                    Assert.NotEqual(a, b);
                    Assert.Equal("inner", logger.CurrentOperation);
                }

                Assert.Equal(a, logger.CurrentOperationId);
                Assert.Equal("outer", logger.CurrentOperation);
            }
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Log_AfterDispose_DoesNotThrow()
    {
        var dir = NewTmpDir();
        try
        {
            var opts = new VoxLoggerOptions { WriteToConsole = false, MinLevel = VoxLogLevel.Trace };
            var logger = VoxLogger.Create(dir, opts);
            logger.Dispose();

            var ex = Record.Exception(() => logger.Info("after dispose"));
            Assert.Null(ex);
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }
}
