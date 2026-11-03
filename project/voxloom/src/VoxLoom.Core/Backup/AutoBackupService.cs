
using System;
using System.Threading;
using VoxLoom.Core.Logging;

namespace VoxLoom.Core.Backup;

/// <summary>
/// 自动备份服务配置项。
/// </summary>
public sealed class AutoBackupOptions
{
    /// <summary>
    /// 是否启用自动备份，默认启用。为 false 时 <see cref="AutoBackupService.Start"/> 直接返回。
    /// </summary>
    public bool Enabled { get; set; } = true;

    /// <summary>
    /// 备份间隔分钟数，默认 60。有效范围 1~1440，构造或 Start 时会校验，非法值抛 <see cref="BackupException"/>。
    /// </summary>
    public int IntervalMinutes { get; set; } = 60;

    /// <summary>
    /// 备份密码，可为空。仅由调用方从环境变量读取后传入，本服务不读取配置文件、不记录日志。
    /// </summary>
    public string? Password { get; set; }
}

/// <summary>
/// 定时自动备份服务：按固定周期触发备份，成功/失败通过事件与日志通知，异常绝不抛给定时器回调或调用方。
/// </summary>
public sealed class AutoBackupService : IDisposable
{
    private const int MinIntervalMinutes = 1;
    private const int MaxIntervalMinutes = 1440;
    private const string OperationName = "autobackup";

    private readonly AutoBackupOptions _options;
    private readonly Func<string?> _projectDirectoryProvider;
    private readonly Func<string?> _projectNameProvider;
    private readonly Func<string, string, string?, BackupRecord> _backupFunc;
    private readonly VoxLogger? _logger;

    private readonly object _syncRoot = new();
    private Timer? _timer;
    private bool _started;
    private bool _disposed;

    /// <summary>
    /// 备份成功完成时触发，参数为本次备份产生的 <see cref="BackupRecord"/>。事件在定时器线程上触发，订阅方需自行处理线程问题。
    /// </summary>
    public event EventHandler<BackupRecord>? BackupCompleted;

    /// <summary>
    /// 备份失败时触发，参数为导致失败的异常。事件在定时器线程上触发，订阅方需自行处理线程问题。
    /// </summary>
    public event EventHandler<Exception>? BackupFailed;

    /// <summary>
    /// 构造自动备份服务。
    /// </summary>
    /// <param name="options">配置项，不可为 null。</param>
    /// <param name="projectDirectoryProvider">返回当前项目目录的委托；返回 null 或空字符串时本次备份跳过（记 debug 日志，不算失败）。</param>
    /// <param name="projectNameProvider">返回当前项目名称的委托；返回 null 或空字符串时本次备份跳过（记 debug 日志，不算失败）。</param>
    /// <param name="backupFunc">执行备份的委托，签名与 <see cref="BackupManager.CreateBackup(string, string, string?)"/> 一致。</param>
    /// <param name="logger">可选日志器，为 null 时静默处理日志。</param>
    /// <exception cref="BackupException">参数为 null 或间隔分钟数不在 1~1440 范围内。</exception>
    public AutoBackupService(
        AutoBackupOptions options,
        Func<string?> projectDirectoryProvider,
        Func<string?> projectNameProvider,
        Func<string, string, string?, BackupRecord> backupFunc,
        VoxLogger? logger = null)
    {
        _options = options ?? throw new BackupException("自动备份配置不能为 null。");
        _projectDirectoryProvider = projectDirectoryProvider ?? throw new BackupException("项目目录提供委托不能为 null。");
        _projectNameProvider = projectNameProvider ?? throw new BackupException("项目名称提供委托不能为 null。");
        _backupFunc = backupFunc ?? throw new BackupException("备份执行委托不能为 null。");
        _logger = logger;

        ValidateInterval(_options.IntervalMinutes);
    }

    /// <summary>
    /// 启动自动备份定时器。
    /// 若 <see cref="AutoBackupOptions.Enabled"/> 为 false，则记录 info 日志并直接返回，不启动定时器。
    /// 重复调用（未 Stop 或 Dispose 前）会抛 <see cref="InvalidOperationException"/>。
    /// </summary>
    /// <exception cref="BackupException">间隔分钟数不在 1~1440 范围内。</exception>
    /// <exception cref="InvalidOperationException">服务已启动或已释放。</exception>
    public void Start()
    {
        lock (_syncRoot)
        {
            if (_disposed)
            {
                throw new InvalidOperationException("自动备份服务已释放，无法启动。");
            }

            if (_started)
            {
                throw new InvalidOperationException("自动备份服务已启动，请勿重复 Start。");
            }

            if (!_options.Enabled)
            {
                _logger?.Info("自动备份已禁用");
                _started = true;
                return;
            }

            ValidateInterval(_options.IntervalMinutes);

            var interval = TimeSpan.FromMinutes(_options.IntervalMinutes);
            _timer = new Timer(OnTimerTick, null, interval, interval);
            _started = true;
        }
    }

    /// <summary>
    /// 停止自动备份定时器并释放其资源。未 Start 时无操作。可重复调用。
    /// Stop 之后定时器不会再触发回调。
    /// </summary>
    public void Stop()
    {
        lock (_syncRoot)
        {
            if (_timer != null)
            {
                _timer.Dispose();
                _timer = null;
            }

            _started = false;
        }
    }

    /// <summary>
    /// 释放服务：停止并释放定时器。可重复调用。
    /// </summary>
    public void Dispose()
    {
        lock (_syncRoot)
        {
            if (_disposed)
            {
                return;
            }

            _disposed = true;
        }

        Stop();
    }

    private void OnTimerTick(object? state)
    {
        try
        {
            using var _ = _logger?.BeginOperation(OperationName);

            string? directory;
            string? projectName;

            try
            {
                directory = _projectDirectoryProvider();
                projectName = _projectNameProvider();
            }
            catch (Exception ex)
            {
                _logger?.Error("获取项目信息失败，本次自动备份跳过。", ex);
                RaiseBackupFailed(ex);
                return;
            }

            if (string.IsNullOrWhiteSpace(directory) || string.IsNullOrWhiteSpace(projectName))
            {
                _logger?.Debug("项目目录或名称为空，本次自动备份跳过。");
                return;
            }

            BackupRecord record;
            try
            {
                record = _backupFunc(directory!, projectName!, _options.Password);
            }
            catch (Exception ex)
            {
                _logger?.Error("自动备份执行失败。", ex);
                RaiseBackupFailed(ex);
                return;
            }

            if (record == null)
            {
                var ex = new BackupException("自动备份返回了空的备份记录。");
                _logger?.Error("自动备份返回了空的备份记录。", ex);
                RaiseBackupFailed(ex);
                return;
            }

            _logger?.Info("自动备份已完成。");
            RaiseBackupCompleted(record);
        }
        catch (Exception ex)
        {
            // 兜底：任何未预料的异常都必须在此吞下，绝不抛回 Timer。
            try
            {
                _logger?.Error("自动备份回调发生未预期异常。", ex);
            }
            catch
            {
                // 日志本身失败也不再向上抛。
            }

            RaiseBackupFailed(ex);
        }
    }

    private void RaiseBackupCompleted(BackupRecord record)
    {
        try
        {
            BackupCompleted?.Invoke(this, record);
        }
        catch (Exception ex)
        {
            try
            {
                _logger?.Error("BackupCompleted 事件订阅方抛出异常。", ex);
            }
            catch
            {
                // 忽略日志异常。
            }
        }
    }

    private void RaiseBackupFailed(Exception ex)
    {
        try
        {
            BackupFailed?.Invoke(this, ex);
        }
        catch (Exception handlerEx)
        {
            try
            {
                _logger?.Error("BackupFailed 事件订阅方抛出异常。", handlerEx);
            }
            catch
            {
                // 忽略日志异常。
            }
        }
    }

    private static void ValidateInterval(int intervalMinutes)
    {
        if (intervalMinutes < MinIntervalMinutes || intervalMinutes > MaxIntervalMinutes)
        {
            throw new BackupException(
                $"自动备份间隔必须在 {MinIntervalMinutes}~{MaxIntervalMinutes} 分钟之间，当前值：{intervalMinutes}。");
        }
    }
}
