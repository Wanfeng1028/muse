using System;
using System.Collections.Generic;
using System.Linq;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Editing;

/// <summary>
/// 单轨输入：一个 take 的名称与其转写稿。
/// </summary>
public sealed record TakeInput(string Name, TranscriptDoc Transcript);

/// <summary>
/// 单轨自然度评分结果。
/// </summary>
public sealed record TakeScore(
    string Name,
    double Score,
    int FillerCount,
    double FillerSeconds,
    int LongPauseCount,
    double WordsPerMinute);

/// <summary>
/// 多轨口误自动推荐：按自然度对多个 take 打分并排序，自动推荐最自然的一版。
/// <para>
/// 评分公式：Score = 语气词密度 + 语气词时长占比 * 100 * 0.5 + 长停顿密度 * 2.0。
/// </para>
/// <para>
/// 权重与理由：
/// 语气词密度（个/分钟）是最直接的"口误"信号，取权重 1；
/// 语气词时长占比乘以 100 换算为"每分钟等效个数"后乘 0.5，避免与密度重复计算而过度惩罚；
/// 长停顿密度（个/分钟）多对应忘词/卡壳，一次长停顿约等于两个语气词的观感，权重取 2。
/// Score 越小越自然。
/// </para>
/// </summary>
public static class TakeRecommender
{
    /// <summary>
    /// 长停顿阈值（秒）：相邻词间隔超过该值计为一次长停顿。
    /// </summary>
    public const double LongPauseThresholdSeconds = 1.5;

    /// <summary>
    /// 对多个 take 按自然度评分并升序排序（Score 越小越自然）。
    /// 返回新列表，不修改入参；并列时按 Name 序数排序保证确定性。
    /// </summary>
    public static IReadOnlyList<TakeScore> Rank(IReadOnlyList<TakeInput> takes)
    {
        ArgumentNullException.ThrowIfNull(takes);
        if (takes.Count == 0)
        {
            throw new ArgumentException("至少需要一个 take");
        }

        var results = new List<TakeScore>(takes.Count);
        foreach (var take in takes)
        {
            ArgumentNullException.ThrowIfNull(take);
            if (string.IsNullOrWhiteSpace(take.Name))
            {
                throw new ArgumentException("TakeInput.Name 不能为 null 或空白", nameof(takes));
            }

            ArgumentNullException.ThrowIfNull(take.Transcript);

            results.Add(Score(take));
        }

        results.Sort(static (a, b) =>
        {
            int byScore = a.Score.CompareTo(b.Score);
            if (byScore != 0)
            {
                return byScore;
            }

            return string.CompareOrdinal(a.Name, b.Name);
        });

        return results;
    }

    /// <summary>
    /// 返回最自然的一版，即 <see cref="Rank"/> 结果的第一项。
    /// </summary>
    public static TakeScore RecommendBest(IReadOnlyList<TakeInput> takes)
    {
        IReadOnlyList<TakeScore> ranked = Rank(takes);
        return ranked[0];
    }

    /// <summary>
    /// 生成一行中文解释，例如 "take2：综合 3.20（语气词 4 个/0.8 秒，长停顿 1 个，语速 210 词/分）"。
    /// </summary>
    public static string Explain(TakeScore score)
    {
        ArgumentNullException.ThrowIfNull(score);

        return string.Format(
            "{0}：综合 {1:F2}（语气词 {2} 个/{3:F1} 秒，长停顿 {4} 个，语速 {5:F0} 词/分）",
            score.Name,
            score.Score,
            score.FillerCount,
            score.FillerSeconds,
            score.LongPauseCount,
            score.WordsPerMinute);
    }

    /// <summary>
    /// 对单个 take 计算自然度评分。
    /// </summary>
    private static TakeScore Score(TakeInput take)
    {
        TranscriptDoc transcript = take.Transcript;

        double minutes = Math.Max(transcript.Duration.TotalMinutes, 1.0 / 60.0);

        IReadOnlyList<TimeRange> fillers = FillerWordDetector.Detect(transcript);

        int fillerCount = fillers.Count;

        double fillerSeconds = 0.0;
        for (int i = 0; i < fillers.Count; i++)
        {
            fillerSeconds += fillers[i].Duration.TotalSeconds;
        }

        double fillerDensity = fillerCount / minutes;
        double fillerRatio = transcript.Duration.TotalSeconds > 0
            ? fillerSeconds / transcript.Duration.TotalSeconds
            : 0.0;

        int longPauseCount = CountLongPauses(transcript);
        double longPauseDensity = longPauseCount / minutes;

        double wordsPerMinute = transcript.Words.Count / minutes;

        double score = fillerDensity
            + fillerRatio * 100.0 * 0.5
            + longPauseDensity * 2.0;

        return new TakeScore(
            take.Name,
            score,
            fillerCount,
            fillerSeconds,
            longPauseCount,
            wordsPerMinute);
    }

    /// <summary>
    /// 统计长停顿次数：遍历已按 Start 升序的词，相邻词间隔超过阈值计一次。
    /// </summary>
    private static int CountLongPauses(TranscriptDoc transcript)
    {
        IReadOnlyList<TranscriptWord> words = transcript.Words;
        if (words.Count < 2)
        {
            return 0;
        }

        int count = 0;
        for (int i = 0; i + 1 < words.Count; i++)
        {
            TimeSpan gap = words[i + 1].Start - words[i].End;
            if (gap.TotalSeconds > LongPauseThresholdSeconds)
            {
                count++;
            }
        }

        return count;
    }
}