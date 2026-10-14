using System;
using System.IO;
using System.Linq;
using System.Text;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public class BackupManagerTests
{
    private static string NewTmpDir()
    {
        var dir = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N").Substring(0, 8));
        Directory.CreateDirectory(dir);
        return dir;
    }

    private static void WriteFile(string path, string content)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, content, Encoding.UTF8);
    }

    [Fact]
    public void CreateAndRestore_RoundTrip()
    {
        var root = NewTmpDir();
        try
        {
            var src = Path.Combine(root, "project");
            var backupDir = Path.Combine(root, "backups");
            var target = Path.Combine(root, "restored");
            Directory.CreateDirectory(src);
            Directory.CreateDirectory(backupDir);

            WriteFile(Path.Combine(src, "a.txt"), "hello-a");
            WriteFile(Path.Combine(src, "sub", "中文文件.txt"), "内容-b");
            var bytesA = File.ReadAllBytes(Path.Combine(src, "a.txt"));
            var bytesB = File.ReadAllBytes(Path.Combine(src, "sub", "中文文件.txt"));

            var mgr = new BackupManager(backupDir, 10);
            var rec = mgr.CreateBackup(src, "proj1");

            Assert.False(string.IsNullOrEmpty(rec.Id));
            Assert.False(string.IsNullOrEmpty(rec.Sha256));
            Assert.True(File.Exists(Path.Combine(backupDir, rec.Id + ".zip")));
            Assert.True(File.Exists(Path.Combine(backupDir, rec.Id + ".json")));

            Directory.Delete(src, true);
            Assert.False(Directory.Exists(src));

            mgr.Restore(rec.Id, target);

            var restoredA = File.ReadAllBytes(Path.Combine(target, "a.txt"));
            var restoredB = File.ReadAllBytes(Path.Combine(target, "sub", "中文文件.txt"));
            Assert.Equal(bytesA, restoredA);
            Assert.Equal(bytesB, restoredB);
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }

    [Fact]
    public void Restore_TamperedZip_Throws()
    {
        var root = NewTmpDir();
        try
        {
            var src = Path.Combine(root, "project");
            var backupDir = Path.Combine(root, "backups");
            var target = Path.Combine(root, "restored");
            Directory.CreateDirectory(src);
            Directory.CreateDirectory(backupDir);
            WriteFile(Path.Combine(src, "a.txt"), "hello-a");

            var mgr = new BackupManager(backupDir, 10);
            var rec = mgr.CreateBackup(src, "proj1");

            var zipPath = Path.Combine(backupDir, rec.Id + ".zip");
            var info = new FileInfo(zipPath);
            Assert.True(info.Length > 20);
            using (var fs = new FileStream(zipPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            {
                fs.Seek(info.Length / 2, SeekOrigin.Begin);
                int b = fs.ReadByte();
                fs.Seek(info.Length / 2, SeekOrigin.Begin);
                fs.WriteByte((byte)(b ^ 0xFF));
            }

            var ex = Assert.Throws<BackupException>(() => mgr.Restore(rec.Id, target));
            Assert.Contains("校验", ex.Message);
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }

    [Fact]
    public void Restore_NonEmptyTarget_Throws()
    {
        var root = NewTmpDir();
        try
        {
            var src = Path.Combine(root, "project");
            var backupDir = Path.Combine(root, "backups");
            var target = Path.Combine(root, "restored");
            Directory.CreateDirectory(src);
            Directory.CreateDirectory(backupDir);
            WriteFile(Path.Combine(src, "a.txt"), "hello-a");

            var mgr = new BackupManager(backupDir, 10);
            var rec = mgr.CreateBackup(src, "proj1");

            Directory.CreateDirectory(target);
            WriteFile(Path.Combine(target, "existing.txt"), "occupied");

            Assert.Throws<BackupException>(() => mgr.Restore(rec.Id, target));
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }

    [Fact]
    public void Restore_MissingBackup_Throws()
    {
        var root = NewTmpDir();
        try
        {
            var backupDir = Path.Combine(root, "backups");
            var target = Path.Combine(root, "restored");
            Directory.CreateDirectory(backupDir);
            var mgr = new BackupManager(backupDir, 10);
            Assert.Throws<BackupException>(() => mgr.Restore("not-exist-id", target));
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }

    [Fact]
    public void Retention_Enforced()
    {
        var root = NewTmpDir();
        try
        {
            var backupDir = Path.Combine(root, "backups");
            Directory.CreateDirectory(backupDir);
            var mgr = new BackupManager(backupDir, 2);

            var firstId = "";
            for (int i = 0; i < 3; i++)
            {
                var src = Path.Combine(root, "proj" + i);
                WriteFile(Path.Combine(src, "f.txt"), "content-" + i);
                var rec = mgr.CreateBackup(src, "proj" + i);
                if (i == 0) firstId = rec.Id;
            }

            var list = mgr.ListBackups();
            Assert.Equal(2, list.Count);
            Assert.False(File.Exists(Path.Combine(backupDir, firstId + ".zip")),
                "oldest zip should have been deleted");
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }

    [Fact]
    public void ListBackups_Empty_ReturnsEmpty()
    {
        var root = NewTmpDir();
        try
        {
            var backupDir = Path.Combine(root, "backups");
            Directory.CreateDirectory(backupDir);
            var mgr = new BackupManager(backupDir, 10);
            var list = mgr.ListBackups();
            Assert.NotNull(list);
            Assert.Empty(list);
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }

    [Fact]
    public void CreateBackup_MissingDir_Throws()
    {
        var root = NewTmpDir();
        try
        {
            var backupDir = Path.Combine(root, "backups");
            Directory.CreateDirectory(backupDir);
            var missing = Path.Combine(root, "no-such-project");
            var mgr = new BackupManager(backupDir, 10);
            Assert.Throws<BackupException>(() => mgr.CreateBackup(missing, "projX"));
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }
}
