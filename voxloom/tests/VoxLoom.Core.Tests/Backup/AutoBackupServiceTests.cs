
using System;
using System.IO;
using System.Threading;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public sealed class AutoBackupServiceTests
{
    private static string NewTempDir()
        => Path.Combine(Path.GetTempPath(), "voxloom-tests-" + Guid.NewGuid().ToString("N")[..8]);

    [Fact]
    public void DisabledService_DoesNotBackup()
    {
        var dir = NewTempDir();
        Directory.CreateDirectory(dir);
        try
        {
            var options = new AutoBackupOptions { Enabled = false, IntervalMinutes = 1 };
            int calls = 0;
            using var service = new AutoBackupService(
                options,
                () => dir,
                () => "proj",
                (a, b, c) =>
                {
                    Interlocked.Increment(ref calls);
                    return new BackupRecord("id", DateTime.UtcNow, "f.zip", 1, "abc");
                });

            service.Start();
            Thread.Sleep(TimeSpan.FromSeconds(3));
            service.Stop();

            Assert.Equal(0, Volatile.Read(ref calls));
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void InvalidInterval_Throws()
    {
        var dir = NewTempDir();
        Directory.CreateDirectory(dir);
        try
        {
            var options = new AutoBackupOptions { Enabled = true, IntervalMinutes = 0 };
            int calls = 0;
            using var service = new AutoBackupService(
                options,
                () => dir,
                () => "proj",
                (a, b, c) =>
                {
                    Interlocked.Increment(ref calls);
                    return new BackupRecord("id", DateTime.UtcNow, "f.zip", 1, "abc");
                });

            Assert.Throws<BackupException>(() => service.Start());
            Assert.Equal(0, Volatile.Read(ref calls));

            // 服务未启动，Stop 应为无操作
            service.Stop();
            Assert.Equal(0, Volatile.Read(ref calls));
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void DoubleStart_Throws()
    {
        var dir = NewTempDir();
        Directory.CreateDirectory(dir);
        try
        {
            var options = new AutoBackupOptions { Enabled = true, IntervalMinutes = 1 };
            using var service = new AutoBackupService(
                options,
                () => dir,
                () => "proj",
                (a, b, c) => new BackupRecord("id", DateTime.UtcNow, "f.zip", 1, "abc"));

            service.Start();
            Assert.Throws<InvalidOperationException>(() => service.Start());
            service.Stop();
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void StopWithoutStart_NoOp()
    {
        var options = new AutoBackupOptions { Enabled = true, IntervalMinutes = 1 };
        var service = new AutoBackupService(
            options,
            () => null,
            () => null,
            (a, b, c) => new BackupRecord("id", DateTime.UtcNow, "f.zip", 1, "abc"));

        service.Stop();
        service.Stop();
        service.Dispose();
    }

    [Fact]
    public void NullProject_SkipsBackup()
    {
        var options = new AutoBackupOptions { Enabled = true, IntervalMinutes = 1 };
        int calls = 0;
        using var service = new AutoBackupService(
            options,
            () => null,
            () => "proj",
            (a, b, c) =>
            {
                Interlocked.Increment(ref calls);
                return new BackupRecord("id", DateTime.UtcNow, "f.zip", 1, "abc");
            });

        using var signal = new ManualResetEventSlim(false);
        service.BackupCompleted += (_, _) => signal.Set();

        service.Start();
        bool completed = signal.Wait(TimeSpan.FromSeconds(75));
        service.Stop();

        Assert.False(completed);
        Assert.Equal(0, Volatile.Read(ref calls));
    }

    [Fact]
    public void Interval_TriggersBackup()
    {
        var dir = NewTempDir();
        Directory.CreateDirectory(dir);
        try
        {
            var options = new AutoBackupOptions { Enabled = true, IntervalMinutes = 1 };
            int calls = 0;
            using var service = new AutoBackupService(
                options,
                () => dir,
                () => "proj",
                (a, b, c) =>
                {
                    Interlocked.Increment(ref calls);
                    return new BackupRecord("id", DateTime.UtcNow, "f.zip", 1, "abc");
                });

            using var signal = new ManualResetEventSlim(false);
            service.BackupCompleted += (_, _) => signal.Set();

            service.Start();
            bool completed = signal.Wait(TimeSpan.FromSeconds(75));
            service.Stop();

            Assert.True(completed);
            Assert.True(Volatile.Read(ref calls) >= 1);
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void BackupFuncThrows_DoesNotCrash()
    {
        var dir = NewTempDir();
        Directory.CreateDirectory(dir);
        try
        {
            var options = new AutoBackupOptions { Enabled = true, IntervalMinutes = 1 };
            using var service = new AutoBackupService(
                options,
                () => dir,
                () => "proj",
                (a, b, c) => throw new InvalidOperationException("boom"));

            using var signal = new ManualResetEventSlim(false);
            service.BackupFailed += (_, _) => signal.Set();

            service.Start();
            bool failed = signal.Wait(TimeSpan.FromSeconds(75));
            service.Stop();

            Assert.True(failed);
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }
}
