using System;
using System.IO;
using System.Linq;
using System.Threading;
using Xunit;
using VoxLoom.Core.Backup;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupR2RetentionOneTests
{
    [Fact]
    public void Retention1_KeepsOnlyLatest()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));
        var backupDir = Path.Combine(root, "backups");
        var projectDir = Path.Combine(root, "project");
        try
        {
            Directory.CreateDirectory(projectDir);
            File.WriteAllText(Path.Combine(projectDir, "a.txt"), "hello world");
            Directory.CreateDirectory(backupDir);

            var manager = new BackupManager(backupDir, retentionCount: 1);

            var first = manager.CreateBackup(projectDir, "proj");
            Thread.Sleep(1100);
            var second = manager.CreateBackup(projectDir, "proj");

            Assert.NotEqual(first.Id, second.Id);

            var list = manager.ListBackups();
            Assert.Single(list);
            Assert.Equal(second.Id, list[0].Id);

            var firstZip = Path.Combine(backupDir, first.Id + ".zip");
            var firstJson = Path.Combine(backupDir, first.Id + ".json");
            Assert.False(File.Exists(firstZip));
            Assert.False(File.Exists(firstJson));

            var secondZip = Path.Combine(backupDir, second.Id + ".zip");
            var secondJson = Path.Combine(backupDir, second.Id + ".json");
            Assert.True(File.Exists(secondZip));
            Assert.True(File.Exists(secondJson));
        }
        finally
        {
            try { if (Directory.Exists(root)) Directory.Delete(root, recursive: true); } catch { }
        }
    }
}
