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
        var path = await PickOpenFileAsync("选择音频文件", "WAV 音频|*.wav|所有文件|*.*");
        if (string.IsNullOrEmpty(path)) return;
        try
        {
            var clip = await Task.Run(() => WavReader.Read(path));
            _clip = clip;
            _doc = null;
            _fillerRanges = new List<TimeRange>();
            _fillersDetected = false;
            Words.Clear();
            ProjectName = Path.GetFileNameWithoutExtension(path);
            AudioFilePath = path;
            AudioDurationSeconds = clip.Duration.TotalSeconds;
            FillerCount = 0;
            StatusText = $"已加载音频：{Path.GetFileName(path)}（{AudioDurationSeconds:F1} 秒），请再导入转写稿";
            RaiseWaveformInvalidated();
        }
        catch (Exception ex)
        {
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
