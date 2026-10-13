using System;
using System.Collections.Generic;
using System.Text;

namespace VoxLoom.Core.Transcript;

/// <summary>时间区间（左闭右开）。</summary>
public readonly record struct TimeRange(TimeSpan Start, TimeSpan End)
{
    /// <summary>区间长度。</summary>
    public TimeSpan Duration => End - Start;

    /// <summary>是否包含给定时刻。</summary>
    public bool Contains(TimeSpan t) => t >= Start && t < End;
}

/// <summary>
/// 转写稿模型：有序词表 + 总时长，提供时间查询与全文拼接。
/// </summary>
public sealed class TranscriptDoc
{
    private readonly TranscriptWord[] _words;

    /// <summary>有序词表（按 Start 升序）。</summary>
    public IReadOnlyList<TranscriptWord> Words => _words;

    /// <summary>总时长。</summary>
    public TimeSpan Duration { get; }

    /// <summary>构造转写稿。传入词表会按 Start 排序并校验单调。</summary>
    public TranscriptDoc(IEnumerable<TranscriptWord> words, TimeSpan duration)
    {
        ArgumentNullException.ThrowIfNull(words);

        var list = new List<TranscriptWord>(words);
        list.Sort(static (a, b) => a.Start.CompareTo(b.Start));
        _words = list.ToArray();

        if (duration < TimeSpan.Zero)
        {
            duration = TimeSpan.Zero;
        }
        if (_words.Length > 0 && _words[^1].End > duration)
        {
            duration = _words[^1].End;
        }

        Duration = duration;
    }

    /// <summary>构造空转写稿。</summary>
    public static TranscriptDoc Empty { get; } = new TranscriptDoc(Array.Empty<TranscriptWord>(), TimeSpan.Zero);

    /// <summary>
    /// 二分查找命中给定时刻的词（左闭右开）。未命中返回 null。
    /// </summary>
    public TranscriptWord? WordAt(TimeSpan t)
    {
        int lo = 0;
        int hi = _words.Length - 1;
        while (lo <= hi)
        {
            int mid = lo + ((hi - lo) >> 1);
            var w = _words[mid];
            if (t < w.Start)
            {
                hi = mid - 1;
            }
            else if (t >= w.End)
            {
                lo = mid + 1;
            }
            else
            {
                return w;
            }
        }

        return null;
    }

    /// <summary>
    /// 返回与给定区间有交集的词（保持原序）。
    /// </summary>
    public IReadOnlyList<TranscriptWord> WordsIn(TimeRange range)
    {
        var result = new List<TranscriptWord>();
        if (_words.Length == 0 || range.End <= range.Start)
        {
            return result;
        }

        // 二分定位第一个 End > range.Start 的词。
        int lo = 0;
        int hi = _words.Length;
        while (lo < hi)
        {
            int mid = lo + ((hi - lo) >> 1);
            if (_words[mid].End <= range.Start)
            {
                lo = mid + 1;
            }
            else
            {
                hi = mid;
            }
        }

        for (int i = lo; i < _words.Length; i++)
        {
            var w = _words[i];
            if (w.Start >= range.End)
            {
                break;
            }
            result.Add(w);
        }

        return result;
    }

    /// <summary>
    /// 全文拼接。相邻词之间：若两词均以 CJK 字符起始/结束，则不加空格，否则加一个空格。
    /// </summary>
    public string PlainText
    {
        get
        {
            if (_words.Length == 0) return string.Empty;

            var sb = new StringBuilder(_words.Length * 4);
            sb.Append(_words[0].Text);
            for (int i = 1; i < _words.Length; i++)
            {
                string prev = _words[i - 1].Text;
                string cur = _words[i].Text;
                if (NeedsSpace(prev, cur))
                {
                    sb.Append(' ');
                }
                sb.Append(cur);
            }

            return sb.ToString();
        }
    }

    private static bool NeedsSpace(string prev, string cur)
    {
        if (prev.Length == 0 || cur.Length == 0) return false;
        char last = prev[^1];
        char first = cur[0];
        // 两侧均为 CJK 则直接拼接，不加空格。
        if (IsCjk(last) && IsCjk(first)) return false;
        return true;
    }

    private static bool IsCjk(char c)
    {
        // 常用 CJK 统一表意文字、扩展 A、兼容表意文字、日文假名、全角标点等粗略范围。
        return (c >= '\u4E00' && c <= '\u9FFF')
            || (c >= '\u3400' && c <= '\u4DBF')
            || (c >= '\uF900' && c <= '\uFAFF')
            || (c >= '\u3040' && c <= '\u30FF')
            || (c >= '\u3000' && c <= '\u303F');
    }
}
