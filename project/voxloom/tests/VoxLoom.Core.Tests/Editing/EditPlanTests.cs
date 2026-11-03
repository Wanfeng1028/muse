using System;
using System.Collections.Generic;
using System.Linq;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EditPlanTests
{
    /// <summary>
    /// 合成 4 秒音频：每秒不同频率正弦，便于区分各段内容。
    /// 采样率 16000Hz，单声道。
    /// </summary>
    private static AudioClip MakeFourSecondClip(int sampleRate = 16000)
    {
        int channels = 1;
        int totalSamples = sampleRate * 4;
        float[] samples = new float[totalSamples];

        double[] freqs = { 200.0, 400.0, 800.0, 1600.0 };
        for (int sec = 0; sec < 4; sec++)
        {
            int start = sec * sampleRate;
            int end = start + sampleRate;
            double f = freqs[sec];
            for (int i = start; i < end; i++)
            {
                samples[i] = (float)(0.5 * Math.Sin(2 * Math.PI * f * (i - start) / sampleRate));
            }
        }

        return new AudioClip(sampleRate, channels, samples);
    }

    [Fact]
    public void Delete_SecondSecond_Produces3SecondClip()
    {
        var clip = MakeFourSecondClip();
        var plan = new EditPlan(clip, new EditOp[]
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)))
        });

        var result = plan.Render();

        Assert.Equal(clip.SampleRate, result.SampleRate);
        Assert.Equal(clip.Channels, result.Channels);

        double expectedSeconds = 3.0;
        double actualSeconds = result.Duration.TotalSeconds;

        // 允许一定误差（过零点对齐与交叉淡化带来的少量偏差）
        Assert.InRange(actualSeconds, expectedSeconds - 0.1, expectedSeconds + 0.1);

        // 检查拼接处：第 1 秒末尾（~200Hz）应与第 3 秒开头（~800Hz）直接相接
        // 简单验证总样本数合理
        Assert.True(Math.Abs(result.Samples.Length - 3 * clip.SampleRate) < clip.SampleRate * 0.1);
    }

    [Fact]
    public void OverlappingOps_ThrowsEditConflictException()
    {
        var clip = MakeFourSecondClip();

        var ex = Assert.Throws<EditConflictException>(() =>
            new EditPlan(clip, new EditOp[]
            {
                new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2))),
                new AttenuateOp(new TimeRange(TimeSpan.FromSeconds(1.5), TimeSpan.FromSeconds(2.5)), -12f)
            }));

        Assert.Contains("重叠", ex.Message);
    }

    [Fact]
    public void Attenuate_ReducesRmsInTargetRange_AndKeepsOthers()
    {
        // 使用恒定振幅信号以便测量 RMS
        int sampleRate = 16000;
        int channels = 1;
        int totalSamples = sampleRate * 3;
        float[] samples = new float[totalSamples];
        for (int i = 0; i < totalSamples; i++)
        {
            samples[i] = 0.5f * (float)Math.Sin(2 * Math.PI * 440.0 * i / sampleRate);
        }
        var clip = new AudioClip(sampleRate, channels, samples);

        var plan = new EditPlan(clip, new EditOp[]
        {
            new AttenuateOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)), -12f)
        });

        var result = plan.Render();
        Assert.Equal(clip.Samples.Length, result.Samples.Length);

        // 目标区间中段（避开 50ms 过渡）RMS 应明显下降
        // 目标区间为 [1s, 2s)，取 [1.25s, 1.75s) 完全落在目标区内
        double targetRms = Rms(result.Samples, sampleRate * 5 / 4, sampleRate / 2);
        double outsideRms = Rms(result.Samples, 0, sampleRate / 2);        // [0s, 0.5s)

        // 原始 RMS 约 0.353（0.5/√2）；-12dB 后约 0.0888
        Assert.True(targetRms < 0.15, $"目标区间 RMS 未下降：{targetRms}");
        Assert.True(outsideRms > 0.25, $"非目标区间 RMS 被意外改变：{outsideRms}");
    }

    private static double Rms(float[] samples, int start, int count)
    {
        double sum = 0;
        for (int i = start; i < start + count; i++)
        {
            sum += samples[i] * samples[i];
        }
        return Math.Sqrt(sum / count);
    }
}
