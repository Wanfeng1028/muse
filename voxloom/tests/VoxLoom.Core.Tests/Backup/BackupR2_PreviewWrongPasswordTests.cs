using System;
using System.IO;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupR2PreviewWrongPasswordTests
{
    [Fact]
    public void RestoreWithPreview_WrongPassword_Throws()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));
        var backupDir = Path.Combine(root, "backups");
        var projectDir = Path.Combine(root, "project");
        var targetDir = Path.Combine(root, "target");
        try
        {
            Directory.CreateDirectory(root);
            Directory.CreateDirectory(projectDir);
            File.WriteAllText(Path.Combine(projectDir, "a.txt"), "hello voxloom");

            var manager = new BackupManager(backupDir);
            var record = manager.CreateBackup(projectDir, "proj", "correct-pw");

            var options = new RestorePreviewOptions
            {
                Password = "wrong-pw",
                AutoConfirm = true,
                Output = new StringWriter()
            };

            Assert.Throws<BackupException>(() =>
                manager.RestoreWithPreview(record.Id, targetDir, options));
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }
}
