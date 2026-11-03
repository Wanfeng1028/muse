using System;
using System.IO;
using System.Linq;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupR2DeleteTests
{
    private static string NewTmpDir()
        => Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));

    private static void WriteProject(string dir)
    {
        Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, "a.txt"), "hello");
        Directory.CreateDirectory(Path.Combine(dir, "sub"));
        File.WriteAllText(Path.Combine(dir, "sub", "b.txt"), "world");
    }

    [Fact]
    public void DeleteBackup_RemovesZipAndSidecar()
    {
        var root = NewTmpDir();
        var backupDir = Path.Combine(root, "backups");
        var projectDir = Path.Combine(root, "project");
        try
        {
            WriteProject(projectDir);
            var mgr = new BackupManager(backupDir, retentionCount: 10);
            var rec = mgr.CreateBackup(projectDir, "demo");

            var zipPath = Path.Combine(backupDir, rec.Id + ".zip");
            var sidecarPath = Path.Combine(backupDir, rec.Id + ".json");
            Assert.True(File.Exists(zipPath));
            Assert.True(File.Exists(sidecarPath));

            mgr.DeleteBackup(rec.Id);

            Assert.False(File.Exists(zipPath));
            Assert.False(File.Exists(sidecarPath));
            Assert.Empty(mgr.ListBackups());
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void DeleteBackup_UnknownId_Throws()
    {
        var root = NewTmpDir();
        var backupDir = Path.Combine(root, "backups");
        try
        {
            var mgr = new BackupManager(backupDir, retentionCount: 10);
            Assert.Throws<BackupException>(() => mgr.DeleteBackup("no-such-id"));
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }
}
