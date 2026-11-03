using System;
using System.Globalization;
using System.Text;
using System.Text.Json.Nodes;

namespace VoxLoom.Core.Logging;

public static class VoxConsoleFormat
{
    public static string FormatDuration(TimeSpan d)
    {
        if (d < TimeSpan.Zero) d = TimeSpan.Zero;
        var totalMs = d.TotalMilliseconds;
        if (totalMs < 1000)
        {
            return string.Format(CultureInfo.InvariantCulture, "{0:0.#}ms", totalMs);
        }
        var totalSeconds = d.TotalSeconds;
        if (totalSeconds < 60)
        {
            return string.Format(CultureInfo.InvariantCulture, "{0:0.#}s", totalSeconds);
        }
        var totalMinutes = d.TotalMinutes;
        if (totalMinutes < 60)
        {
            var m = (int)totalMinutes;
            var s = d.Seconds;
            return string.Format(CultureInfo.InvariantCulture, "{0:0}m{1:0}s", m, s);
        }
        var h = (int)d.TotalHours;
        var mm = d.Minutes;
        return string.Format(CultureInfo.InvariantCulture, "{0:0}h{1:0}m", h, mm);
    }

    public static string FormatBytes(long bytes)
    {
        if (bytes < 0) bytes = 0;
        if (bytes < 1024)
        {
            return bytes.ToString(CultureInfo.InvariantCulture) + " B";
        }
        if (bytes < 1024L * 1024L)
        {
            return string.Format(CultureInfo.InvariantCulture, "{0:0.#} KB", bytes / 1024.0);
        }
        if (bytes < 1024L * 1024L * 1024L)
        {
            return string.Format(CultureInfo.InvariantCulture, "{0:0.#} MB", bytes / (1024.0 * 1024.0));
        }
        return string.Format(CultureInfo.InvariantCulture, "{0:0.#} GB", bytes / (1024.0 * 1024.0 * 1024.0));
    }

    public static string FormatLevel(VoxLogLevel level) => level switch
    {
        VoxLogLevel.Trace => "TRACE",
        VoxLogLevel.Debug => "DEBUG",
        VoxLogLevel.Info => "INFO ",
        VoxLogLevel.Warning => "WARN ",
        VoxLogLevel.Error => "ERROR",
        VoxLogLevel.Fatal => "FATAL",
        _ => "INFO "
    };

    public static ConsoleColor? ColorFor(VoxLogLevel level) => level switch
    {
        VoxLogLevel.Trace => ConsoleColor.Gray,
        VoxLogLevel.Debug => ConsoleColor.Gray,
        VoxLogLevel.Info => null,
        VoxLogLevel.Warning => ConsoleColor.Yellow,
        VoxLogLevel.Error => ConsoleColor.Red,
        VoxLogLevel.Fatal => ConsoleColor.DarkRed,
        _ => null
    };

    public static string RenderLine(VoxLogLevel level, string message, string? operation, string? operationId, string? sanitizedDataJson, DateTime timestampUtc)
    {
        var sb = new StringBuilder(128);
        sb.Append('[');
        sb.Append(timestampUtc.ToLocalTime().ToString("HH:mm:ss", CultureInfo.InvariantCulture));
        sb.Append("] ");
        sb.Append(FormatLevel(level));
        sb.Append(' ');
        sb.Append(message ?? string.Empty);

        if (!string.IsNullOrEmpty(operation))
        {
            sb.Append(" op=");
            sb.Append(operation);
        }
        if (!string.IsNullOrEmpty(operationId))
        {
            sb.Append(" id=");
            sb.Append(operationId);
        }

        if (!string.IsNullOrEmpty(sanitizedDataJson))
        {
            JsonNode? node = null;
            try { node = JsonNode.Parse(sanitizedDataJson); } catch { node = null; }

            if (node is JsonObject obj)
            {
                foreach (var kv in obj)
                {
                    sb.Append(' ');
                    sb.Append(kv.Key);
                    sb.Append('=');
                    sb.Append(ValueToText(kv.Value, kv.Key));
                }
            }
            else if (node is not null)
            {
                sb.Append(" data=");
                sb.Append(node.ToJsonString());
            }
        }

        return sb.ToString();
    }

    private static string ValueToText(JsonNode? v, string key)
    {
        if (v is null) return "null";

        if (v is JsonValue value)
        {
            if (value.TryGetValue<string>(out var s)) return s;
            if (value.TryGetValue<bool>(out var b)) return b ? "true" : "false";
            if (value.TryGetValue<decimal>(out var dec))
            {
                if (IsBytesKey(key))
                {
                    return FormatBytes((long)dec);
                }
                return dec.ToString(CultureInfo.InvariantCulture);
            }
            return value.ToJsonString();
        }

        return v.ToJsonString();
    }

    private static bool IsBytesKey(string key)
    {
        return key.EndsWith("bytes", StringComparison.Ordinal)
            || key.EndsWith("Bytes", StringComparison.Ordinal)
            || key.EndsWith("size", StringComparison.Ordinal)
            || key.EndsWith("Size", StringComparison.Ordinal);
    }

    public static string RenderTable(string[] headers, string[][] rows)
    {
        int cols = headers.Length;
        var widths = new int[cols];
        for (int c = 0; c < cols; c++)
        {
            widths[c] = DisplayWidth(headers[c]) + 2;
        }
        if (rows is not null)
        {
            foreach (var row in rows)
            {
                if (row is null) continue;
                for (int c = 0; c < cols && c < row.Length; c++)
                {
                    var w = DisplayWidth(row[c]) + 2;
                    if (w > widths[c]) widths[c] = w;
                }
            }
        }

        var sb = new StringBuilder();

        for (int c = 0; c < cols; c++)
        {
            if (c > 0) sb.Append(' ');
            sb.Append(PadCell(headers[c], widths[c]));
        }
        sb.Append('\n');

        for (int c = 0; c < cols; c++)
        {
            if (c > 0) sb.Append(' ');
            sb.Append(new string('-', widths[c]));
        }

        if (rows is not null)
        {
            foreach (var row in rows)
            {
                sb.Append('\n');
                for (int c = 0; c < cols; c++)
                {
                    if (c > 0) sb.Append(' ');
                    var cell = (row is not null && c < row.Length) ? row[c] : null;
                    sb.Append(PadCell(cell, widths[c]));
                }
            }
        }

        return sb.ToString();
    }

    private static string PadCell(string? s, int width)
    {
        var text = s ?? string.Empty;
        var pad = width - DisplayWidth(text);
        if (pad <= 0) return text;
        return text + new string(' ', pad);
    }

    public static int DisplayWidth(string s)
    {
        if (s is null) return 0;
        int w = 0;
        foreach (var ch in s)
        {
            w += IsWide(ch) ? 2 : 1;
        }
        return w;
    }

    private static bool IsWide(char c)
    {
        if (c >= '\u1100' && c <= '\u115F') return true;
        if (c == '\u2329' || c == '\u232A') return true;
        if (c >= '\u2E80' && c <= '\uA4CF') return true;
        if (c >= '\uAC00' && c <= '\uD7A3') return true;
        if (c >= '\uF900' && c <= '\uFAFF') return true;
        if (c >= '\uFE10' && c <= '\uFE19') return true;
        if (c >= '\uFE30' && c <= '\uFE4F') return true;
        if (c >= '\uFF00' && c <= '\uFF60') return true;
        if (c >= '\uFFE0' && c <= '\uFFE6') return true;
        return false;
    }

    public static string RenderProgressBar(double fraction, int width = 20)
    {
        if (fraction < 0) fraction = 0;
        if (fraction > 1) fraction = 1;
        if (width < 1) width = 1;
        int filled = (int)Math.Round(fraction * width);
        if (filled < 0) filled = 0;
        if (filled > width) filled = width;
        return new string('█', filled)
            + new string('░', width - filled)
            + " "
            + ((int)Math.Round(fraction * 100)).ToString(CultureInfo.InvariantCulture)
            + "%";
    }
}
