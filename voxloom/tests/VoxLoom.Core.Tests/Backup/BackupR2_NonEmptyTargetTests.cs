using System;
using System.IO;
using System.Text.Json;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupR2NonEmptyTargetTests
{
    [Fact]
    public void Restore_NonEmptyTarget_Throws()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));
        var backupDir = Path.Combine(root, "backups");
        var projectDir = Path.Combine(root, "project");
        var targetDir = Path.Combine(root, "target");
        try
        {
            Directory.CreateDirectory(root);
            Directory.CreateDirectory(projectDir);
            File.WriteAllText(Path.Combine(projectDir, "a.txt"), "hello");
            Directory.CreateDirectory(targetDir);
            File.WriteAllText(Path.Combine(targetDir, "existing.txt"), "existing");

            var manager = new BackupManager(backupDir);
            var record = manager.CreateBackup(projectDir, "demo");

            var ex = Assert.Throws<BackupException>(
                () => manager.Restore(record.Id, targetDir));
            Assert.Contains("非空", ex.Message);
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }
}
