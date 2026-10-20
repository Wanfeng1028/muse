using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using VoxLoom.Core.Backup;
using Xunit;

namespace VoxLoom.Core.Tests.Backup;

public sealed class BackupR2ZipSlipTests
{
    [Fact]
    public void Restore_ZipSlipEntry_Rejected()
    {
        var backupDir = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));
        var targetParent = Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N"));
        var target = Path.Combine(targetParent, "restore-target");
        Directory.CreateDirectory(backupDir);
        Directory.CreateDirectory(targetParent);

        try
        {
            var zipPath = Path.Combine(backupDir, "evil1.zip");

            using (var fs = new FileStream(zipPath, FileMode.Create, FileAccess.Write))
            using (var archive = new ZipArchive(fs, ZipArchiveMode.Create))
            {
                var manifestEntry = archive.CreateEntry("manifest.json");
                using (var ms = manifestEntry.Open())
                {
                    var bytes = Encoding.UTF8.GetBytes("{\"files\":[]}");
                    ms.Write(bytes, 0, bytes.Length);
                }

                var evilEntry = archive.CreateEntry("../evil.txt");
                using (var es = evilEntry.Open())
                {
                    var bytes = Encoding.UTF8.GetBytes("pwned");
                    es.Write(bytes, 0, bytes.Length);
                }
            }

            var zipBytes = new FileInfo(zipPath).Length;
            string sha;
            using (var stream = File.OpenRead(zipPath))
            using (var sha256 = SHA256.Create())
            {
                var hash = sha256.ComputeHash(stream);
                sha = Convert.ToHexString(hash).ToLowerInvariant();
            }

            var sidecarPath = Path.Combine(backupDir, "evil1.json");
            var recordJson = "{" +
                "\"Id\":\"evil1\"," +
                "\"CreatedUtc\":\"" + DateTime.UtcNow.ToString("o") + "\"," +
                "\"FileName\":\"evil1.zip\"," +
                "\"SizeBytes\":" + zipBytes + "," +
                "\"Sha256\":\"" + sha + "\"," +
                "\"Encrypted\":false" +
                "}";
            File.WriteAllText(sidecarPath, recordJson);

            var mgr = new BackupManager(backupDir);

            var ex = Assert.Throws<BackupException>(() => mgr.Restore("evil1", target));
            Assert.Contains("非法", ex.Message);

            var escapedPath = Path.Combine(targetParent, "evil.txt");
            Assert.False(File.Exists(escapedPath));
            Assert.False(File.Exists(target));
        }
        finally
        {
            if (Directory.Exists(backupDir)) Directory.Delete(backupDir, recursive: true);
            if (Directory.Exists(targetParent)) Directory.Delete(targetParent, recursive: true);
        }
    }
}
