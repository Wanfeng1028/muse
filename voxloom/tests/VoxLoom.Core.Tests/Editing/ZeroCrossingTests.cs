using System;
using VoxLoom.Core.Editing;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class ZeroCrossingTests
{
    [Fact]
    public void FindNearest_FindsActualZeroCrossing()
    {
        // 构造一个正弦波：采样率 1000Hz，频率 10Hz，1 秒
        int sampleRate = 1000;
        int n = sampleRate;
        double freq = 10.0;
        float[] mono = new float[n];
        for (int i = 0; i < n; i++)
        {
            mono[i] = (float)Math.Sin(2 * Math.PI * freq * i / sampleRate);
        }

        // 在索引 100 附近查找过零点；正弦周期 100 采样，过零点应在 ~0、~50、~100 等位置
        int idx = ZeroCrossing.FindNearest(mono, 100, 40);

        // 断言：找到的过零点附近采样符号应变化
        Assert.InRange(idx, 0, n - 2);
        float a = mono[idx];
        float b = mono[idx + 1];
        bool crosses = (a <= 0f && b >= 0f) || (a >= 0f && b <= 0f);
        Assert.True(crosses, $"索引 {idx} 处不是过零点：a={a}, b={b}");

        // 距离 100 应在 searchRadius 内
        Assert.True(Math.Abs(idx - 100) <= 40);
    }

    [Fact]
    public void FindNearest_NoCrossing_ReturnsOriginalIndex()
    {
        // 全为正值，无过零点
        float[] mono = new float[100];
        for (int i = 0; i < mono.Length; i++) mono[i] = 0.5f;

        int idx = ZeroCrossing.FindNearest(mono, 50, 10);
        Assert.Equal(50, idx);
    }

    [Fact]
    public void FindNearest_IndexOutOfRange_Clamped()
    {
        float[] mono = new float[10];
        mono[0] = -1f;
        mono[1] = 1f;

        int idx = ZeroCrossing.FindNearest(mono, 100, 5);
        // 索引被裁剪到 9，范围内找不到过零（因为只有 0-1 是过零，距离 9 太远）
        Assert.Equal(9, idx);
    }

    [Fact]
    public void ApplyShortFade_AttenuatesEnds()
    {
        float[] mono = new float[100];
        for (int i = 0; i < mono.Length; i++) mono[i] = 1f;

        ZeroCrossing.ApplyShortFade(mono, 0, 100);

        // 首尾应接近 0，中间应接近 1
        Assert.True(Math.Abs(mono[0]) < 0.01f, $"首采样未衰减：{mono[0]}");
        Assert.True(Math.Abs(mono[99]) < 0.01f, $"末采样未衰减：{mono[99]}");
        Assert.True(mono[50] > 0.9f, $"中间采样不应被过度衰减：{mono[50]}");
    }

    [Fact]
    public void ApplyShortFade_ZeroLength_NoOp()
    {
        float[] mono = new float[10];
        for (int i = 0; i < mono.Length; i++) mono[i] = 1f;

        ZeroCrossing.ApplyShortFade(mono, 0, 0);

        for (int i = 0; i < mono.Length; i++)
        {
            Assert.Equal(1f, mono[i]);
        }
    }
}
