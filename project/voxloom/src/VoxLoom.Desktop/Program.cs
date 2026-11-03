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
        Services.DesktopBoot.Initialize(args);
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
        if (args.Contains("--metrics"))
        {
            RunMetricsMode(args);
            return;
        }
        if (args.Contains("--probe-import"))
        {
            RunProbeImport(args);
            return;
        }
        if (args.Contains("--probe-backup"))
        {
            RunProbeBackup(args);
            return;
        }
        if (args.Contains("--probe-restore"))
        {
            RunProbeRestore(args);
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

    /// <summary>
    /// 指标汇总模式：聚合日志目录下 metrics-*.jsonl（默认近 24 小时），打印各操作次数/失败数/成功率/平均延迟。
    /// 用法：VoxLoom.Desktop --metrics [--json] [--hours N]
    /// </summary>
    private static void RunMetricsMode(string[] args)
    {
        var dir = Services.DesktopBoot.Config.LogDirectory;
        double hours = 24;
        var h = ArgValue(args, "--hours");
        if (h is not null && double.TryParse(h, out var parsed) && parsed > 0) hours = parsed;
        var since = DateTime.UtcNow.AddHours(-hours);
        var summaries = VoxLoom.Core.Logging.VoxMetrics.ReadSummary(dir, since);
        if (args.Contains("--json"))
        {
            Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(summaries,
                new System.Text.Json.JsonSerializerOptions { WriteIndented = true }));
            return;
        }
        Console.WriteLine($"指标汇总（近 {hours:g} 小时，目录：{dir}）");
        Console.WriteLine($"{"操作",-16}{"次数",6}{"失败",6}{"成功率",8}{"平均延迟",10}");
        if (summaries.Count == 0)
        {
            Console.WriteLine("暂无指标数据。");
            return;
        }
        foreach (var s in summaries)
        {
            Console.WriteLine($"{s.Op,-16}{s.Count,6}{s.Failures,6}{s.SuccessRate * 100,7:F1}%{s.AvgMs,9:F1}ms");
        }
    }

    private static string? ArgValue(string[] args, string name)
    {
        var idx = Array.IndexOf(args, name);
        return idx >= 0 && idx + 1 < args.Length ? args[idx + 1] : null;
    }

    /// <summary>
    /// 运维探针：导入单个音频文件，验证 Core 的格式探测与导入管线是否可用。
    /// 用法：--probe-import &lt;音频文件路径&gt;。
    /// 缺参数退出码 2；成功打印 OK 行；异常退出码 3。
    /// </summary>
    private static void RunProbeImport(string[] args)
    {
        var path = ArgValue(args, "--probe-import");
        if (string.IsNullOrEmpty(path))
        {
            Console.Error.WriteLine("用法：--probe-import <音频文件路径>");
            Environment.Exit(2);
            return;
        }

        try
        {
            var format = VoxLoom.Core.Audio.AudioImporter.DetectFormat(path);
            var clip = VoxLoom.Core.Audio.AudioImporter.Import(path);
            var formatName = VoxLoom.Core.Audio.AudioImporter.FormatDisplayName(format);
            Console.Out.WriteLine(
                $"OK: 导入成功：{path}（{formatName}，{clip.Duration.TotalSeconds:F1} 秒）");
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"ERROR: {ex.Message}");
            Environment.Exit(3);
        }
    }

    /// <summary>
    /// 运维探针：对指定项目目录创建一次备份，验证 BackupManager 的创建路径与保留策略。
    /// 用法：--probe-backup &lt;项目目录&gt; &lt;项目名&gt;。
    /// 密码只从环境变量 VOXLOOM_BACKUP_PASSWORD 读取，不提供任何命令行密码参数。
    /// 缺参数退出码 2；成功打印 OK 行；异常退出码 3。
    /// </summary>
    private static void RunProbeBackup(string[] args)
    {
        var idx = Array.IndexOf(args, "--probe-backup");
        var dir = idx >= 0 && idx + 1 < args.Length ? args[idx + 1] : null;
        var name = idx >= 0 && idx + 2 < args.Length ? args[idx + 2] : null;
        if (string.IsNullOrEmpty(dir) || string.IsNullOrEmpty(name))
        {
            Console.Error.WriteLine("用法：--probe-backup <项目目录> <项目名>");
            Environment.Exit(2);
            return;
        }

        try
        {
            var cfg = Services.DesktopBoot.Config;
            var password = Environment.GetEnvironmentVariable("VOXLOOM_BACKUP_PASSWORD");
            if (string.IsNullOrEmpty(password))
            {
                password = null;
            }

            var manager = new VoxLoom.Core.Backup.BackupManager(
                cfg.BackupDirectory,
                cfg.BackupRetentionCount,
                Services.DesktopBoot.Logger);

            var record = manager.CreateBackup(dir, name, password);
            Console.Out.WriteLine($"OK: {record.Id}（{record.SizeBytes} 字节）");
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"ERROR: {ex.Message}");
            Environment.Exit(3);
        }
    }

    /// <summary>
    /// 运维探针：从备份 Id 恢复到目标目录，验证 BackupManager 的恢复路径。
    /// 用法：--probe-restore &lt;backupId&gt; &lt;目标目录&gt;。
    /// 密码只从环境变量 VOXLOOM_BACKUP_PASSWORD 读取，不提供任何命令行密码参数。
    /// 缺参数退出码 2；成功打印 OK 行；异常退出码 3。
    /// </summary>
    private static void RunProbeRestore(string[] args)
    {
        var idx = Array.IndexOf(args, "--probe-restore");
        var backupId = idx >= 0 && idx + 1 < args.Length ? args[idx + 1] : null;
        var target = idx >= 0 && idx + 2 < args.Length ? args[idx + 2] : null;
        if (string.IsNullOrEmpty(backupId) || string.IsNullOrEmpty(target))
        {
            Console.Error.WriteLine("用法：--probe-restore <backupId> <目标目录>");
            Environment.Exit(2);
            return;
        }

        try
        {
            var cfg = Services.DesktopBoot.Config;
            var password = Environment.GetEnvironmentVariable("VOXLOOM_BACKUP_PASSWORD");
            if (string.IsNullOrEmpty(password))
            {
                password = null;
            }

            var manager = new VoxLoom.Core.Backup.BackupManager(
                cfg.BackupDirectory,
                cfg.BackupRetentionCount,
                Services.DesktopBoot.Logger);

            manager.Restore(backupId, target, password);
            Console.Out.WriteLine($"OK: 已恢复 {backupId} 到 {target}");
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"ERROR: {ex.Message}");
            Environment.Exit(3);
        }
    }

    // Avalonia 配置，供可视化设计器与测试使用
    public static AppBuilder BuildAvaloniaApp()
        => AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .LogToTrace();
}
