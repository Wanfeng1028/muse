using System;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Markup.Xaml;
using VoxLoom.Desktop.ViewModels;

namespace VoxLoom.Desktop.Views;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        // 注：Avalonia.Generators 源码生成器需要 Roslyn 4.14，
        // 本机 .NET 8 SDK 自带 Roslyn 4.11，生成器无法加载，
        // 故用运行时 XAML 加载代替编译期 InitializeComponent。
        AvaloniaXamlLoader.Load(this);

        DataContextChanged += (_, _) => AttachViewModel();
        Opened += (_, _) => AttachViewModel();
    }

    private MainViewModel? _attached;

    private void AttachViewModel()
    {
        if (DataContext is not MainViewModel vm) return;
        if (ReferenceEquals(_attached, vm)) return;

        if (_attached is not null)
        {
            _attached.WaveformInvalidated -= OnWaveformInvalidated;
        }

        _attached = vm;
        _attached.WaveformInvalidated += OnWaveformInvalidated;

        var list = this.FindControl<ListBox>("WordList");
        if (list is not null)
        {
            list.SelectionChanged += OnWordListSelectionChanged;
            list.AddHandler(PointerReleasedEvent, OnWordListPointerReleased, Avalonia.Interactivity.RoutingStrategies.Tunnel);
        }

        // 首次挂载即刷新一次波形
        OnWaveformInvalidated(this, EventArgs.Empty);
    }

    private void OnWordListSelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (sender is not ListBox list || DataContext is not MainViewModel vm) return;
        var selected = new HashSet<WordViewModel>(list.SelectedItems.OfType<WordViewModel>());
        foreach (var w in vm.Words) w.IsSelected = selected.Contains(w);
    }

    private void OnWordListPointerReleased(object? sender, PointerReleasedEventArgs e)
    {
        if (sender is not ListBox list) return;
        if (list.SelectedItem is WordViewModel word && DataContext is MainViewModel vm)
        {
            vm.StatusText = $"词「{word.Text}」 {word.TimeLabel}";
        }
    }

    private void OnWaveformInvalidated(object? sender, EventArgs e)
    {
        if (DataContext is not MainViewModel vm) return;
        var waveform = this.FindControl<WaveformView>("Waveform");
        if (waveform is null) return;
        waveform.SetClip(vm.CurrentClip);
        waveform.SetHighlights(vm.FillerRanges);
        waveform.InvalidateVisual();
    }
}
