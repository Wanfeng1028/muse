using System;

namespace VoxLoom.Core.Editing;

/// <summary>
/// 过零点工具：用于在剪辑点寻找合适的采样位置，避免波形突变产生爆音。
/// </summary>
public static class ZeroCrossing
{
    /// <summary>
    /// 在 [index-searchRadius, index+searchRadius] 范围内寻找最接近 index 的过零点索引。
    /// 过零点定义为相邻两个采样符号不同（含 0 情况视为符号变化）。
    /// 若找不到则返回裁剪到合法范围的 index。
    /// </summary>
    public static int FindNearest(float[] mono, int index, int searchRadius)
    {
        ArgumentNullException.ThrowIfNull(mono);

        if (mono.Length == 0)
        {
            return 0;
        }

        // 裁剪到合法范围
        if (index < 0) index = 0;
        if (index >= mono.Length) index = mono.Length - 1;

        if (searchRadius <= 0 || mono.Length < 2)
        {
            return index;
        }

        int lo = Math.Max(0, index - searchRadius);
        int hi = Math.Min(mono.Length - 2, index + searchRadius);

        int bestIndex = index;
        int bestDistance = int.MaxValue;

        for (int i = lo; i <= hi; i++)
        {
            float a = mono[i];
            float b = mono[i + 1];

            // 符号变化：严格异号，或其中一个恰为 0 而另一个非 0。
            // 注意 (0,0) 不算过零——否则全静音段处处都是"过零点"。
            bool crosses = (a < 0f && b >= 0f) || (a > 0f && b <= 0f) || (a == 0f && b != 0f);
            if (!crosses) continue;

            int distance = Math.Abs(i - index);
            if (distance < bestDistance)
            {
                bestDistance = distance;
                bestIndex = i;
            }
        }

        return bestIndex;
    }

    /// <summary>
    /// 在 [start, start+length) 区间做 raised-cosine 淡入淡出。
    /// 前半段淡入，后半段淡出，用于拼接点平滑，消除爆音。
    /// length &lt;= 0 时无操作。
    /// </summary>
    public static void ApplyShortFade(float[] mono, int start, int length)
    {
        ArgumentNullException.ThrowIfNull(mono);

        if (length <= 0) return;

        // 裁剪到数组边界
        int s = Math.Max(0, start);
        int e = Math.Min(mono.Length, start + length);
        int n = e - s;
        if (n <= 0) return;

        int half = n / 2;

        // 淡入（前一半）
        for (int i = 0; i < half; i++)
        {
            double t = half > 0 ? (double)i / half : 0.0;
            float gain = (float)(0.5 * (1.0 - Math.Cos(Math.PI * t)));
            mono[s + i] *= gain;
        }

        // 淡出（后一半）
        int fadeOutStart = s + half;
        int fadeOutLen = n - half;
        for (int i = 0; i < fadeOutLen; i++)
        {
            double t = fadeOutLen > 1 ? (double)i / (fadeOutLen - 1) : 1.0;
            float gain = (float)(0.5 * (1.0 + Math.Cos(Math.PI * t)));
            mono[fadeOutStart + i] *= gain;
        }
    }
}
