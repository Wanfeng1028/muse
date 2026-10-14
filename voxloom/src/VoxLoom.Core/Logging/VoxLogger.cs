using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace VoxLoom.Core.Logging;

public enum VoxLogLevel { Trace, Debug, Info, Warning, Error, Fatal }

public sealed class VoxLoggerOptions
{
    public VoxLogLevel MinLevel { get; set; } = VoxLogLevel.Info;
    public long MaxFileBytes { get; set; } = 5 * 1024 * 1024;
    public int MaxRetainedFiles { get; set; } = 10;
    public bool WriteToConsole { get; set; } = true;
}

public sealed class VoxLogger : IDisposable
{
    private static readonly string[] SecretKeyTokens =
    {
        "password", "passwd", "secret", "token", "apikey", "api_key", "api-key", "auth", "credential"
    };

    private readonly object _lock = new();
    private readonly VoxLoggerOptions _options;
    private readonly string _logDirectory;
    private readonly string _baseName;
    private StreamWriter? _writer;
    private long _currentBytes;
    private bool _disposed;

    private static readonly AsyncLocal<OperationState?> _current = new();

    private sealed class OperationState
    {
        public string? Id;
        public string? Name;
        public OperationState? Parent;
    }

    private VoxLogger(string logDirectory, VoxLoggerOptions options)
    {
        _logDirectory = logDirectory;
        _options = options;
        _baseName = $"voxloom-{DateTime.Now:yyyyMMdd}.log";
        OpenAppend();
    }

    public static VoxLogger Create(string logDirectory, VoxLoggerOptions? options = null)
    {
        if (string.IsNullOrWhiteSpace(logDirectory))
            throw new ArgumentException("日志目录不能为空", nameof(logDirectory));
        try
        {
            Directory.CreateDirectory(logDirectory);
        }
        catch (Exception ex)
        {
            throw new IOException($"创建日志目录失败：{logDirectory}", ex);
        }
        return new VoxLogger(logDirectory, options ?? new VoxLoggerOptions());
    }

    public string? CurrentOperationId => _current.Value?.Id;
    public string? CurrentOperation => _current.Value?.Name;

    public IDisposable BeginOperation(string operationName)
    {
        var state = new OperationState
        {
            Id = Guid.NewGuid().ToString("N")[..8],
            Name = operationName,
            Parent = _current.Value
        };
        _current.Value = state;
        return new OperationScope(this, state);
    }

    private sealed class OperationScope : IDisposable
    {
        private readonly VoxLogger _owner;
        private readonly OperationState _state;
        private bool _disposed;
        public OperationScope(VoxLogger owner, OperationState state) { _owner = owner; _state = state; }
        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            _current.Value = _state.Parent;
        }
    }

    public void Trace(string message, object? data = null, Exception? ex = null) => Log(VoxLogLevel.Trace, message, data, ex);
    public void Debug(string message, object? data = null, Exception? ex = null) => Log(VoxLogLevel.Debug, message, data, ex);
    public void Info(string message, object? data = null, Exception? ex = null) => Log(VoxLogLevel.Info, message, data, ex);
    public void Warning(string message, object? data = null, Exception? ex = null) => Log(VoxLogLevel.Warning, message, data, ex);
    public void Error(string message, object? data = null, Exception? ex = null) => Log(VoxLogLevel.Error, message, data, ex);
    public void Fatal(string message, object? data = null, Exception? ex = null) => Log(VoxLogLevel.Fatal, message, data, ex);

    public void Log(VoxLogLevel level, string message, object? data = null, Exception? ex = null)
    {
        try
        {
            if (level < _options.MinLevel) return;
            var line = BuildLine(level, message, data, ex);
            lock (_lock)
            {
                if (_disposed) return;
                RotateIfNeeded();
                _writer!.WriteLine(line);
                _writer.Flush();
                _currentBytes += Encoding.UTF8.GetByteCount(line) + 1;
            }
            if (_options.WriteToConsole)
            {
                try { Console.Out.WriteLine(line); } catch { }
            }
        }
        catch (Exception inner)
        {
            try { Console.Error.WriteLine($"日志写入失败（已忽略）：{inner.Message}"); } catch { }
        }
    }

    private string BuildLine(VoxLogLevel level, string message, object? data, Exception? ex)
    {
        var sb = new StringBuilder(256);
        sb.Append('{');
        AppendString(sb, "ts", DateTime.UtcNow.ToString("o"));
        sb.Append(',');
        AppendString(sb, "level", LevelText(level));

        var opName = CurrentOperation;
        var opId = CurrentOperationId;
        if (!string.IsNullOrEmpty(opName))
        {
            sb.Append(',');
            AppendString(sb, "op", opName);
        }
        if (!string.IsNullOrEmpty(opId))
        {
            sb.Append(',');
            AppendString(sb, "op_id", opId);
        }

        sb.Append(',');
        AppendString(sb, "msg", message ?? string.Empty);

        if (data is not null)
        {
            var sanitized = SerializeAndSanitize(data);
            if (sanitized is not null)
            {
                sb.Append(",\"data\":");
                sb.Append(sanitized);
            }
        }

        if (ex is not null)
        {
            sb.Append(',');
            AppendString(sb, "ex", ex.ToString());
        }

        sb.Append('}');
        return sb.ToString();
    }

    private static string? SerializeAndSanitize(object data)
    {
        try
        {
            var node = JsonSerializer.SerializeToNode(data);
            if (node is null) return null;
            SanitizeNode(node);
            return node.ToJsonString();
        }
        catch
        {
            try
            {
                var fallback = data.ToString();
                return JsonSerializer.Serialize(fallback);
            }
            catch
            {
                return null;
            }
        }
    }

    private static void SanitizeNode(JsonNode node)
    {
        if (node is JsonObject obj)
        {
            var keys = obj.Select(kv => kv.Key).ToList();
            foreach (var key in keys)
            {
                if (IsSecretKey(key))
                {
                    obj[key] = "***";
                }
                else
                {
                    var child = obj[key];
                    if (child is not null) SanitizeNode(child);
                }
            }
        }
        else if (node is JsonArray arr)
        {
            foreach (var item in arr)
            {
                if (item is not null) SanitizeNode(item);
            }
        }
    }

    private static bool IsSecretKey(string key)
    {
        var lower = key.ToLowerInvariant();
        foreach (var token in SecretKeyTokens)
        {
            if (lower.Contains(token)) return true;
        }
        return false;
    }

    private static string LevelText(VoxLogLevel level) => level switch
    {
        VoxLogLevel.Trace => "trace",
        VoxLogLevel.Debug => "debug",
        VoxLogLevel.Info => "info",
        VoxLogLevel.Warning => "warning",
        VoxLogLevel.Error => "error",
        VoxLogLevel.Fatal => "fatal",
        _ => "info"
    };

    private static void AppendString(StringBuilder sb, string name, string value)
    {
        sb.Append('"');
        sb.Append(EscapeJson(name));
        sb.Append("\":");
        sb.Append('"');
        sb.Append(EscapeJson(value));
        sb.Append('"');
    }

    private static string EscapeJson(string s)
    {
        var sb = new StringBuilder(s.Length + 8);
        foreach (var c in s)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                case '\b': sb.Append("\\b"); break;
                case '\f': sb.Append("\\f"); break;
                default:
                    if (c < 0x20)
                        sb.Append("\\u").Append(((int)c).ToString("x4"));
                    else
                        sb.Append(c);
                    break;
            }
        }
        return sb.ToString();
    }

    private void OpenAppend()
    {
        var path = Path.Combine(_logDirectory, _baseName);
        var stream = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.Read);
        _writer = new StreamWriter(stream, new UTF8Encoding(false));
        _writer.AutoFlush = false;
        _currentBytes = stream.Length;
    }

    private void RotateIfNeeded()
    {
        if (_options.MaxFileBytes <= 0) return;
        if (_currentBytes <= _options.MaxFileBytes) return;

        try { _writer?.Flush(); } catch { }
        try { _writer?.Dispose(); } catch { }
        _writer = null;

        var basePath = Path.Combine(_logDirectory, _baseName);
        int index = 1;
        string rotated;
        do
        {
            rotated = Path.Combine(_logDirectory, $"voxloom-{DateTime.Now:yyyyMMdd}.{index}.log");
            index++;
        } while (File.Exists(rotated));

        try
        {
            if (File.Exists(basePath)) File.Move(basePath, rotated);
        }
        catch { }

        OpenAppend();
        // 先建新文件再裁剪：否则裁剪时数不到刚建的 base 文件，稳态会多留一个。
        PruneOldFiles();
    }

    private void PruneOldFiles()
    {
        try
        {
            var files = Directory.GetFiles(_logDirectory, "voxloom-*.log")
                .Select(f => new FileInfo(f))
                .OrderByDescending(f => f.LastWriteTimeUtc)
                .ToList();
            for (int i = _options.MaxRetainedFiles; i < files.Count; i++)
            {
                try { files[i].Delete(); } catch { }
            }
        }
        catch { }
    }

    public void Dispose()
    {
        lock (_lock)
        {
            if (_disposed) return;
            _disposed = true;
            try { _writer?.Flush(); } catch { }
            try { _writer?.Dispose(); } catch { }
            _writer = null;
        }
    }
}
