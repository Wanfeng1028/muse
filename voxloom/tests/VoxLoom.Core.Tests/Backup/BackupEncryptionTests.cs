using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupEncryptionTests
{
    private static string NewTmpDir()
    {
        var dir = Path.Combine(Path.GetTempPath(), "voxloom-tests-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(dir);
        return dir;
    }

    private static void WriteFile(string path, string content)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, content);
    }

    [Fact]
    public void EncryptedRoundTrip_RestoresIdenticalBytes()
    {
        var root = NewTmpDir();
        var src = NewTmpDir();
        var backupDir = NewTmpDir();
        var restoreDir = Path.Combine(root, "restore");
        try
        {
            var bytesA = Encoding.UTF8.GetBytes("hello 中文内容 A");
            var bytesB = new byte[] { 1, 2, 3, 4, 5, 250, 128, 0, 77 };
            File.WriteAllBytes(Path.Combine(src, "文件一.txt"), bytesA);
            WriteFile(Path.Combine(src, "sub", "b.bin"), "placeholder");
            File.WriteAllBytes(Path.Combine(src, "sub", "b.bin"), bytesB);

            var mgr = new BackupManager(backupDir);
            var rec = mgr.CreateBackup(src, "proj", "correct-horse-123");
            Assert.True(rec.Encrypted);

            var mgr2 = new BackupManager(backupDir);
            mgr2.Restore(rec.Id, restoreDir, "correct-horse-123");

            var outA = File.ReadAllBytes(Path.Combine(restoreDir, "文件一.txt"));
            var outB = File.ReadAllBytes(Path.Combine(restoreDir, "sub", "b.bin"));
            Assert.Equal(bytesA, outA);
            Assert.Equal(bytesB, outB);
        }
        finally
        {
            TryDelete(root);
            TryDelete(src);
            TryDelete(backupDir);
        }
    }

    [Fact]
    public void Restore_WithWrongPassword_ThrowsHonestError()
    {
        var root = NewTmpDir();
        var src = NewTmpDir();
        var backupDir = NewTmpDir();
        try
        {
            WriteFile(Path.Combine(src, "a.txt"), "data");
            var mgr = new BackupManager(backupDir);
            var rec = mgr.CreateBackup(src, "proj", "correct-horse-123");

            var mgr2 = new BackupManager(backupDir);
            var ex = Assert.Throws<BackupException>(() =>
                mgr2.Restore(rec.Id, Path.Combine(root, "restore"), "wrong-password"));
            Assert.Contains("密码错误", ex.Message);
        }
        finally
        {
            TryDelete(root);
            TryDelete(src);
            TryDelete(backupDir);
        }
    }

    [Fact]
    public void RestoreEncrypted_WithoutPassword_Throws()
    {
        var root = NewTmpDir();
        var src = NewTmpDir();
        var backupDir = NewTmpDir();
        try
        {
            WriteFile(Path.Combine(src, "a.txt"), "data");
            var mgr = new BackupManager(backupDir);
            var rec = mgr.CreateBackup(src, "proj", "correct-horse-123");

            var mgr2 = new BackupManager(backupDir);
            var ex = Assert.Throws<BackupException>(() =>
                mgr2.Restore(rec.Id, Path.Combine(root, "restore")));
            Assert.Contains("需要密码", ex.Message);
        }
        finally
        {
            TryDelete(root);
            TryDelete(src);
            TryDelete(backupDir);
        }
    }

    [Fact]
    public void NoPassword_KeepsLegacyZipFormat()
    {
        var root = NewTmpDir();
        var src = NewTmpDir();
        var backupDir = NewTmpDir();
        var restoreDir = Path.Combine(root, "restore");
        try
        {
            WriteFile(Path.Combine(src, "a.txt"), "legacy");
            var mgr = new BackupManager(backupDir);
            var rec = mgr.CreateBackup(src, "proj");

            var zipPath = Path.Combine(backupDir, rec.Id + ".zip");
            using (var fs = File.OpenRead(zipPath))
            {
                var b0 = fs.ReadByte();
                var b1 = fs.ReadByte();
                Assert.Equal((int)'P', b0);
                Assert.Equal((int)'K', b1);
            }

            var mgr2 = new BackupManager(backupDir);
            mgr2.Restore(rec.Id, restoreDir);
            Assert.True(File.Exists(Path.Combine(restoreDir, "a.txt")));
        }
        finally
        {
            TryDelete(root);
            TryDelete(src);
            TryDelete(backupDir);
        }
    }

    [Fact]
    public void EmptyPassword_Rejected()
    {
        var src = NewTmpDir();
        var backupDir = NewTmpDir();
        try
        {
            WriteFile(Path.Combine(src, "a.txt"), "data");
            var mgr = new BackupManager(backupDir);
            var ex = Assert.Throws<BackupException>(() => mgr.CreateBackup(src, "proj", ""));
            Assert.Contains("密码不能为空", ex.Message);
        }
        finally
        {
            TryDelete(src);
            TryDelete(backupDir);
        }
    }

    [Fact]
    public void EncryptedFile_MarkedAndNotPlainZip()
    {
        var src = NewTmpDir();
        var backupDir = NewTmpDir();
        try
        {
            WriteFile(Path.Combine(src, "a.txt"), "data");
            var mgr = new BackupManager(backupDir);
            var rec = mgr.CreateBackup(src, "proj", "correct-horse-123");

            var zipPath = Path.Combine(backupDir, rec.Id + ".zip");
            var header = new byte[6];
            using (var fs = File.OpenRead(zipPath))
            {
                var read = fs.Read(header, 0, 6);
                Assert.Equal(6, read);
            }
            Assert.Equal("VXENC1", Encoding.ASCII.GetString(header));

            var sidecarPath = Path.Combine(backupDir, rec.Id + ".json");
            var recBack = JsonSerializer.Deserialize<BackupRecord>(File.ReadAllText(sidecarPath));
            Assert.NotNull(recBack);
            Assert.True(recBack!.Encrypted);

            var legacyJson = "{\"Id\":\"20200101-000000-abc\",\"CreatedUtc\":\"2020-01-01T00:00:00Z\",\"FileName\":\"20200101-000000-abc.zip\",\"SizeBytes\":123,\"Sha256\":\"deadbeef\"}";
            var legacy = JsonSerializer.Deserialize<BackupRecord>(legacyJson);
            Assert.NotNull(legacy);
            Assert.False(legacy!.Encrypted);
        }
        finally
        {
            TryDelete(src);
            TryDelete(backupDir);
        }
    }

    private static void TryDelete(string dir)
    {
        try
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, recursive: true);
        }
        catch { }
    }
}
