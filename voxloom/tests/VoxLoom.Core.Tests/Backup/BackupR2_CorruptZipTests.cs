using System;
using System.IO;
using System.Security.Cryptography;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupR2CorruptZipTests
{
    [Fact]
    public void Restore_CorruptedZipBytes_ThrowsChecksumError()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));
        var backupDir = Path.Combine(root, "backups");
        var projectDir = Path.Combine(root, "project");
        var targetDir = Path.Combine(root, "restore-target");

        try
        {
            Directory.CreateDirectory(backupDir);
            Directory.CreateDirectory(projectDir);
            File.WriteAllText(Path.Combine(projectDir, "a.txt"), "hello");

            var mgr = new BackupManager(backupDir, 10);
            var rec = mgr.CreateBackup(projectDir, "proj");

            Assert.True(File.Exists(Path.Combine(backupDir, rec.Id + ".zip")));
            Assert.True(File.Exists(Path.Combine(backupDir, rec.Id + ".json")));

            var zipPath = Path.Combine(backupDir, rec.Id + ".zip");
            var bytes = File.ReadAllBytes(zipPath);
            Assert.True(bytes.Length > 40, "备份文件太小，无法执行篡改");

            var mid = bytes.Length / 2;
            var start = mid - 10;
            for (int i = start; i < start + 20; i++)
            {
                bytes[i] = (byte)~bytes[i];
            }
            File.WriteAllBytes(zipPath, bytes);

            var ex = Assert.Throws<BackupException>(() => mgr.Restore(rec.Id, targetDir));
            Assert.Contains("校验", ex.Message);
        }
        finally
        {
            try
            {
                if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
            }
            catch { }
        }
    }
}
