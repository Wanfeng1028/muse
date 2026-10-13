using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace VoxLoom.Core.Transcript;

/// <summary>
/// 转写稿导入器：支持 Whisper JSON、LRC、纯文本三种格式。
/// </summary>
public static class TranscriptImporter
{
    /// <summary>
    /// 解析 whisper.cpp / faster-whisper verbose_json 格式。
    /// 优先使用 segments[].words[] 词级时间；若缺失则按 segments 内字数均分。
    /// </summary>
    public static TranscriptDoc ParseWhisperJson(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            throw new TranscriptFormatException("Whisper JSON 内容为空。");
        }

        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(json);
        }
        catch (JsonException ex)
        {
            throw new TranscriptFormatException("Whisper JSON 解析失败：JSON 语法错误。", ex);
        }

        using (doc)
        {
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                throw new TranscriptFormatException("Whisper JSON 顶层必须是对象。");
            }

            if (!root.TryGetProperty("segments", out var segments) || segments.ValueKind != JsonValueKind.Array)
            {
                throw new TranscriptFormatException("Whisper JSON 缺少 segments 数组。");
            }

            var words = new List<TranscriptWord>();
            TimeSpan maxEnd = TimeSpan.Zero;

            foreach (var seg in segments.EnumerateArray())
            {
                if (seg.ValueKind != JsonValueKind.Object) continue;

                double segStart = ReadDouble(seg, "start", 0);
                double segEnd = ReadDouble(seg, "end", segStart);
                string segText = ReadString(seg, "text") ?? string.Empty;
                float segConf = (float)ReadDouble(seg, "confidence", 1.0);

                TimeSpan segStartTs = SecondsToTimeSpan(segStart);
                TimeSpan segEndTs = SecondsToTimeSpan(segEnd);
                if (segEndTs < segStartTs) segEndTs = segStartTs;
                if (segEndTs > maxEnd) maxEnd = segEndTs;

                bool hasWords = seg.TryGetProperty("words", out var wordsArr)
                    && wordsArr.ValueKind == JsonValueKind.Array
                    && wordsArr.GetArrayLength() > 0;

                if (hasWords)
                {
                    foreach (var w in wordsArr.EnumerateArray())
                    {
                        if (w.ValueKind != JsonValueKind.Object) continue;
                        string? text = ReadString(w, "word") ?? ReadString(w, "text");
                        if (string.IsNullOrEmpty(text)) continue;

                        double ws = ReadDouble(w, "start", segStart);
                        double we = ReadDouble(w, "end", ws);
                        float conf = (float)ReadDouble(w, "probability",
                            ReadDouble(w, "confidence", segConf));

                        var wsTs = SecondsToTimeSpan(ws);
                        var weTs = SecondsToTimeSpan(we);
                        if (weTs < wsTs) weTs = wsTs;
                        if (weTs > maxEnd) maxEnd = weTs;

                        words.Add(new TranscriptWord(text.Trim(), wsTs, weTs, conf));
                    }
                }
                else
                {
                    // 退化：按段内字符数均分。
                    var pieces = SplitByCharWeight(segText);
                    if (pieces.Count == 0) continue;
                    var dur = segEndTs - segStartTs;
                    if (dur < TimeSpan.Zero) dur = TimeSpan.Zero;
                    double totalWeight = 0;
                    foreach (var p in pieces) totalWeight += Math.Max(1, p.Length);
                    if (totalWeight <= 0) totalWeight = 1;

                    TimeSpan cursor = segStartTs;
                    foreach (var p in pieces)
                    {
                        double w = Math.Max(1, p.Length) / totalWeight;
                        var pieceDur = TimeSpan.FromTicks((long)(dur.Ticks * w));
                        var pieceEnd = cursor + pieceDur;
                        if (pieceEnd > segEndTs) pieceEnd = segEndTs;
                        words.Add(new TranscriptWord(p, cursor, pieceEnd, segConf));
                        cursor = pieceEnd;
                    }
                }
            }

            return new TranscriptDoc(words, maxEnd);
        }
    }

    /// <summary>
    /// 解析 LRC 格式：每行形如 [mm:ss.cc] 文本，词级时间按行内字数均分。
    /// </summary>
    public static TranscriptDoc ParseLrc(string lrc)
    {
        if (string.IsNullOrWhiteSpace(lrc))
        {
            throw new TranscriptFormatException("LRC 内容为空。");
        }

        var lines = lrc.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
        var entries = new List<(TimeSpan Start, string Text)>();

        var tagRegex = new Regex(@"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]", RegexOptions.Compiled);

        foreach (var raw in lines)
        {
            string line = raw.Trim();
            if (line.Length == 0) continue;

            var matches = tagRegex.Matches(line);
            if (matches.Count == 0) continue;

            // 文本是最后一个标签之后的全部内容。
            var last = matches[^1];
            string text = line[(last.Index + last.Length)..].Trim();
            if (text.Length == 0) continue;

            foreach (Match m in matches)
            {
                int mm = int.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture);
                int ss = int.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture);
                string cs = m.Groups[3].Success ? m.Groups[3].Value : "0";

                // 厘秒对齐到两位或三位。
                int centis;
                if (cs.Length == 1) centis = int.Parse(cs, CultureInfo.InvariantCulture) * 10;
                else if (cs.Length == 2) centis = int.Parse(cs, CultureInfo.InvariantCulture);
                else centis = int.Parse(cs[..2], CultureInfo.InvariantCulture);

                var ts = new TimeSpan(0, 0, mm, ss, centis * 10);
                entries.Add((ts, text));
            }
        }

        if (entries.Count == 0)
        {
            throw new TranscriptFormatException("LRC 中未找到任何有效的时间标签行。");
        }

        entries.Sort(static (a, b) => a.Start.CompareTo(b.Start));

        var words = new List<TranscriptWord>();
        TimeSpan maxEnd = TimeSpan.Zero;

        for (int i = 0; i < entries.Count; i++)
        {
            var (start, text) = entries[i];
            TimeSpan end = i + 1 < entries.Count ? entries[i + 1].Start : start + EstimateDuration(text);
            if (end < start) end = start;
            if (end > maxEnd) maxEnd = end;

            var pieces = SplitByCharWeight(text);
            if (pieces.Count == 0) continue;

            double totalWeight = 0;
            foreach (var p in pieces) totalWeight += Math.Max(1, p.Length);
            if (totalWeight <= 0) totalWeight = 1;

            var dur = end - start;
            TimeSpan cursor = start;
            foreach (var p in pieces)
            {
                double w = Math.Max(1, p.Length) / totalWeight;
                var pieceDur = TimeSpan.FromTicks((long)(dur.Ticks * w));
                var pieceEnd = cursor + pieceDur;
                if (pieceEnd > end) pieceEnd = end;
                words.Add(new TranscriptWord(p, cursor, pieceEnd, 1f));
                cursor = pieceEnd;
            }
        }

        return new TranscriptDoc(words, maxEnd);
    }

    /// <summary>
    /// 解析纯文本：按字符数均分 totalDuration。
    /// </summary>
    public static TranscriptDoc ParsePlainText(string text, TimeSpan totalDuration)
    {
        if (text is null)
        {
            throw new TranscriptFormatException("纯文本内容为 null。");
        }

        if (totalDuration < TimeSpan.Zero)
        {
            throw new TranscriptFormatException("总时长不能为负。");
        }

        var pieces = SplitByCharWeight(text);
        if (pieces.Count == 0)
        {
            throw new TranscriptFormatException("纯文本内容为空，无法解析。");
        }

        double totalWeight = 0;
        foreach (var p in pieces) totalWeight += Math.Max(1, p.Length);
        if (totalWeight <= 0) totalWeight = 1;

        var words = new List<TranscriptWord>(pieces.Count);
        TimeSpan cursor = TimeSpan.Zero;
        for (int i = 0; i < pieces.Count; i++)
        {
            double w = Math.Max(1, pieces[i].Length) / totalWeight;
            TimeSpan pieceDur = TimeSpan.FromTicks((long)(totalDuration.Ticks * w));
            TimeSpan end = i == pieces.Count - 1 ? totalDuration : cursor + pieceDur;
            if (end > totalDuration) end = totalDuration;
            if (end < cursor) end = cursor;
            words.Add(new TranscriptWord(pieces[i], cursor, end, 1f));
            cursor = end;
        }

        return new TranscriptDoc(words, totalDuration);
    }

    private static TimeSpan EstimateDuration(string text)
    {
        // 粗略：每个 CJK 字 200ms，其他字符 100ms。
        double secs = 0;
        foreach (var c in text)
        {
            secs += IsCjk(c) ? 0.2 : 0.1;
        }
        if (secs <= 0) secs = 0.2;
        return TimeSpan.FromSeconds(secs);
    }

    private static List<string> SplitByCharWeight(string text)
    {
        var result = new List<string>();
        if (string.IsNullOrWhiteSpace(text)) return result;

        var sb = new StringBuilder();
        foreach (var c in text)
        {
            if (char.IsWhiteSpace(c))
            {
                if (sb.Length > 0)
                {
                    result.Add(sb.ToString());
                    sb.Clear();
                }
            }
            else if (IsCjk(c))
            {
                if (sb.Length > 0)
                {
                    result.Add(sb.ToString());
                    sb.Clear();
                }
                result.Add(c.ToString());
            }
            else if (IsPunctuation(c))
            {
                if (sb.Length > 0)
                {
                    sb.Append(c);
                    result.Add(sb.ToString());
                    sb.Clear();
                }
                else if (result.Count > 0)
                {
                    // 标点附着到前一个词。
                    result[^1] += c;
                }
                else
                {
                    result.Add(c.ToString());
                }
            }
            else
            {
                sb.Append(c);
            }
        }

        if (sb.Length > 0) result.Add(sb.ToString());
        return result;
    }

    private static bool IsCjk(char c)
    {
        return (c >= '\u4E00' && c <= '\u9FFF')
            || (c >= '\u3400' && c <= '\u4DBF')
            || (c >= '\uF900' && c <= '\uFAFF')
            || (c >= '\u3040' && c <= '\u30FF');
    }

    private static bool IsPunctuation(char c)
    {
        if (char.IsPunctuation(c)) return true;
        return c is '。' or '，' or '！' or '？' or '；' or '：' or '、' or '“' or '”' or '‘' or '’' or '（' or '）' or '《' or '》';
    }

    private static TimeSpan SecondsToTimeSpan(double seconds)
    {
        if (double.IsNaN(seconds) || seconds < 0) seconds = 0;
        if (double.IsInfinity(seconds)) seconds = 0;
        return TimeSpan.FromSeconds(seconds);
    }

    private static double ReadDouble(JsonElement obj, string name, double fallback)
    {
        if (!obj.TryGetProperty(name, out var el)) return fallback;
        switch (el.ValueKind)
        {
            case JsonValueKind.Number:
                return el.GetDouble();
            case JsonValueKind.String:
                return double.TryParse(el.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : fallback;
            default:
                return fallback;
        }
    }

    private static string? ReadString(JsonElement obj, string name)
    {
        if (!obj.TryGetProperty(name, out var el)) return null;
        return el.ValueKind == JsonValueKind.String ? el.GetString() : null;
    }
}
