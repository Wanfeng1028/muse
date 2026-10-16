using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using VoxLoom.Core.Alignment;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Backup;
using VoxLoom.Core.Logging;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Logging;

[CollectionDefinition("MetricsSerial", DisableParallelization = true)]
public sealed class MetricsSerialCollection { }

[Collection("MetricsSerial")]
public class MetricsOperationsTests
{
    private static string NewTmpDir()
    {
        return Path.Combine(AppContext.BaseDirectory, "test-tmp-" + Guid.NewGuid().ToString("N")[..8]);
    }

    private static List<string> ReadMetricLines(string metricsDir)
    {
        if (!Directory.Exists(metricsDir))
            return new List<string>();

        var lines = new List<string>();
        foreach (var file in Directory.GetFiles(metricsDir, "metrics-*.jsonl"))
        {
            lines.AddRange(File.ReadAllLines(file));
        }
        return lines;
    }

    [Fact]
    public void CorruptWav_Import_ThrowsAndRecordsFailure()
    {
        var root = NewTmpDir();
        var metricsDir = Path.Combine(root, "metrics");
        Directory.CreateDirectory(metricsDir);
        VoxMetrics.Initialize(metricsDir);
        try
        {
            var wavPath = Path.Combine(root, "corrupt.wav");
            File.WriteAllBytes(wavPath, new byte[] { 0x00, 0x01, 0x02, 0x03, 0x04 });

            var ex = Assert.Throws<WavFormatException>(() => AudioImporter.Import(wavPath));
            Assert.NotNull(ex);

            var lines = ReadMetricLines(metricsDir);
            Assert.Contains(lines, l => l.Contains("\"op\":\"audio.import\"") && l.Contains("\"success\":false") && l.Contains("\"error_type\":\"WavFormatException\""));
        }
        finally
        {
            VoxMetrics.Shutdown();
            Directory.Delete(root, true);
        }
    }

    [Fact]
    public void EmptyWhisperJson_RecordsFailure()
    {
        var root = NewTmpDir();
        var metricsDir = Path.Combine(root, "metrics");
        Directory.CreateDirectory(metricsDir);
        VoxMetrics.Initialize(metricsDir);
        try
        {
            var ex = Assert.Throws<TranscriptFormatException>(() => TranscriptImporter.ParseWhisperJson(""));
            Assert.NotNull(ex);

            var lines = ReadMetricLines(metricsDir);
            Assert.Contains(lines, l => l.Contains("\"op\":\"transcript.import\"") && l.Contains("\"success\":false") && l.Contains("\"error_type\":\"TranscriptFormatException\""));
        }
        finally
        {
            VoxMetrics.Shutdown();
            Directory.Delete(root, true);
        }
    }

    [Fact]
    public void Align_RecordsSuccess()
    {
        var root = NewTmpDir();
        var metricsDir = Path.Combine(root, "metrics");
        Directory.CreateDirectory(metricsDir);
        VoxMetrics.Initialize(metricsDir);
        try
        {
            var samples = new float[16000 * 4];
            for (int i = 16000; i < 16000 * 3; i++)
                samples[i] = (float)(0.5 * Math.Sin(2 * Math.PI * 440.0 * (i - 16000) / 16000.0));
            var clip = new AudioClip(16000, 1, samples);
            var rough = new TranscriptDoc(new List<TranscriptWord>
            {
                new("你好", TimeSpan.FromSeconds(0.0), TimeSpan.FromSeconds(1.0)),
                new("世界", TimeSpan.FromSeconds(1.0), TimeSpan.FromSeconds(2.0)),
            }, TimeSpan.FromSeconds(4));

            var result = RuleBasedAligner.Refine(clip, rough);
            Assert.NotNull(result);

            var lines = ReadMetricLines(metricsDir);
            Assert.Contains(lines, l => l.Contains("\"op\":\"align\"") && l.Contains("\"success\":true"));
        }
        finally
        {
            VoxMetrics.Shutdown();
            Directory.Delete(root, true);
        }
    }

    [Fact]
    public void BackupCreate_RecordsSuccess()
    {
        var root = NewTmpDir();
        var metricsDir = Path.Combine(root, "metrics");
        Directory.CreateDirectory(metricsDir);
        VoxMetrics.Initialize(metricsDir);
        try
        {
            var backupDir = Path.Combine(root, "backups");
            var projectDir = Path.Combine(root, "project");
            Directory.CreateDirectory(backupDir);
            Directory.CreateDirectory(projectDir);
            File.WriteAllText(Path.Combine(projectDir, "project.json"), "{\"name\":\"demo\"}");

            var manager = new BackupManager(backupDir);
            var record = manager.CreateBackup(projectDir, "demo");
            Assert.NotNull(record);
            Assert.False(string.IsNullOrEmpty(record.Id));

            var lines = ReadMetricLines(metricsDir);
            Assert.Contains(lines, l => l.Contains("\"op\":\"backup.create\"") && l.Contains("\"success\":true"));
        }
        finally
        {
            VoxMetrics.Shutdown();
            Directory.Delete(root, true);
        }
    }

    [Fact]
    public void TruncatedBackup_Restore_ThrowsAndRecordsFailure()
    {
        var root = NewTmpDir();
        var metricsDir = Path.Combine(root, "metrics");
        Directory.CreateDirectory(metricsDir);
        VoxMetrics.Initialize(metricsDir);
        try
        {
            var backupDir = Path.Combine(root, "backups");
            var projectDir = Path.Combine(root, "project");
            Directory.CreateDirectory(backupDir);
            Directory.CreateDirectory(projectDir);
            File.WriteAllText(Path.Combine(projectDir, "project.json"), "{\"name\":\"demo\"}");

            var manager = new BackupManager(backupDir);
            var record = manager.CreateBackup(projectDir, "demo");
            Assert.NotNull(record);

            var zipPath = Directory.GetFiles(backupDir, "*.zip", SearchOption.AllDirectories).FirstOrDefault();
            if (zipPath == null)
            {
                var found = Directory.GetFiles(backupDir, "*", SearchOption.AllDirectories)
                    .Where(p => !Directory.Exists(p))
                    .OrderByDescending(p => new FileInfo(p).Length)
                    .FirstOrDefault();
                Assert.NotNull(found);
                zipPath = found;
            }

            var len = new FileInfo(zipPath).Length;
            using (var fs = new FileStream(zipPath, FileMode.Open))
            {
                fs.SetLength(len / 2);
            }

            var targetDir = Path.Combine(root, "restore-target");
            Directory.CreateDirectory(targetDir);

            var ex = Assert.Throws<BackupException>(() => manager.Restore(record.Id, targetDir));
            Assert.NotNull(ex);

            var lines = ReadMetricLines(metricsDir);
            Assert.Contains(lines, l => l.Contains("\"op\":\"backup.restore\"") && l.Contains("\"success\":false") && l.Contains("\"error_type\":\"BackupException\""));
        }
        finally
        {
            VoxMetrics.Shutdown();
            Directory.Delete(root, true);
        }
    }
}
