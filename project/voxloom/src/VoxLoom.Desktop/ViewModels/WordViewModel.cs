using System;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Desktop.ViewModels;

/// <summary>
/// 单词条目视图模型，包装 TranscriptWord 供 UI 绑定。
/// </summary>
public sealed class WordViewModel
{
    public string Text { get; }
    public TimeSpan Start { get; }
    public TimeSpan End { get; }
    public float Confidence { get; }

    /// <summary>起始秒数（用于波形定位）。</summary>
    public double StartSeconds => Start.TotalSeconds;

    /// <summary>结束秒数（用于波形定位）。</summary>
    public double EndSeconds => End.TotalSeconds;

    /// <summary>时间标签，如 00:03.2–00:04.1。</summary>
    public string TimeLabel => $"{Start:mm\\:ss\\.f}–{End:mm\\:ss\\.f}";

    public bool IsFiller { get; set; }

    public bool IsSelected { get; set; }

    public WordViewModel(TranscriptWord word)
    {
        Text = word.Text;
        Start = word.Start;
        End = word.End;
        Confidence = word.Confidence;
    }
}
