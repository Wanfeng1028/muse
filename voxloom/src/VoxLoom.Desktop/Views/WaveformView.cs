using System;
using System.Collections.Generic;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Desktop.Views;

/// <summary>
/// 简易波形绘制控件：根据 AudioClip 采样数据绘制峰值包络。
/// </summary>
public sealed class WaveformView : Control
{
    private AudioClip? _clip;
    private IReadOnlyList<TimeRange> _highlights = Array.Empty<TimeRange>();

    public static readonly StyledProperty<IBrush?> WaveBrushProperty =
        AvaloniaProperty.Register<WaveformView, IBrush?>(nameof(WaveBrush));

    public static readonly StyledProperty<IBrush?> HighlightBrushProperty =
        AvaloniaProperty.Register<WaveformView, IBrush?>(nameof(HighlightBrush));

    public IBrush? WaveBrush
    {
        get => GetValue(WaveBrushProperty);
        set => SetValue(WaveBrushProperty, value);
    }

    public IBrush? HighlightBrush
    {
        get => GetValue(HighlightBrushProperty);
        set => SetValue(HighlightBrushProperty, value);
    }

    public WaveformView()
    {
        // 录音棚配色（见 docs/SOUL.md）：深板岩底 + 纸色波形 + 橙色高亮
        WaveBrush = new SolidColorBrush(Color.Parse("#EDE6D6"));
        HighlightBrush = new SolidColorBrush(Color.Parse("#E8833A"));
    }

    /// <summary>设置要绘制的音频数据。</summary>
    public void SetClip(AudioClip? clip)
    {
        _clip = clip;
        InvalidateVisual();
    }

    /// <summary>设置高亮时间区间（例如需静音的气口）。</summary>
    public void SetHighlights(IReadOnlyList<TimeRange> ranges)
    {
        _highlights = ranges ?? Array.Empty<TimeRange>();
        InvalidateVisual();
    }

    private static readonly Color BgColor = Color.Parse("#1C1A17");
    private static readonly Color GridColor = Color.Parse("#3A342C");
    private static readonly Color WaveColor = Color.Parse("#EDE6D6");
    private static readonly Color HighlightColor = Color.Parse("#E8833A");

    public override void Render(DrawingContext context)
    {
        base.Render(context);

        var bounds = new Rect(Bounds.Size);
        context.FillRectangle(new SolidColorBrush(BgColor), bounds);

        var width = bounds.Width;
        var height = bounds.Height;
        if (width <= 0 || height <= 0) return;

        var midY = height / 2.0;

        // 中线
        context.DrawLine(new Pen(new SolidColorBrush(GridColor), 1),
            new Point(0, midY), new Point(width, midY));

        if (_clip is null || _clip.Samples.Length == 0 || _clip.SampleRate <= 0)
        {
            return;
        }

        var samples = _clip.Samples;
        var sampleRate = _clip.SampleRate;
        var totalSeconds = samples.Length / (double)sampleRate;

        // 高亮区间：半透明橙色带
        if (_highlights.Count > 0 && totalSeconds > 0)
        {
            var bandBrush = new SolidColorBrush(HighlightColor, 0.22);
            var edgePen = new Pen(new SolidColorBrush(HighlightColor), 1);
            foreach (var range in _highlights)
            {
                var x1 = range.Start.TotalSeconds / totalSeconds * width;
                var x2 = range.End.TotalSeconds / totalSeconds * width;
                if (x2 < x1) (x1, x2) = (x2, x1);
                context.FillRectangle(bandBrush, new Rect(x1, 0, Math.Max(2, x2 - x1), height));
                context.DrawLine(edgePen, new Point(x1, 0), new Point(x1, height));
                context.DrawLine(edgePen, new Point(x2, 0), new Point(x2, height));
            }
        }

        // 波形：逐像素列峰值
        var waveBrush = WaveBrush as SolidColorBrush ?? new SolidColorBrush(WaveColor);
        var pen = new Pen(waveBrush, 1);
        var columns = (int)Math.Max(1, width);
        var samplesPerColumn = Math.Max(1, samples.Length / columns);
        for (var x = 0; x < columns; x++)
        {
            var startIdx = x * samplesPerColumn;
            var endIdx = Math.Min(samples.Length, startIdx + samplesPerColumn);
            float peak = 0;
            for (var i = startIdx; i < endIdx; i++)
            {
                var v = Math.Abs(samples[i]);
                if (v > peak) peak = v;
            }
            var h = Math.Min(midY - 1, peak * midY);
            if (h < 0.5) continue;
            context.DrawLine(pen, new Point(x, midY - h), new Point(x, midY + h));
        }
    }
}
