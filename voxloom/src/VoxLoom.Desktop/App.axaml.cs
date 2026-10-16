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

    /// <summary>定时自动备份服务（v2）。</summary>
    private VoxLoom.Core.Backup.AutoBackupService? _autoBackup;


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

            // 定时自动备份（v2）：独立 BackupManager（backups/auto 子目录 + 独立保留份数）；
            // 快照由 MainViewModel.TryStageAutoBackupSnapshot 按需落盘，未加载项目时跳过。
            var autoCfg = Services.DesktopBoot.Config;
            var autoManager = new VoxLoom.Core.Backup.BackupManager(
                System.IO.Path.Combine(autoCfg.BackupDirectory, "auto"),
                autoCfg.AutoBackupRetentionCount,
                Services.DesktopBoot.Logger);
            _autoBackup = new VoxLoom.Core.Backup.AutoBackupService(
                new VoxLoom.Core.Backup.AutoBackupOptions
                {
                    Enabled = autoCfg.AutoBackupEnabled,
                    IntervalMinutes = autoCfg.AutoBackupIntervalMinutes,
                    Password = System.Environment.GetEnvironmentVariable("VOXLOOM_AUTOBACKUP_PASSWORD"),
                },
                () => vm.TryStageAutoBackupSnapshot(),
                () => vm.ProjectName,
                (dir, name, pwd) => autoManager.CreateBackup(dir, name, pwd),
                Services.DesktopBoot.Logger);
            _autoBackup.BackupCompleted += (_, record) =>
                Services.DesktopBoot.Logger.Info("定时自动备份完成", new { backupId = record.Id });
            _autoBackup.BackupFailed += (_, ex) =>
                Services.DesktopBoot.Logger.Error("定时自动备份失败", null, ex);
            _autoBackup.Start();
            desktop.Exit += (_, _) => _autoBackup?.Stop();
        }

        base.OnFrameworkInitializationCompleted();

    }
}
