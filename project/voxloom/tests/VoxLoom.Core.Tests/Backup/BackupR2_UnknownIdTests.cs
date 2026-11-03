using System;
using System.IO;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public class BackupR2UnknownIdTests
{
    [Fact]
    public void Restore_UnknownId_Throws()
    {
        var backupDir = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));
        var targetDir = Path.Combine(backupDir, "restore-target");
        try
        {
            var mgr = new BackupManager(backupDir);
            var ex = Assert.Throws<BackupException>(() => mgr.Restore("no-such-id", targetDir));
            Assert.Contains("不存在", ex.Message);
        }
        finally
        {
            if (Directory.Exists(backupDir))
            {
                Directory.Delete(backupDir, recursive: true);
            }
        }
    }
}
