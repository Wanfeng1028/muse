using System.Text;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public class BackupRestorePreviewTests
{
    private static string NewTmpDir()
    {
        var dir = Path.Combine(Path.GetTempPath(), "voxloom-test-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(dir);
        return dir;
    }

    private static void WriteFile(string path, string content)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, content, new UTF8Encoding(false));
    }

    [Fact]
    public void ListBackupContents_ReturnsEntriesWithSizeAndTime()
    {
        var proj = NewTmpDir();
        var backups = NewTmpDir();
        var target = Path.Combine(NewTmpDir(), "out");
        try
        {
            var aPath = Path.Combine(proj, "a.txt");
            WriteFile(aPath, "hello a");
            var cnRel = "子目录/中文文件.txt";
            var cnFull = Path.Combine(proj, "子目录", "中文文件.txt");
            WriteFile(cnFull, "中文内容-hello");
            var aLen = new FileInfo(aPath).Length;
            var cnLen = new FileInfo(cnFull).Length;

            var mgr = new BackupManager(backups);
            var rec = mgr.CreateBackup(proj, "proj");

            var entries = mgr.ListBackupContents(rec.Id);
            Assert.NotEmpty(entries);

            var a = entries.Single(e => e.Path == "a.txt");
            Assert.Equal(aLen, a.SizeBytes);
            Assert.True(a.SizeBytes > 0);

            var cn = entries.Single(e => e.Path == "子目录/中文文件.txt");
            Assert.Equal(cnLen, cn.SizeBytes);
            Assert.True(cn.SizeBytes > 0);

            Assert.All(entries, e => Assert.True(e.ModifiedUtc > new DateTime(2020, 1, 1, 0, 0, 0, DateTimeKind.Utc)));

            var sorted = entries.OrderBy(e => e.Path, StringComparer.Ordinal).ToList();
            Assert.Equal(sorted.Select(e => e.Path), entries.Select(e => e.Path));
        }
        finally
        {
            try { if (Directory.Exists(proj)) Directory.Delete(proj, true); } catch { }
            try { if (Directory.Exists(backups)) Directory.Delete(backups, true); } catch { }
            try { if (Directory.Exists(target)) Directory.Delete(target, true); } catch { }
        }
    }

    [Fact]
    public void ListBackupContents_EncryptedRequiresPassword()
    {
        var proj = NewTmpDir();
        var backups = NewTmpDir();
        try
        {
            WriteFile(Path.Combine(proj, "a.txt"), "secret");
            var mgr = new BackupManager(backups);
            var rec = mgr.CreateBackup(proj, "proj", "pw123");

            var ex1 = Assert.Throws<BackupException>(() => mgr.ListBackupContents(rec.Id));
            Assert.Contains("需要密码", ex1.Message);

            var entries = mgr.ListBackupContents(rec.Id, "pw123");
            Assert.NotEmpty(entries);

            var ex2 = Assert.Throws<BackupException>(() => mgr.ListBackupContents(rec.Id, "wrong"));
            Assert.Contains("密码错误", ex2.Message);
        }
        finally
        {
            try { if (Directory.Exists(proj)) Directory.Delete(proj, true); } catch { }
            try { if (Directory.Exists(backups)) Directory.Delete(backups, true); } catch { }
        }
    }

    [Fact]
    public void RestoreWithPreview_PrintsListingAndRestores()
    {
        var proj = NewTmpDir();
        var backups = NewTmpDir();
        var target = Path.Combine(NewTmpDir(), "out");
        try
        {
            var bytes = Encoding.UTF8.GetBytes("preview-content");
            File.WriteAllBytes(Path.Combine(proj, "a.txt"), bytes);

            var mgr = new BackupManager(backups);
            var rec = mgr.CreateBackup(proj, "proj");

            var sw = new StringWriter();
            var options = new RestorePreviewOptions
            {
                Output = sw,
                Confirmer = _ => true
            };
            mgr.RestoreWithPreview(rec.Id, target, options);

            var restored = File.ReadAllBytes(Path.Combine(target, "a.txt"));
            Assert.Equal(bytes, restored);

            var text = sw.ToString();
            Assert.Contains("a.txt", text);
            Assert.Contains("确认恢复", text);
        }
        finally
        {
            try { if (Directory.Exists(proj)) Directory.Delete(proj, true); } catch { }
            try { if (Directory.Exists(backups)) Directory.Delete(backups, true); } catch { }
            try { if (Directory.Exists(target)) Directory.Delete(target, true); } catch { }
        }
    }

    [Fact]
    public void RestoreWithPreview_Declined_AbortsWithoutRestore()
    {
        var proj = NewTmpDir();
        var backups = NewTmpDir();
        var target = Path.Combine(NewTmpDir(), "out");
        try
        {
            WriteFile(Path.Combine(proj, "a.txt"), "data");
            var mgr = new BackupManager(backups);
            var rec = mgr.CreateBackup(proj, "proj");

            var sw = new StringWriter();
            var options = new RestorePreviewOptions
            {
                Output = sw,
                Confirmer = _ => false
            };

            var ex = Assert.Throws<BackupException>(() => mgr.RestoreWithPreview(rec.Id, target, options));
            Assert.Contains("取消", ex.Message);
            Assert.False(Directory.Exists(target));
        }
        finally
        {
            try { if (Directory.Exists(proj)) Directory.Delete(proj, true); } catch { }
            try { if (Directory.Exists(backups)) Directory.Delete(backups, true); } catch { }
            try { if (Directory.Exists(target)) Directory.Delete(target, true); } catch { }
        }
    }

    [Fact]
    public void RestoreWithPreview_AutoConfirm_SkipsPrompt()
    {
        var proj = NewTmpDir();
        var backups = NewTmpDir();
        var target = Path.Combine(NewTmpDir(), "out");
        try
        {
            var bytes = Encoding.UTF8.GetBytes("auto");
            File.WriteAllBytes(Path.Combine(proj, "a.txt"), bytes);

            var mgr = new BackupManager(backups);
            var rec = mgr.CreateBackup(proj, "proj");

            var sw = new StringWriter();
            var options = new RestorePreviewOptions
            {
                Output = sw,
                AutoConfirm = true,
                Confirmer = _ => throw new Exception("must not be called")
            };

            mgr.RestoreWithPreview(rec.Id, target, options);

            var restored = File.ReadAllBytes(Path.Combine(target, "a.txt"));
            Assert.Equal(bytes, restored);
        }
        finally
        {
            try { if (Directory.Exists(proj)) Directory.Delete(proj, true); } catch { }
            try { if (Directory.Exists(backups)) Directory.Delete(backups, true); } catch { }
            try { if (Directory.Exists(target)) Directory.Delete(target, true); } catch { }
        }
    }
}
