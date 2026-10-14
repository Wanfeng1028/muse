using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using VoxLoom.Core.Logging;

namespace VoxLoom.Core.Backup;

public sealed class BackupException : Exception
{
    public BackupException(string message) : base(message) { }
    public BackupException(string message, Exception inner) : base(message, inner) { }
}

public sealed record BackupRecord(string Id, DateTime CreatedUtc, string FileName, long SizeBytes, string Sha256);

public sealed class BackupManager
{
    private readonly string _backupDirectory;
    private readonly int _retentionCount;
    private readonly VoxLogger? _logger;

    public BackupManager(string backupDirectory, int retentionCount = 10, VoxLogger? logger = null)
    {
        if (string.IsNullOrWhiteSpace(backupDirectory))
            throw new ArgumentException("备份目录不能为空", nameof(backupDirectory));
        _backupDirectory = backupDirectory;
        _retentionCount = retentionCount < 1 ? 1 : retentionCount;
        _logger = logger;
        Directory.CreateDirectory(_backupDirectory);
    }

    public BackupRecord CreateBackup(string projectDirectory, string projectName)
    {
        if (!Directory.Exists(projectDirectory))
            throw new BackupException($"项目目录不存在：{projectDirectory}");
        if (string.IsNullOrWhiteSpace(projectName))
            throw new BackupException("项目名称不能为空");

        var id = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N")[..6];
        var staging = Path.Combine(Path.GetTempPath(), "voxloom-backup-" + id);
        var zipPath = Path.Combine(_backupDirectory, id + ".zip");
        var sidecarPath = Path.Combine(_backupDirectory, id + ".json");

        using var op = _logger?.BeginOperation("backup");

        try
        {
            CopyDirectory(projectDirectory, staging);

            var files = new List<(string rel, string full)>();
            CollectFiles(staging, staging, files);

            var manifestFiles = new List<object>();
            foreach (var (rel, full) in files)
            {
                var sha = ComputeSha256(full);
                var bytes = new FileInfo(full).Length;
                manifestFiles.Add(new
                {
                    path = rel.Replace('\\', '/'),
                    sha256 = sha,
                    bytes
                });
            }

            var version = Assembly.GetExecutingAssembly().GetName().Version?.ToString() ?? "0.0.0";
            var manifest = new
            {
                format = "voxloom-backup/1",
                id,
                projectName,
                createdUtc = DateTime.UtcNow.ToString("o"),
                voxloomVersion = version,
                files = manifestFiles
            };
            var manifestJson = JsonSerializer.Serialize(manifest, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(Path.Combine(staging, "manifest.json"), manifestJson);

            if (File.Exists(zipPath)) File.Delete(zipPath);
            ZipFile.CreateFromDirectory(staging, zipPath, CompressionLevel.Optimal, includeBaseDirectory: false);

            var zipSha = ComputeSha256(zipPath);
            var zipBytes = new FileInfo(zipPath).Length;
            var record = new BackupRecord(id, DateTime.UtcNow, id + ".zip", zipBytes, zipSha);
            File.WriteAllText(sidecarPath,
                JsonSerializer.Serialize(record, new JsonSerializerOptions { WriteIndented = true }));

            EnforceRetention();
            _logger?.Info("备份完成", new { backupId = id, projectName, bytes = zipBytes });
            return record;
        }
        catch (BackupException) { throw; }
        catch (Exception ex)
        {
            throw new BackupException($"创建备份失败：{ex.Message}", ex);
        }
        finally
        {
            TryDeleteDirectory(staging);
        }
    }

    public IReadOnlyList<BackupRecord> ListBackups()
    {
        var list = new List<BackupRecord>();
        if (!Directory.Exists(_backupDirectory)) return list;

        foreach (var f in Directory.GetFiles(_backupDirectory, "*.json"))
        {
            try
            {
                var json = File.ReadAllText(f);
                var rec = JsonSerializer.Deserialize<BackupRecord>(json);
                if (rec is null || string.IsNullOrEmpty(rec.Id))
                {
                    _logger?.Warning("备份记录缺少必要字段，已跳过", new { file = f });
                    continue;
                }
                list.Add(rec);
            }
            catch (Exception ex)
            {
                _logger?.Warning("备份记录解析失败，已跳过", new { file = f }, ex);
            }
        }
        return list.OrderByDescending(r => r.CreatedUtc).ToList();
    }

    public void Restore(string backupId, string targetDirectory)
    {
        if (string.IsNullOrWhiteSpace(backupId))
            throw new BackupException("备份编号不能为空");

        var zipPath = Path.Combine(_backupDirectory, backupId + ".zip");
        var sidecarPath = Path.Combine(_backupDirectory, backupId + ".json");
        if (!File.Exists(zipPath))
            throw new BackupException($"备份文件不存在：{zipPath}");

        BackupRecord? rec = null;
        if (File.Exists(sidecarPath))
        {
            try { rec = JsonSerializer.Deserialize<BackupRecord>(File.ReadAllText(sidecarPath)); }
            catch { rec = null; }
        }

        if (rec is not null)
        {
            var actualSha = ComputeSha256(zipPath);
            if (!string.Equals(actualSha, rec.Sha256, StringComparison.OrdinalIgnoreCase))
                throw new BackupException("备份文件校验失败，可能已损坏");
        }

        var temp = Path.Combine(Path.GetTempPath(), "voxloom-restore-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(temp);

        try
        {
            ExtractZipSafe(zipPath, temp);

            var manifestPath = Path.Combine(temp, "manifest.json");
            if (File.Exists(manifestPath))
            {
                var manifestJson = File.ReadAllText(manifestPath);
                using var mdoc = JsonDocument.Parse(manifestJson);
                if (mdoc.RootElement.TryGetProperty("files", out var filesEl) &&
                    filesEl.ValueKind == JsonValueKind.Array)
                {
                    foreach (var f in filesEl.EnumerateArray())
                    {
                        var rel = f.GetProperty("path").GetString();
                        var expectSha = f.GetProperty("sha256").GetString();
                        if (string.IsNullOrEmpty(rel) || string.IsNullOrEmpty(expectSha)) continue;
                        var full = Path.Combine(temp, rel.Replace('/', Path.DirectorySeparatorChar));
                        if (!File.Exists(full))
                            throw new BackupException($"备份内容缺失文件：{rel}");
                        var actual = ComputeSha256(full);
                        if (!string.Equals(actual, expectSha, StringComparison.OrdinalIgnoreCase))
                            throw new BackupException($"备份内容校验失败：{rel}");
                    }
                }
            }

            if (Directory.Exists(targetDirectory) &&
                Directory.EnumerateFileSystemEntries(targetDirectory).Any())
            {
                throw new BackupException($"目标目录非空：{targetDirectory}");
            }

            var parent = Path.GetDirectoryName(Path.GetFullPath(targetDirectory));
            if (!string.IsNullOrEmpty(parent)) Directory.CreateDirectory(parent);

            if (Directory.Exists(targetDirectory)) Directory.Delete(targetDirectory);

            try
            {
                Directory.Move(temp, targetDirectory);
            }
            catch
            {
                CopyDirectory(temp, targetDirectory);
                TryDeleteDirectory(temp);
            }

            _logger?.Info("恢复完成", new { backupId, targetDirectory });
        }
        catch (BackupException) { throw; }
        catch (Exception ex)
        {
            throw new BackupException($"恢复备份失败：{ex.Message}", ex);
        }
        finally
        {
            TryDeleteDirectory(temp);
        }
    }

    public void DeleteBackup(string backupId)
    {
        if (string.IsNullOrWhiteSpace(backupId))
            throw new BackupException("备份编号不能为空");
        var zipPath = Path.Combine(_backupDirectory, backupId + ".zip");
        var sidecarPath = Path.Combine(_backupDirectory, backupId + ".json");
        if (!File.Exists(zipPath) && !File.Exists(sidecarPath))
            throw new BackupException($"备份不存在：{backupId}");
        try
        {
            if (File.Exists(zipPath)) File.Delete(zipPath);
            if (File.Exists(sidecarPath)) File.Delete(sidecarPath);
        }
        catch (Exception ex)
        {
            throw new BackupException($"删除备份失败：{ex.Message}", ex);
        }
    }

    private void EnforceRetention()
    {
        try
        {
            var records = ListBackups();
            for (int i = _retentionCount; i < records.Count; i++)
            {
                try
                {
                    var r = records[i];
                    var zip = Path.Combine(_backupDirectory, r.Id + ".zip");
                    var json = Path.Combine(_backupDirectory, r.Id + ".json");
                    if (File.Exists(zip)) File.Delete(zip);
                    if (File.Exists(json)) File.Delete(json);
                }
                catch (Exception ex)
                {
                    _logger?.Warning("清理旧备份失败，已跳过", new { backupId = records[i].Id }, ex);
                }
            }
        }
        catch (Exception ex)
        {
            _logger?.Warning("清理旧备份整体失败", null, ex);
        }
    }

    private static void ExtractZipSafe(string zipPath, string targetDir)
    {
        var targetFull = Path.GetFullPath(targetDir);
        if (!targetFull.EndsWith(Path.DirectorySeparatorChar))
            targetFull += Path.DirectorySeparatorChar;

        using var archive = ZipFile.OpenRead(zipPath);
        foreach (var entry in archive.Entries)
        {
            var rel = entry.FullName;
            if (string.IsNullOrEmpty(rel)) continue;
            if (Path.IsPathRooted(rel))
                throw new BackupException($"备份包含非法绝对路径条目：{rel}");
            if (rel.Split('/', '\\').Any(part => part == ".."))
                throw new BackupException($"备份包含非法路径条目：{rel}");

            var dest = Path.GetFullPath(Path.Combine(targetFull, rel));
            if (!dest.StartsWith(targetFull, StringComparison.Ordinal))
                throw new BackupException($"备份条目越界：{rel}");

            if (string.IsNullOrEmpty(entry.Name))
            {
                Directory.CreateDirectory(dest);
                continue;
            }
            Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
            entry.ExtractToFile(dest, overwrite: true);
        }
    }

    private static void CollectFiles(string root, string current, List<(string, string)> acc)
    {
        foreach (var f in Directory.GetFiles(current))
        {
            var rel = Path.GetRelativePath(root, f);
            acc.Add((rel, f));
        }
        foreach (var d in Directory.GetDirectories(current))
        {
            CollectFiles(root, d, acc);
        }
    }

    private static void CopyDirectory(string source, string target)
    {
        Directory.CreateDirectory(target);
        foreach (var f in Directory.GetFiles(source))
        {
            var dest = Path.Combine(target, Path.GetFileName(f));
            File.Copy(f, dest, overwrite: true);
        }
        foreach (var d in Directory.GetDirectories(source))
        {
            CopyDirectory(d, Path.Combine(target, Path.GetFileName(d)));
        }
    }

    private static string ComputeSha256(string path)
    {
        using var stream = File.OpenRead(path);
        using var sha = SHA256.Create();
        var hash = sha.ComputeHash(stream);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    private static void TryDeleteDirectory(string dir)
    {
        try
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, recursive: true);
        }
        catch { }
    }
}
