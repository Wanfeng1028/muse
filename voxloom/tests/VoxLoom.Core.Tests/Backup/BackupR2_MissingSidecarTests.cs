using System;
using System.IO;
using System.Text.Json;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupR2MissingSidecarTests
{
    [Fact]
    public void Restore_MissingSidecar_StillRestores()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));
        var projectDir = Path.Combine(root, "project");
        var backupDir = Path.Combine(root, "backups");
        var targetDir = Path.Combine(root, "restored");
        try
        {
            Directory.CreateDirectory(projectDir);
            File.WriteAllText(Path.Combine(projectDir, "a.txt"), "hello-sidecar");

            var manager = new BackupManager(backupDir, retentionCount: 10);
            var record = manager.CreateBackup(projectDir, "侧车测试项目");

            Assert.Equal("hello-sidecar", File.ReadAllText(Path.Combine(projectDir, "a.txt")));
            Assert.True(File.Exists(Path.Combine(backupDir, record.Id + ".json")));
            Assert.True(File.Exists(Path.Combine(backupDir, record.Id + ".zip")));

            File.Delete(Path.Combine(backupDir, record.Id + ".json"));
            Assert.False(File.Exists(Path.Combine(backupDir, record.Id + ".json")));

            manager.Restore(record.Id, targetDir);

            var restoredFile = Path.Combine(targetDir, "a.txt");
            Assert.True(File.Exists(restoredFile));
            Assert.Equal("hello-sidecar", File.ReadAllText(restoredFile));
        }
        finally
        {
            if (Directory.Exists(root))
            {
                try { Directory.Delete(root, recursive: true); } catch { }
            }
        }
    }
}
