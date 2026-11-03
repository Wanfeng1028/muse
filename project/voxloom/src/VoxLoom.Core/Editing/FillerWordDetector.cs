using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Editing;

/// <summary>
/// 中文播客语气词检测：识别「嗯、啊、那个、这个、然后（句首）、就是说」等填充词，
/// 并返回合并后的时间区间，便于一键弱化或删除。
/// </summary>
public static class FillerWordDetector
{
    /// <summary>相邻命中间隔小于该阈值时合并为一个区间。</summary>
    private const double MergeGapSeconds = 0.300;

    /// <summary>默认语气词表。</summary>
    public static readonly IReadOnlyList<string> DefaultFillers = new[]
    {
        "嗯", "啊", "那个", "这个", "然后", "就是说"
    };

    /// <summary>
    /// 使用默认语气词表检测。
    /// </summary>
    public static IReadOnlyList<TimeRange> Detect(TranscriptDoc transcript)
        => Detect(transcript, DefaultFillers);

    /// <summary>
    /// 使用自定义语气词表检测。
    /// 规则：词的 Text 去掉标点后与语气词完全相等即命中；
    /// 若语气词为「然后」，仅当其为句首（即它前面的词以句末标点结尾，或它是第一个词）时命中。
    /// 返回的区间按时间排序，相邻命中间隔 &lt; 300ms 合并。
    /// </summary>
    public static IReadOnlyList<TimeRange> Detect(
        TranscriptDoc transcript, IReadOnlyCollection<string> fillers)
    {
        ArgumentNullException.ThrowIfNull(transcript);
        ArgumentNullException.ThrowIfNull(fillers);

        var normalized = new HashSet<string>(fillers
            .Where(f => !string.IsNullOrWhiteSpace(f))
            .Select(f => StripPunctuation(f).Trim()),
            StringComparer.Ordinal);

        if (normalized.Count == 0) return Array.Empty<TimeRange>();

        var words = transcript.Words;
        var hits = new List<TimeRange>();

        for (int i = 0; i < words.Count; i++)
        {
            var w = words[i];
            string text = StripPunctuation(w.Text).Trim();
            if (text.Length == 0) continue;

            if (!normalized.Contains(text)) continue;

            // 特殊规则：'然后' 仅在句首命中
            if (text == "然后" && !IsSentenceStart(words, i))
            {
                continue;
            }

            hits.Add(new TimeRange(w.Start, w.End));
        }

        return MergeAdjacent(hits, MergeGapSeconds);
    }

    /// <summary>
    /// 将命中区间转为一组 AttenuateOp（一键弱化）。
    /// </summary>
    public static EditOp[] ToAttenuateOps(IReadOnlyList<TimeRange> ranges, float db = -12f)
    {
        ArgumentNullException.ThrowIfNull(ranges);

        var ops = new EditOp[ranges.Count];
        for (int i = 0; i < ranges.Count; i++)
        {
            ops[i] = new AttenuateOp(ranges[i], db);
        }
        return ops;
    }

    /// <summary>
    /// 判断词 i 是否位于句首（前面没有词，或前一个词以句末标点结尾）。
    /// </summary>
    private static bool IsSentenceStart(IReadOnlyList<TranscriptWord> words, int i)
    {
        if (i == 0) return true;
        var prev = words[i - 1];
        string prevText = prev.Text ?? string.Empty;
        if (prevText.Length == 0) return false;

        char last = prevText[^1];
        return IsSentenceEndPunct(last);
    }

    private static bool IsSentenceEndPunct(char c)
        => c == '。' || c == '！' || c == '？' || c == '.' || c == '!' || c == '?'
           || c == '；' || c == ';' || c == '…' || c == '、' || c == ',';

    /// <summary>
    /// 去除中英文标点与空白。
    /// </summary>
    private static string StripPunctuation(string s)
    {
        if (string.IsNullOrEmpty(s)) return string.Empty;

        var sb = new StringBuilder(s.Length);
        foreach (char c in s)
        {
            if (char.IsWhiteSpace(c)) continue;
            if (char.IsPunctuation(c)) continue;
            if (char.IsSymbol(c)) continue;
            sb.Append(c);
        }
        return sb.ToString();
    }

    /// <summary>
    /// 合并相邻或间隔小于 gapSeconds 的区间。
    /// </summary>
    private static IReadOnlyList<TimeRange> MergeAdjacent(
        List<TimeRange> ranges, double gapSeconds)
    {
        if (ranges.Count == 0) return Array.Empty<TimeRange>();

        var ordered = ranges.OrderBy(r => r.Start).ToList();
        var merged = new List<TimeRange>();

        var current = ordered[0];
        for (int i = 1; i < ordered.Count; i++)
        {
            var next = ordered[i];
            double gap = (next.Start - current.End).TotalSeconds;

            if (gap < gapSeconds)
            {
                // 合并：取并集
                var newEnd = next.End > current.End ? next.End : current.End;
                current = new TimeRange(current.Start, newEnd);
            }
            else
            {
                merged.Add(current);
                current = next;
            }
        }
        merged.Add(current);

        return merged;
    }
}
