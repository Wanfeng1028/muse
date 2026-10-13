using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Avalonia.Threading;
using System;
using System.Threading.Tasks;
using VoxLoom.Desktop.Services;
using VoxLoom.Desktop.ViewModels;
using VoxLoom.Desktop.Views;

namespace VoxLoom.Desktop;

public partial class App : Application
{
    /// <summary>截图模式输出路径（Program --screenshot 传入）。</summary>
    public static string? ScreenshotOutputPath { get; set; }

    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var vm = new MainViewModel();
            var window = new MainWindow
            {
                DataContext = vm,
                Width = 1600,
                Height = 900,
            };

            if (ScreenshotOutputPath is string shotPath)
            {
                // 截图模式：载入演示数据，窗口渲染完成后抓屏并退出
                var (clip, doc) = DemoProjectGenerator.Generate();
                vm.LoadDemoProject(clip, doc);
                window.Opened += async (_, _) =>
                {
                    await Task.Delay(1200);
                    await Dispatcher.UIThread.InvokeAsync(() =>
                    {
                        ScreenshotService.SaveWindowPng(window, shotPath, 1600, 900);
                        Console.WriteLine($"截图已保存：{shotPath}");
                    });
                    desktop.Shutdown();
                };
            }

            desktop.MainWindow = window;
        }

        base.OnFrameworkInitializationCompleted();
    }
}
