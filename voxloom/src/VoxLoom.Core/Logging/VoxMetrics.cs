using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;

namespace VoxLoom.Core.Logging;

/// <summary>
/// VoxLoom 指标记录器：把操作耗时/成功失败等指标以 JSONL 追加写入本地文件。
/// 文件复用与 <see cref="VoxLogger"/> 一致的体积轮转语义（按修改时间倒序裁剪）。
/// 线程安全，未初始化时静默丢弃写入。
/// </summary>
public static class VoxMetrics
{
    /// <summary>
    /// 单个 op 的聚合摘要。
    /// </summary>
    /// <param name="Op">操作名。</param>
    /// <param name="Count">总条数。</param>
    /// <param name="Failures">失败条数（success == false）。</param>
    /// <param name="AvgMs">平均耗时（毫秒，保留 1 位小数）。</param>
    /// <param name="SuccessRate">成功率，四舍五入到 4 位小数；Count 为 0 时为 1.0。</param>
    public sealed record MetricSummary(string Op, int Count, int Failures, double AvgMs, double SuccessRate);

    private static readonly object WriteLock = new object();

    private static string? _directory;
    private static StreamWriter? _writer;
    private static long _currentBytes;

    /// <summary>
    /// 指标文件体积上限（字节）。超过后触发轮转。测试可调小。
    /// </summary>
    public static long MaxFileBytes { get; set; } = 5 * 1024 * 1024;

    /// <summary>
    /// 指标文件保留份数上限（含当前文件）。测试可调小。
    /// </summary>
    public static int MaxRetainedFiles { get; set; } = 10;

    /// <summary>
    /// 初始化指标写入目录，可重复调用以切换目录（旧 writer 会先被释放）。
    /// </summary>
    /// <param name="directory">目标目录，不能为空或空白。</param>
    /// <exception cref="ArgumentException">directory 为 null、空或仅空白时抛出。</exception>
    public static void Initialize(string directory)
    {
        if (string.IsNullOrWhiteSpace(directory))
        {
            throw new ArgumentException("指标目录不能为空。", nameof(directory));
        }

        lock (WriteLock)
        {
            ReleaseWriterLocked();
            _directory = directory;
            Directory.CreateDirectory(directory);
            OpenWriterLocked();
        }
    }

    /// <summary>
    /// 释放当前 writer，供测试清理使用。可重复调用。
    /// </summary>
    public static void Shutdown()
    {
        lock (WriteLock)
        {
            ReleaseWriterLocked();
        }
    }

    /// <summary>
    /// 计时执行带返回值的操作，成功返回其结果；失败时记录失败指标并原样抛出原始异常。
    /// </summary>
    /// <typeparam name="T">返回值类型。</typeparam>
    /// <param name="op">操作名。</param>
    /// <param name="body">要执行的操作。</param>
    /// <param name="items">可选的条目数。</param>
    /// <returns>body 的返回值。</returns>
    public static T Timed<T>(string op, Func<T> body, int? items = null)
    {
        ArgumentNullException.ThrowIfNull(body);
        Stopwatch stopwatch = Stopwatch.StartNew();
        try
        {
            T result = body();
            stopwatch.Stop();
            Record(op, stopwatch.Elapsed, true, null, items);
            return result;
        }
        catch (Exception ex)
        {
            stopwatch.Stop();
            Record(op, stopwatch.Elapsed, false, ex.GetType().Name, items);
            throw;
        }
    }

    /// <summary>
    /// 计时执行无返回值的操作，失败时记录失败指标并原样抛出原始异常。
    /// </summary>
    /// <param name="op">操作名。</param>
    /// <param name="body">要执行的操作。</param>
    /// <param name="items">可选的条目数。</param>
    public static void Timed(string op, Action body, int? items = null)
    {
        ArgumentNullException.ThrowIfNull(body);
        Stopwatch stopwatch = Stopwatch.StartNew();
        try
        {
            body();
            stopwatch.Stop();
            Record(op, stopwatch.Elapsed, true, null, items);
        }
        catch (Exception ex)
        {
            stopwatch.Stop();
            Record(op, stopwatch.Elapsed, false, ex.GetType().Name, items);
            throw;
        }
    }

    /// <summary>
    /// 记录一条指标。未初始化时静默丢弃。
    /// </summary>
    /// <param name="op">操作名。</param>
    /// <param name="duration">耗时。</param>
    /// <param name="success">是否成功。</param>
    /// <param name="errorType">失败时的异常类型名，成功时为 null。</param>
    /// <param name="items">可选的条目数。</param>
    public static void Record(string op, TimeSpan duration, bool success, string? errorType = null, int? items = null)
    {
        lock (WriteLock)
        {
            if (_writer is null || _directory is null)
            {
                return;
            }

            double durationMs = Math.Round(duration.TotalMilliseconds, 1, MidpointRounding.AwayFromZero);

            string line = BuildLine(op, durationMs, success, errorType, items);
            byte[] payload = Encoding.UTF8.GetBytes(line);

            if (_currentBytes + payload.Length > MaxFileBytes)
            {
                RotateLocked();
                if (_writer is null)
                {
                    return;
                }
            }

            _writer.Write(line);
            _writer.Flush();
            _currentBytes += payload.Length;
        }
    }

    /// <summary>
    /// 读取指定目录下的全部指标文件并聚合为摘要，按 Op 字母序返回。
    /// 坏行会被跳过，不抛异常。
    /// </summary>
    /// <param name="directory">指标目录。</param>
    /// <param name="sinceUtc">若非空，仅统计 ts &gt;= sinceUtc 的记录。</param>
    /// <returns>聚合摘要列表。</returns>
    public static IReadOnlyList<MetricSummary> ReadSummary(string directory, DateTime? sinceUtc = null)
    {
        if (string.IsNullOrWhiteSpace(directory) || !Directory.Exists(directory))
        {
            return Array.Empty<MetricSummary>();
        }

        Dictionary<string, Accumulator> map = new Dictionary<string, Accumulator>(StringComparer.Ordinal);
        string[] files = Directory.GetFiles(directory, "metrics-*.jsonl");

        foreach (string file in files)
        {
            IEnumerable<string> lines;
            try
            {
                lines = File.ReadLines(file);
            }
            catch (IOException)
            {
                continue;
            }
            catch (UnauthorizedAccessException)
            {
                continue;
            }

            foreach (string raw in lines)
            {
                if (string.IsNullOrWhiteSpace(raw))
                {
                    continue;
                }

                if (!TryParseLine(raw, sinceUtc, out string op, out double durationMs, out bool success))
                {
                    continue;
                }

                if (!map.TryGetValue(op, out Accumulator? acc))
                {
                    acc = new Accumulator();
                    map[op] = acc;
                }

                acc.Count++;
                if (!success)
                {
                    acc.Failures++;
                }
                acc.TotalMs += durationMs;
            }
        }

        List<MetricSummary> result = new List<MetricSummary>(map.Count);
        foreach (KeyValuePair<string, Accumulator> pair in map)
        {
            Accumulator acc = pair.Value;
            double avgMs = acc.Count > 0 ? Math.Round(acc.TotalMs / acc.Count, 1, MidpointRounding.AwayFromZero) : 0.0;
            double successRate = acc.Count == 0
                ? 1.0
                : Math.Round((double)(acc.Count - acc.Failures) / acc.Count, 4, MidpointRounding.AwayFromZero);
            result.Add(new MetricSummary(pair.Key, acc.Count, acc.Failures, avgMs, successRate));
        }

        result.Sort(static (a, b) => string.CompareOrdinal(a.Op, b.Op));
        return result;
    }

    private static string BuildLine(string op, double durationMs, bool success, string? errorType, int? items)
    {
        StringBuilder builder = new StringBuilder(160);
        builder.Append('{');
        builder.Append("\"ts\":\"");
        builder.Append(DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ", CultureInfo.InvariantCulture));
        builder.Append("\",\"op\":");
        AppendJsonString(builder, op);
        builder.Append(",\"duration_ms\":");
        builder.Append(durationMs.ToString("0.0", CultureInfo.InvariantCulture));
        builder.Append(",\"success\":");
        builder.Append(success ? "true" : "false");
        builder.Append(",\"error_type\":");
        if (errorType is null)
        {
            builder.Append("null");
        }
        else
        {
            AppendJsonString(builder, errorType);
        }
        builder.Append(",\"items\":");
        if (items.HasValue)
        {
            builder.Append(items.Value.ToString(CultureInfo.InvariantCulture));
        }
        else
        {
            builder.Append("null");
        }
        builder.Append('}');
        builder.Append('\n');
        return builder.ToString();
    }

    private static void AppendJsonString(StringBuilder builder, string value)
    {
        builder.Append('"');
        foreach (char c in value)
        {
            switch (c)
            {
                case '"':
                    builder.Append("\\\"");
                    break;
                case '\\':
                    builder.Append("\\\\");
                    break;
                case '\n':
                    builder.Append("\\n");
                    break;
                case '\r':
                    builder.Append("\\r");
                    break;
                case '\t':
                    builder.Append("\\t");
                    break;
                default:
                    if (c < ' ')
                    {
                        builder.Append("\\u");
                        builder.Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                    }
                    else
                    {
                        builder.Append(c);
                    }
                    break;
            }
        }
        builder.Append('"');
    }

    private static bool TryParseLine(string line, DateTime? sinceUtc, out string op, out double durationMs, out bool success)
    {
        op = string.Empty;
        durationMs = 0.0;
        success = true;

        try
        {
            using JsonDocument document = JsonDocument.Parse(line);
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                return false;
            }

            if (!root.TryGetProperty("op", out JsonElement opElement) || opElement.ValueKind != JsonValueKind.String)
            {
                return false;
            }

            string? opValue = opElement.GetString();
            if (string.IsNullOrEmpty(opValue))
            {
                return false;
            }

            if (!root.TryGetProperty("duration_ms", out JsonElement durationElement) || durationElement.ValueKind != JsonValueKind.Number)
            {
                return false;
            }

            if (!durationElement.TryGetDouble(out double durationValue))
            {
                return false;
            }

            if (!root.TryGetProperty("success", out JsonElement successElement) ||
                (successElement.ValueKind != JsonValueKind.True && successElement.ValueKind != JsonValueKind.False))
            {
                return false;
            }

            if (sinceUtc.HasValue)
            {
                if (!root.TryGetProperty("ts", out JsonElement tsElement) || tsElement.ValueKind != JsonValueKind.String)
                {
                    return false;
                }

                string? tsValue = tsElement.GetString();
                if (tsValue is null || !DateTime.TryParse(tsValue, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out DateTime parsedTs))
                {
                    return false;
                }

                if (parsedTs < sinceUtc.Value.ToUniversalTime())
                {
                    return false;
                }
            }

            op = opValue;
            durationMs = durationValue;
            success = successElement.ValueKind == JsonValueKind.True;
            return true;
        }
        catch (JsonException)
        {
            return false;
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static void OpenWriterLocked()
    {
        if (_directory is null)
        {
            return;
        }

        string path = CurrentFilePath();
        FileStream stream = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.Read);
        _writer = new StreamWriter(stream, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        _writer.AutoFlush = false;
        _currentBytes = stream.Length;
    }

    private static void ReleaseWriterLocked()
    {
        if (_writer is not null)
        {
            try
            {
                _writer.Flush();
            }
            catch (IOException)
            {
            }
            try
            {
                _writer.Dispose();
            }
            catch (IOException)
            {
            }
            _writer = null;
        }
        _currentBytes = 0;
    }

    private static void RotateLocked()
    {
        if (_directory is null)
        {
            return;
        }

        ReleaseWriterLocked();

        string currentPath = CurrentFilePath();
        if (File.Exists(currentPath))
        {
            int index = 1;
            string rotated;
            do
            {
                rotated = Path.Combine(_directory, $"metrics-{DateTime.Now:yyyyMMdd}.{index}.jsonl");
                index++;
            }
            while (File.Exists(rotated));

            try
            {
                File.Move(currentPath, rotated);
            }
            catch (IOException)
            {
            }
        }

        OpenWriterLocked();
        TrimLocked();
    }

    private static void TrimLocked()
    {
        if (_directory is null)
        {
            return;
        }

        int keep = MaxRetainedFiles;
        if (keep < 1)
        {
            keep = 1;
        }

        string[] files = Directory.GetFiles(_directory, "metrics-*.jsonl");
        if (files.Length <= keep)
        {
            return;
        }

        Array.Sort(files, static (a, b) => File.GetLastWriteTimeUtc(b).CompareTo(File.GetLastWriteTimeUtc(a)));

        for (int i = keep; i < files.Length; i++)
        {
            try
            {
                File.Delete(files[i]);
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }
    }

    private static string CurrentFilePath()
    {
        return Path.Combine(_directory!, $"metrics-{DateTime.Now:yyyyMMdd}.jsonl");
    }

    private sealed class Accumulator
    {
        public int Count;
        public int Failures;
        public double TotalMs;
    }
}
