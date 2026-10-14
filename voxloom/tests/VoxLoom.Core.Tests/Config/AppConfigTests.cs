using System;
using System.IO;
using VoxLoom.Core.Config;
using Xunit;

namespace VoxLoom.Core.Tests.Config;

public class AppConfigTests
{
    private static string NewTmpDir()
    {
        var dir = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(dir);
        return dir;
    }

    private static string SetEnv(string name, string? value)
    {
        var old = Environment.GetEnvironmentVariable(name);
        Environment.SetEnvironmentVariable(name, value);
        return old!;
    }

    private static void RestoreEnv(string name, string? old)
    {
        Environment.SetEnvironmentVariable(name, old);
    }

    [Fact]
    public void Load_MissingFile_ReturnsDefaults()
    {
        var dir = NewTmpDir();
        try
        {
            var cfgPath = Path.Combine(dir, "does-not-exist.json");
            var cfg = AppConfig.Load(cfgPath);
            Assert.Equal("ffmpeg", cfg.FfmpegPath);
            Assert.Equal(10, cfg.BackupRetentionCount);
            Assert.False(string.IsNullOrEmpty(cfg.LogDirectory));
            Assert.False(string.IsNullOrEmpty(cfg.BackupDirectory));
            Assert.False(string.IsNullOrEmpty(cfg.ProjectsDirectory));
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Load_FileValues_And_EnvOverride()
    {
        var dir = NewTmpDir();
        string? oldRet = null;
        try
        {
            var cfgPath = Path.Combine(dir, "config.json");
            File.WriteAllText(cfgPath, "{\"backupRetentionCount\":7,\"logDirectory\":\"./mylogs\"}");

            var cfg = AppConfig.Load(cfgPath);
            Assert.Equal(7, cfg.BackupRetentionCount);
            Assert.Contains("mylogs", cfg.LogDirectory);

            oldRet = SetEnv("VOXLOOM_BACKUP_RETENTION", "5");
            var cfg2 = AppConfig.Load(cfgPath);
            Assert.Equal(5, cfg2.BackupRetentionCount);
        }
        finally
        {
            if (oldRet != null || Environment.GetEnvironmentVariable("VOXLOOM_BACKUP_RETENTION") != null)
                RestoreEnv("VOXLOOM_BACKUP_RETENTION", oldRet);
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Load_SecretKeyInFile_Throws()
    {
        var dir = NewTmpDir();
        try
        {
            var cfgPath = Path.Combine(dir, "config.json");
            File.WriteAllText(cfgPath, "{\"apiKey\":\"sk-x\"}");
            Assert.Throws<ConfigValidationException>(() => AppConfig.Load(cfgPath));
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Load_BadJson_Throws()
    {
        var dir = NewTmpDir();
        try
        {
            var cfgPath = Path.Combine(dir, "config.json");
            File.WriteAllText(cfgPath, "{\"a\":");
            Assert.Throws<ConfigValidationException>(() => AppConfig.Load(cfgPath));
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Validate_CollectsAllProblems()
    {
        var dir = NewTmpDir();
        string? oldRet = Environment.GetEnvironmentVariable("VOXLOOM_BACKUP_RETENTION");
        string? oldLog = Environment.GetEnvironmentVariable("VOXLOOM_LOG_DIR");
        try
        {
            Environment.SetEnvironmentVariable("VOXLOOM_BACKUP_RETENTION", null);
            Environment.SetEnvironmentVariable("VOXLOOM_LOG_DIR", null);

            var cfgPath = Path.Combine(dir, "config.json");
            File.WriteAllText(cfgPath, "{\"backupRetentionCount\":0,\"logDirectory\":\"\"}");
            var cfg = AppConfig.Load(cfgPath);
            var ex = Assert.Throws<ConfigValidationException>(() => cfg.Validate());
            Assert.Contains("1..100", ex.Message);
            Assert.Contains("日志", ex.Message);
        }
        finally
        {
            RestoreEnv("VOXLOOM_BACKUP_RETENTION", oldRet);
            RestoreEnv("VOXLOOM_LOG_DIR", oldLog);
            try { Directory.Delete(dir, true); } catch { }
        }
    }

    [Fact]
    public void Validate_BadRetentionEnv_Throws()
    {
        var dir = NewTmpDir();
        string? old = null;
        try
        {
            var cfgPath = Path.Combine(dir, "config.json");
            File.WriteAllText(cfgPath, "{}");
            old = SetEnv("VOXLOOM_BACKUP_RETENTION", "abc");
            Assert.Throws<ConfigValidationException>(() => AppConfig.Load(cfgPath));
        }
        finally
        {
            RestoreEnv("VOXLOOM_BACKUP_RETENTION", old);
            try { Directory.Delete(dir, true); } catch { }
        }
    }
}
