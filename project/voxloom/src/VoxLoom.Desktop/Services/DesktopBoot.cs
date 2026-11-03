using VoxLoom.Core.Config;
using VoxLoom.Core.Logging;

namespace VoxLoom.Desktop.Services;

public static class DesktopBoot
{
    public static AppConfig Config { get; private set; } = null!;
    public static VoxLogger Logger { get; private set; } = null!;
    private static bool _initialized;

    public static void Initialize(string[] args)
    {
        if (_initialized) return;
        _initialized = true;

        AppConfig config;
        try
        {
            config = AppConfig.Load();
            config.Validate();
        }
        catch (ConfigValidationException ex)
        {
            Console.Error.WriteLine($"配置校验失败，启动中止：{ex.Message}");
            Environment.Exit(2);
            return;
        }

        Config = config;
        Logger = VoxLogger.Create(config.LogDirectory);
        VoxMetrics.Initialize(config.LogDirectory);
        Logger.Info("VoxLoom 启动", new { version = typeof(DesktopBoot).Assembly.GetName().Version?.ToString() });

        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            try { Logger.Fatal("未处理异常导致进程退出", null, e.ExceptionObject as Exception); } catch { }
        };
    }
}
