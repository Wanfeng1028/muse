using System;
using System.IO;
using System.Linq;
using Xunit;
using VoxLoom.Core.Backup;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupR2RetentionTests
{
    [Fact]
    public void Retention2_KeepsLatestTwo()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));
        var backupDir = Path.Combine(root, "backups");
        var projectDir = Path.Combine(root, "project");
        Directory.CreateDirectory(backupDir);
        Directory.CreateDirectory(projectDir);
        File.WriteAllText(Path.Combine(projectDir, "a.txt"), "hello voxloom");

        try
        {
            var manager = new BackupManager(backupDir, retentionCount: 2);

            var rec1 = manager.CreateBackup(projectDir, "proj");
            var rec2 = manager.CreateBackup(projectDir, "proj");
            var rec3 = manager.CreateBackup(projectDir, "proj");

            var list = manager.ListBackups();
            Assert.Equal(2, list.Count);

            var ids = list.Select(r => r.Id).OrderBy(x => x, StringComparer.Ordinal).ToList();
            var expected = new[] { rec2.Id, rec3.Id }.OrderBy(x => x, StringComparer.Ordinal).ToList();
            Assert.Equal(expected, ids);

            Assert.DoesNotContain(rec1.Id, ids);
            Assert.Contains(rec2.Id, ids);
            Assert.Contains(rec3.Id, ids);

            var zipCount = Directory.GetFiles(backupDir, "*.zip").Length;
            Assert.Equal(2, zipCount);
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }
}
