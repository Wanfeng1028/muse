using System;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupR2CorruptZipSidecarTests
{
    private static string NewTempDir()
        => Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));

    private static string ComputeSha256Lower(string path)
    {
        using var stream = File.OpenRead(path);
        using var sha = SHA256.Create();
        var hash = sha.ComputeHash(stream);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    private static void WriteProject(string dir)
    {
        Directory.CreateDirectory(dir);
        File.WriteAllText(Path.Combine(dir, "a.txt"), "hello world");
        File.WriteAllText(Path.Combine(dir, "b.txt"), "second file content");
        Directory.CreateDirectory(Path.Combine(dir, "sub"));
        File.WriteAllText(Path.Combine(dir, "sub", "c.txt"), "nested content here");
    }

    [Fact]
    public void Restore_CorruptedZipWithFixedSidecar_Throws()
    {
        var root = NewTempDir();
        var backupDir = Path.Combine(root, "backups");
        var projectDir = Path.Combine(root, "project");
        var targetDir = Path.Combine(root, "restore-target");

        try
        {
            WriteProject(projectDir);

            var manager = new BackupManager(backupDir, 10, null);
            var record = manager.CreateBackup(projectDir, "demo");

            Assert.NotNull(record);
            Assert.False(string.IsNullOrWhiteSpace(record.Id));

            var zipPath = Path.Combine(backupDir, record.Id + ".zip");
            var sidecarPath = Path.Combine(backupDir, record.Id + ".json");
            Assert.True(File.Exists(zipPath));
            Assert.True(File.Exists(sidecarPath));

            // 篡改 zip：翻转若干字节，破坏压缩流。
            var bytes = File.ReadAllBytes(zipPath);
            Assert.True(bytes.Length > 64);
            for (int i = 30; i < bytes.Length && i < 130; i++)
            {
                bytes[i] = (byte)(bytes[i] ^ 0xFF);
            }
            File.WriteAllBytes(zipPath, bytes);

            // 用篡改后文件的真实 SHA256 修正 sidecar，绕过外层校验。
            var newSha = ComputeSha256Lower(zipPath);
            var json = File.ReadAllText(sidecarPath);
            var loaded = JsonSerializer.Deserialize<BackupRecord>(json);
            Assert.NotNull(loaded);
            var fixedRecord = loaded! with { Sha256 = newSha };
            File.WriteAllText(sidecarPath,
                JsonSerializer.Serialize(fixedRecord, new JsonSerializerOptions { WriteIndented = true }));

            // 确认外层校验现在会通过（真实 SHA 一致）。
            var reloaded = JsonSerializer.Deserialize<BackupRecord>(File.ReadAllText(sidecarPath));
            Assert.NotNull(reloaded);
            Assert.Equal(newSha, reloaded!.Sha256);

            var ex = Assert.Throws<BackupException>(() => manager.Restore(record.Id, targetDir));
            Assert.False(string.IsNullOrWhiteSpace(ex.Message));
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
