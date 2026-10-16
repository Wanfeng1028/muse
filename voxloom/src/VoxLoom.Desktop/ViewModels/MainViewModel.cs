using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Desktop.ViewModels;

/// <summary>
/// 主界面视图模型：加载音频/转写、删除选中词、弱化语气词、导出音频与 EDL。
/// </summary>
public sealed partial class MainViewModel : ObservableObject
{
    private AudioClip? _clip;
    private TranscriptDoc? _doc;
    private List<TimeRange> _fillerRanges = new();
    private bool _fillersDetected;

    /// <summary>波形数据变化时触发，View 层据此刷新 WaveformView。</summary>
    public event EventHandler? WaveformInvalidated;

    public ObservableCollection<WordViewModel> Words { get; } = new();

    [ObservableProperty]
    private string _projectName = "未命名项目";

    [ObservableProperty]
    private string _statusText = "就绪：点「载入演示」或导入自己的音频开始。";

    [ObservableProperty]
    private string? _audioFilePath;

    [ObservableProperty]
    private double _audioDurationSeconds;

    [ObservableProperty]
    private int _fillerCount;

    [ObservableProperty]
    private string _tapeName = "VOXLOOM_DEMO";

    public AudioClip? CurrentClip => _clip;

    private VoxLoom.Core.Backup.BackupManager? _backupManager;
    private VoxLoom.Core.Backup.BackupManager BackupManager =>
        _backupManager ??= new VoxLoom.Core.Backup.BackupManager(
            Services.DesktopBoot.Config.BackupDirectory,
            Services.DesktopBoot.Config.BackupRetentionCount,
            Services.DesktopBoot.Logger);

    /// <summary>破坏性操作前自动备份当前项目；备份失败只记日志、不阻断编辑。</summary>
    private void AutoBackup(string reason)
    {
        if (_clip is null) return;
        try
        {
            using var op = Services.DesktopBoot.Logger.BeginOperation("auto-backup");
            var dir = StageProjectSnapshot(reason);
            var record = BackupManager.CreateBackup(dir, ProjectName);
            Services.DesktopBoot.Logger.Info("自动备份完成", new { reason, backupId = record.Id });
        }
        catch (Exception ex)
        {
            Services.DesktopBoot.Logger.Warning("自动备份失败，已跳过", new { reason }, ex);
        }
    }

    public IReadOnlyList<TimeRange> FillerRanges => _fillerRanges;

    public int SampleRate => _clip?.SampleRate ?? 44100;

    private void RaiseWaveformInvalidated() => WaveformInvalidated?.Invoke(this, EventArgs.Empty);

    public void LoadDemoProject(AudioClip clip, TranscriptDoc doc, string name = "演示项目")
    {
        _clip = clip;
        _doc = doc;
        _fillerRanges = new List<TimeRange>();
        _fillersDetected = false;
        ProjectName = name;
        AudioFilePath = null;
        AudioDurationSeconds = clip.Duration.TotalSeconds;
        FillerCount = 0;
        RefreshWords();
        StatusText = $"已载入{name}：{doc.Words.Count} 个词，{AudioDurationSeconds:F1} 秒";
        RaiseWaveformInvalidated();
    }

    [RelayCommand]
    private void LoadDemo()
    {
        var (clip, doc) = Services.DemoProjectGenerator.Generate();
        LoadDemoProject(clip, doc);
    }

    [RelayCommand]
    private async Task ImportAudioAsync()
    {
        var path = await PickOpenFileAsync("选择音频文件", AudioImporter.OpenFileFilter);
        if (string.IsNullOrEmpty(path)) return;
        AudioFormat format = AudioFormat.Wav;
        try
        {
            format = AudioImporter.DetectFormat(path);
            using var op = Services.DesktopBoot.Logger.BeginOperation("import-audio");
            Services.DesktopBoot.Logger.Info("开始导入音频", new { path, format = AudioImporter.FormatDisplayName(format) });
            var clip = await Task.Run(() => AudioImporter.Import(path));
            _clip = clip;
            _doc = null;
            _fillerRanges = new List<TimeRange>();
            _fillersDetected = false;
            Words.Clear();
            ProjectName = Path.GetFileNameWithoutExtension(path);
            AudioFilePath = path;
            AudioDurationSeconds = clip.Duration.TotalSeconds;
            FillerCount = 0;
            StatusText = $"已加载音频：{Path.GetFileName(path)}（{AudioImporter.FormatDisplayName(format)}，{AudioDurationSeconds:F1} 秒），请再导入转写稿";
            Services.DesktopBoot.Logger.Info("音频导入完成", new { path, seconds = AudioDurationSeconds });
            RaiseWaveformInvalidated();
        }
        catch (Exception ex)
        {
            Services.DesktopBoot.Logger.Error("导入音频失败", new { path }, ex);
            StatusText = $"加载音频失败：{ex.Message}";
        }
    }

    [RelayCommand]
    private async Task ImportTranscriptAsync()
    {
        var path = await PickOpenFileAsync("选择转写稿", "转写稿|*.json;*.lrc;*.txt|所有文件|*.*");
        if (string.IsNullOrEmpty(path)) return;
        try
        {
            var ext = Path.GetExtension(path).ToLowerInvariant();
            TranscriptDoc doc;
            if (ext == ".json")
            {
                doc = TranscriptImporter.ParseWhisperJson(await File.ReadAllTextAsync(path));
            }
            else if (ext == ".lrc")
            {
                doc = TranscriptImporter.ParseLrc(await File.ReadAllTextAsync(path));
            }
            else
            {
                var duration = _clip?.Duration ?? TimeSpan.FromSeconds(60);
                doc = TranscriptImporter.ParsePlainText(await File.ReadAllTextAsync(path), duration);
            }
            _doc = doc;
            _fillerRanges = new List<TimeRange>();
            _fillersDetected = false;
            FillerCount = 0;
            RefreshWords();
            StatusText = $"已加载转写稿：{Path.GetFileName(path)}（{doc.Words.Count} 个词）";
            RaiseWaveformInvalidated();
        }
        catch (Exception ex)
        {
            StatusText = $"加载转写稿失败：{ex.Message}";
        }
    }

    [RelayCommand]
    private void DeleteSelected()
    {
        if (_clip is null)
        {
            StatusText = "请先加载音频。";
            return;
        }
        var selected = Words.Where(w => w.IsSelected).ToList();
        if (selected.Count == 0)
        {
            StatusText = "先在右侧转写稿里选中要删掉的词。";
            return;
        }
        try
        {
            AutoBackup("删除前自动备份");
            var ops = selected
                .Select(w => (EditOp)new DeleteOp(new TimeRange(w.Start, w.End)))
                .ToList();
            var plan = new EditPlan(_clip, ops);
            _clip = plan.Render();
            foreach (var w in selected) Words.Remove(w);
            AudioDurationSeconds = _clip.Duration.TotalSeconds;
            var seconds = selected.Sum(w => (w.End - w.Start).TotalSeconds);
            StatusText = $"已删除 {selected.Count} 段，共 {seconds:F1} 秒（过零点拼接，无爆音）";
            RaiseWaveformInvalidated();
        }
        catch (Exception ex)
        {
            StatusText = $"删除失败：{ex.Message}";
        }
    }

    [RelayCommand]
    private void WeakenFillers()
    {
        if (_clip is null || _doc is null)
        {
            StatusText = "请先加载音频与转写稿。";
            return;
        }
        try
        {
            if (!_fillersDetected)
            {
                _fillerRanges = FillerWordDetector.Detect(_doc).ToList();
                _fillersDetected = true;
                FillerCount = _fillerRanges.Count;
                MarkFillerWords();
                StatusText = FillerCount == 0
                    ? "没检测到语气词，口播很干净。"
                    : $"检测到 {FillerCount} 处语气词（橙色标记），再点一次执行弱化";
                RaiseWaveformInvalidated();
                return;
            }

            AutoBackup("弱化语气词前自动备份");
            var ops = FillerWordDetector.ToAttenuateOps(_fillerRanges, -12f);
            _clip = new EditPlan(_clip, ops).Render();
            AudioDurationSeconds = _clip.Duration.TotalSeconds;
            StatusText = $"已弱化 {FillerCount} 处语气词（-12dB，保留呼吸节奏）";
            RaiseWaveformInvalidated();
        }
        catch (Exception ex)
        {
            StatusText = $"弱化失败：{ex.Message}";
        }
    }

    [RelayCommand]
    private async Task ExportAudioAsync()
    {
        if (_clip is null)
        {
            StatusText = "没有可导出的音频。";
            return;
        }
        var path = await PickSaveFileAsync("导出音频", "WAV 音频|*.wav|所有文件|*.*", $"{TapeName}.wav");
        if (string.IsNullOrEmpty(path)) return;
        try
        {
            await Task.Run(() => WavWriter.Write(path, _clip));
            StatusText = $"已导出音频：{Path.GetFileName(path)}";
        }
        catch (Exception ex)
        {
            StatusText = $"导出失败：{ex.Message}";
        }
    }

    [RelayCommand]
    private async Task ExportEdlAsync()
    {
        if (_doc is null || _clip is null)
        {
            StatusText = "请先加载音频与转写稿。";
            return;
        }
        var path = await PickSaveFileAsync("导出 EDL", "EDL|*.edl|所有文件|*.*", $"{TapeName}.edl");
        if (string.IsNullOrEmpty(path)) return;
        try
        {
            // 导出事件：每段语气词区间对应剪掉，保留其余部分
            var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>();
            var recordCursor = TimeSpan.Zero;
            var previousEnd = TimeSpan.Zero;
            foreach (var range in _fillerRanges.OrderBy(r => r.Start))
            {
                if (range.Start > previousEnd)
                {
                    var keep = new TimeRange(previousEnd, range.Start);
                    events.Add((keep, recordCursor));
                    recordCursor += keep.End - keep.Start;
                }
                previousEnd = range.End;
            }
            var total = _clip.Duration;
            if (total > previousEnd)
            {
                events.Add((new TimeRange(previousEnd, total), recordCursor));
            }
            var content = EdlExporter.ExportCmx3600(TapeName, events, SampleRate);
            await File.WriteAllTextAsync(path, content);
            StatusText = $"已导出 EDL：{Path.GetFileName(path)}（{events.Count} 段，可进 Premiere/Reaper 精修）";
        }
        catch (Exception ex)
        {
            StatusText = $"导出失败：{ex.Message}";
        }
    }

    [RelayCommand]
    private async Task BackupProjectAsync()
    {
        if (_clip is null)
        {
            StatusText = "没有可备份的项目，请先加载音频。";
            return;
        }
        try
        {
            using var op = Services.DesktopBoot.Logger.BeginOperation("backup-project");
            var dir = await Task.Run(() => StageProjectSnapshot("手动备份"));
            var record = await Task.Run(() => BackupManager.CreateBackup(dir, ProjectName));
            Services.DesktopBoot.Logger.Info("项目备份完成", new { backupId = record.Id, projectName = ProjectName });
            StatusText = $"已备份项目「{ProjectName}」（备份号 {record.Id}），共保留最近 {Services.DesktopBoot.Config.BackupRetentionCount} 份";
        }
        catch (Exception ex)
        {
            Services.DesktopBoot.Logger.Error("项目备份失败", new { projectName = ProjectName }, ex);
            StatusText = $"备份失败：{ex.Message}";
        }
    }

    [RelayCommand]
    private async Task RestoreProjectAsync()
    {
        var path = await PickOpenFileAsync("选择备份文件", "VoxLoom 备份|*.zip|所有文件|*.*");
        if (string.IsNullOrEmpty(path)) return;
        try
        {
            using var op = Services.DesktopBoot.Logger.BeginOperation("restore-project");
            var backupId = Path.GetFileNameWithoutExtension(path);
            var target = Path.Combine(Services.DesktopBoot.Config.ProjectsDirectory, $"restored-{backupId}");
            await Task.Run(() => BackupManager.Restore(backupId, target));
            var snapshot = await Task.Run(() => Services.ProjectSnapshot.Read(target));
            if (snapshot is null)
            {
                StatusText = "恢复完成，但快照解析失败（可能不是 VoxLoom 项目备份）。";
                return;
            }
            _clip = snapshot.Value.Clip;
            _doc = snapshot.Value.Doc;
            _fillerRanges = new List<TimeRange>();
            _fillersDetected = false;
            ProjectName = snapshot.Value.ProjectName;
            AudioFilePath = null;
            AudioDurationSeconds = _clip.Duration.TotalSeconds;
            FillerCount = 0;
            RefreshWords();
            Services.DesktopBoot.Logger.Info("项目恢复完成", new { backupId, target });
            StatusText = $"已从备份 {backupId} 恢复项目「{ProjectName}」";
            RaiseWaveformInvalidated();
        }
        catch (Exception ex)
        {
            Services.DesktopBoot.Logger.Error("项目恢复失败", new { backupPath = path }, ex);
            StatusText = $"恢复失败：{ex.Message}";
        }
    }

    /// <summary>供定时自动备份调用：有已加载项目时落盘快照并返回目录，否则返回 null（本次跳过）。</summary>
    public string? TryStageAutoBackupSnapshot()
    {
        if (_clip is null || _doc is null) return null;
        return StageProjectSnapshot("autobackup");
    }

    /// <summary>把当前内存中的项目落盘为快照目录，返回目录路径。</summary>
    private string StageProjectSnapshot(string reason)
    {
        var safeName = string.Concat(ProjectName.Select(c => char.IsLetterOrDigit(c) || c == '-' || c == '_' ? c : '_'));
        if (string.IsNullOrEmpty(safeName)) safeName = "project";
        var dir = Path.Combine(Services.DesktopBoot.Config.ProjectsDirectory, $"{safeName}-{DateTime.Now:yyyyMMdd-HHmmss}");
        Services.ProjectSnapshot.Write(dir, _clip!, _doc, ProjectName, AudioFilePath);
        Services.DesktopBoot.Logger.Info("项目快照已落盘", new { reason, dir });
        return dir;
    }

    private void MarkFillerWords()
    {
        foreach (var w in Words) w.IsFiller = false;
        foreach (var range in _fillerRanges)
        {
            foreach (var w in Words)
            {
                if (w.Start < range.End && w.End > range.Start) w.IsFiller = true;
            }
        }
    }

    private void RefreshWords()
    {
        Words.Clear();
        if (_doc is null) return;
        foreach (var w in _doc.Words) Words.Add(new WordViewModel(w));
    }

    private static Task<string?> PickOpenFileAsync(string title, string filter)
        => FileDialogService.OpenFileAsync(title, filter);

    private static Task<string?> PickSaveFileAsync(string title, string filter, string defaultName)
        => FileDialogService.SaveFileAsync(title, filter, defaultName);
}

/// <summary>
/// 文件对话框服务占位，由 View 层注入实现。
/// </summary>
public static class FileDialogService
{
    public static Func<string, string, Task<string?>>? OpenHandler { get; set; }
    public static Func<string, string, string, Task<string?>>? SaveHandler { get; set; }

    public static Task<string?> OpenFileAsync(string title, string filter)
        => OpenHandler?.Invoke(title, filter) ?? Task.FromResult<string?>(null);

    public static Task<string?> SaveFileAsync(string title, string filter, string defaultName)
        => SaveHandler?.Invoke(title, filter, defaultName) ?? Task.FromResult<string?>(null);
}
