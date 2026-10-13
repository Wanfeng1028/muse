using Avalonia;
using System;
using System.Linq;
using VoxLoom.Desktop.Services;
using VoxLoom.Desktop.ViewModels;
using VoxLoom.Desktop.Views;

namespace VoxLoom.Desktop;

internal sealed class Program
{
    // 初始化代码，在 AppMain 之前不要使用任何 Avalonia、第三方 API 或任何依赖 SynchronizationContext 的代码
    [STAThread]
    public static void Main(string[] args)
    {
        if (args.Contains("--screenshot"))
        {
            RunScreenshotMode(args);
            return;
        }
        if (args.Contains("--demo-wav"))
        {
            RunDemoGenMode(args);
            return;
        }
        BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
    }

    /// <summary>
    /// 截图模式：启动真实窗口（含演示数据），待渲染完成后抓屏，用于视觉验收。
    /// 用法：VoxLoom.Desktop --screenshot /path/out.png（需在 Xvfb 下运行）
    /// </summary>
    private static void RunScreenshotMode(string[] args)
    {
        var idx = Array.IndexOf(args, "--screenshot");
        if (idx < 0 || idx + 1 >= args.Length)
        {
            Console.Error.WriteLine("用法：--screenshot <输出png路径>");
            Environment.Exit(2);
        }
        App.ScreenshotOutputPath = args[idx + 1];
        BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
    }

    /// <summary>
    /// 演示数据生成模式。
    /// 用法：VoxLoom.Desktop --demo-wav /path/a.wav --demo-transcript /path/t.lrc
    /// </summary>
    private static void RunDemoGenMode(string[] args)
    {
        string? wav = ArgValue(args, "--demo-wav");
        string? lrc = ArgValue(args, "--demo-transcript");
        if (wav is null)
        {
            Console.Error.WriteLine("用法：--demo-wav <输出wav路径> [--demo-transcript <输出lrc路径>]");
            Environment.Exit(2);
        }
        DemoProjectGenerator.WriteFiles(wav, lrc);
        Console.WriteLine($"演示数据已生成：{wav}" + (lrc is null ? "" : $" / {lrc}"));
    }

    private static string? ArgValue(string[] args, string name)
    {
        var idx = Array.IndexOf(args, name);
        return idx >= 0 && idx + 1 < args.Length ? args[idx + 1] : null;
    }

    // Avalonia 配置，供可视化设计器与测试使用
    public static AppBuilder BuildAvaloniaApp()
        => AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .LogToTrace();
}
