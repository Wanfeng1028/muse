using System;

namespace VoxLoom.Core.Audio;

/// <summary>
/// 波形多级 LOD（Level Of Detail）金字塔。
/// 对单声道采样构建 min/max 桶，逐级聚合，用于千万级采样点的流畅缩放渲染。
/// 构建复杂度 O(n)，单桶查询 O(1)。
/// </summary>
public sealed class WaveformLod
{
    private readonly float[][] _mins;
    private readonly float[][] _maxs;

    /// <summary>构建波形金字塔。</summary>
    /// <param name="monoSamples">单声道采样数据。</param>
    /// <param name="bucketSize">每级桶大小（聚合粒度），必须为正。</param>
    public WaveformLod(float[] monoSamples, int bucketSize = 256)
    {
        ArgumentNullException.ThrowIfNull(monoSamples);
        if (bucketSize <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(bucketSize), "桶大小必须为正整数。");
        }

        if (monoSamples.Length == 0)
        {
            _mins = Array.Empty<float[]>();
            _maxs = Array.Empty<float[]>();
            Levels = 0;
            return;
        }

        // 第 0 级：直接对原始采样按 bucketSize 分桶。
        int level0Count = (monoSamples.Length + bucketSize - 1) / bucketSize;
        var level0Min = new float[level0Count];
        var level0Max = new float[level0Count];

        for (int i = 0; i < monoSamples.Length; i++)
        {
            int b = i / bucketSize;
            float v = monoSamples[i];
            if (i % bucketSize == 0)
            {
                level0Min[b] = v;
                level0Max[b] = v;
            }
            else
            {
                if (v < level0Min[b]) level0Min[b] = v;
                if (v > level0Max[b]) level0Max[b] = v;
            }
        }

        // 逐级向上聚合，直到顶级只剩 1 个桶。
        var mins = new System.Collections.Generic.List<float[]> { level0Min };
        var maxs = new System.Collections.Generic.List<float[]> { level0Max };

        while (mins[^1].Length > 1)
        {
            var prevMin = mins[^1];
            var prevMax = maxs[^1];
            int nextCount = (prevMin.Length + bucketSize - 1) / bucketSize;
            // bucketSize=1 时 nextCount == prevMin.Length，聚合无法再收缩；
            // 不终止会导致无限循环（2026-10-19 深测发现真 bug）。
            if (nextCount >= prevMin.Length) break;
            var nextMin = new float[nextCount];
            var nextMax = new float[nextCount];

            for (int i = 0; i < prevMin.Length; i++)
            {
                int b = i / bucketSize;
                if (i % bucketSize == 0)
                {
                    nextMin[b] = prevMin[i];
                    nextMax[b] = prevMax[i];
                }
                else
                {
                    if (prevMin[i] < nextMin[b]) nextMin[b] = prevMin[i];
                    if (prevMax[i] > nextMax[b]) nextMax[b] = prevMax[i];
                }
            }

            mins.Add(nextMin);
            maxs.Add(nextMax);
        }

        _mins = mins.ToArray();
        _maxs = maxs.ToArray();
        Levels = _mins.Length;
    }

    /// <summary>金字塔层数（第 0 级为最细，级数越大越粗）。</summary>
    public int Levels { get; }

    /// <summary>获取指定级别的 min/max 桶数组。越界返回空数组。</summary>
    public (float Min, float Max)[] GetLevel(int level)
    {
        if (level < 0 || level >= Levels)
        {
            return Array.Empty<(float Min, float Max)>();
        }

        var min = _mins[level];
        var max = _maxs[level];
        var result = new (float Min, float Max)[min.Length];
        for (int i = 0; i < min.Length; i++)
        {
            result[i] = (min[i], max[i]);
        }

        return result;
    }

    /// <summary>获取指定级别的桶数量。越界返回 0。</summary>
    public int GetBucketCount(int level)
    {
        if (level < 0 || level >= Levels) return 0;
        return _mins[level].Length;
    }

    /// <summary>
    /// 获取指定级别、指定桶区间 [startBucket, startBucket+count) 的峰值。
    /// 区间会被裁剪到合法范围。返回数组长度等于实际裁剪后的桶数。
    /// </summary>
    public (float Min, float Max)[] GetPeaks(int level, int startBucket, int count)
    {
        if (level < 0 || level >= Levels || count <= 0)
        {
            return Array.Empty<(float Min, float Max)>();
        }

        var min = _mins[level];
        var max = _maxs[level];
        int total = min.Length;

        int start = startBucket;
        int end = startBucket + count;

        if (start < 0) start = 0;
        if (end > total) end = total;
        if (start >= end) return Array.Empty<(float Min, float Max)>();

        int len = end - start;
        var result = new (float Min, float Max)[len];
        for (int i = 0; i < len; i++)
        {
            result[i] = (min[start + i], max[start + i]);
        }

        return result;
    }
}
