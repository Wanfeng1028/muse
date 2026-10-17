using System;
using System.Collections.Generic;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing;

public class EditPlanDeepTests
{
    // 构造 4 秒单声道 16000Hz 常量信号夹具
    private static AudioClip MakeConst(int seconds, int sampleRate, int channels, float value)
    {
        int frames = seconds * sampleRate;
        var samples = new float[frames * channels];
        for (int i = 0; i < samples.Length; i++) samples[i] = value;
        return new AudioClip(sampleRate, channels, samples);
    }

    private static AudioClip MakeSine(int seconds, int sampleRate, int channels, double freq, double amp = 0.5)
    {
        int frames = seconds * sampleRate;
        var samples = new float[frames * channels];
        for (int f = 0; f < frames; f++)
        {
            float v = (float)(amp * Math.Sin(2.0 * Math.PI * freq * f / sampleRate));
            for (int c = 0; c < channels; c++) samples[f * channels + c] = v;
        }
        return new AudioClip(sampleRate, channels, samples);
    }

    [Fact]
    public void Constructor_NullSource_ThrowsArgumentNullException()
    {
        // 依据：构造 source 为 null 抛 ArgumentNullException
        Assert.Throws<ArgumentNullException>(() => new EditPlan(null!, Array.Empty<EditOp>()));
    }

    [Fact]
    public void Constructor_NullOps_ThrowsArgumentNullException()
    {
        // 依据：ops 为 null 抛 ArgumentNullException
        var src = MakeConst(1, 16000, 1, 0.1f);
        Assert.Throws<ArgumentNullException>(() => new EditPlan(src, null!));
    }

    [Fact]
    public void Constructor_Overlapping_ThrowsEditConflictException()
    {
        // 依据：按 Start 排序后 curr.Start < prev.End 抛 EditConflictException（包含关系重叠）
        var src = MakeConst(4, 16000, 1, 0.1f);
        var ops = new EditOp[]
        {
            new DeleteOp(new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(3))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2))),
        };
        Assert.Throws<EditConflictException>(() => new EditPlan(src, ops));
    }

    [Fact]
    public void Constructor_AdjacentRanges_Allowed_AndRenderDuration()
    {
        // 依据：相邻区间 [0,1) 与 [1,2) 不抛（左闭右开允许相接），Render 后时长约 2 秒
        var src = MakeConst(4, 16000, 1, 0.2f);
        var ops = new EditOp[]
        {
            new DeleteOp(new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1))),
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2))),
        };
        var plan = new EditPlan(src, ops);
        var result = plan.Render();
        Assert.Equal(16000, result.SampleRate);
        Assert.Equal(1, result.Channels);
        Assert.InRange(result.Duration.TotalSeconds, 1.9, 2.1);
    }

    [Fact]
    public void Constructor_UnsortedOps_Allowed_AndRenderDeletesBoth()
    {
        // 依据：乱序 ops（先 [2,3) 再 [0,1)）构造不抛且 Render 正确删除两段 → 时长约 2 秒
        var src = MakeConst(4, 16000, 1, 0.3f);
        var ops = new EditOp[]
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(3))),
            new DeleteOp(new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1))),
        };
        var plan = new EditPlan(src, ops);
        var result = plan.Render();
        Assert.InRange(result.Duration.TotalSeconds, 1.9, 2.1);
    }

    [Fact]
    public void ReplaceOp_Basic_DurationApproxThreeAndHalf()
    {
        // 依据：4 秒源 [1,2) 替换为 0.5 秒 → 时长约 3.5 秒（允许 ±0.1 秒）
        var src = MakeConst(4, 16000, 1, 0.2f);
        var repl = MakeConst(1, 16000, 1, 0.9f);
        // 0.5 秒替换源
        var halfSamples = new float[8000];
        for (int i = 0; i < halfSamples.Length; i++) halfSamples[i] = 0.9f;
        var replHalf = new AudioClip(16000, 1, halfSamples);

        var plan = new EditPlan(src, new EditOp[]
        {
            new ReplaceOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)), replHalf)
        });
        var result = plan.Render();
        Assert.InRange(result.Duration.TotalSeconds, 3.4, 3.6);
        // 额外确认替换源本身没被使用错误
        Assert.Equal(16000, repl.SampleRate);
    }

    [Fact]
    public void ReplaceOp_ChannelExpand_MonoToStereo_DuplicatesChannels()
    {
        // 依据：目标立体声、替换源单声道 → 输出 2 声道且两声道样本相等
        var src = MakeConst(4, 16000, 2, 0.2f);
        var replMono = MakeConst(1, 16000, 1, 0.7f);

        var plan = new EditPlan(src, new EditOp[]
        {
            new ReplaceOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)), replMono)
        });
        var result = plan.Render();
        Assert.Equal(2, result.Channels);
        Assert.Equal(16000, result.SampleRate);

        // 找到替换区段（从 1 秒开始）检查左右声道相等
        int startFrame = 16000;
        for (int f = startFrame; f < startFrame + 100; f++)
        {
            float l = result.Samples[f * 2];
            float r = result.Samples[f * 2 + 1];
            Assert.Equal(l, r, 4);
            Assert.Equal(0.7f, l, 4);
        }
    }

    [Fact]
    public void ReplaceOp_ChannelTrim_StereoToMono_TakesFirstChannel()
    {
        // 依据：目标单声道、替换源立体声 → 输出单声道取替换源首声道
        var src = MakeConst(4, 16000, 1, 0.2f);

        // 替换源：左声道全 0.8，右声道全 0.1，1 秒
        var replSamples = new float[16000 * 2];
        for (int f = 0; f < 16000; f++)
        {
            replSamples[f * 2] = 0.8f;
            replSamples[f * 2 + 1] = 0.1f;
        }
        var replStereo = new AudioClip(16000, 2, replSamples);

        var plan = new EditPlan(src, new EditOp[]
        {
            new ReplaceOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)), replStereo)
        });
        var result = plan.Render();
        Assert.Equal(1, result.Channels);

        int startFrame = 16000;
        for (int f = startFrame; f < startFrame + 100; f++)
        {
            Assert.Equal(0.8f, result.Samples[f], 4);
        }
    }

    [Fact]
    public void ReplaceOp_Resample_HalfRate_DoublesFrames()
    {
        // 依据：源 16000Hz，替换源 8000Hz 1 秒（8000 帧）→ 插入后该段约 1 秒（outFrames = 16000）
        var src = MakeConst(4, 16000, 1, 0.2f);
        var repl = MakeConst(1, 8000, 1, 0.6f);

        var plan = new EditPlan(src, new EditOp[]
        {
            new ReplaceOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)), repl)
        });
        var result = plan.Render();
        // 替换后总时长应约 4 秒（1 秒替换 1 秒）
        Assert.InRange(result.Duration.TotalSeconds, 3.9, 4.1);
        Assert.Equal(16000, result.SampleRate);
    }

    [Fact]
    public void DeleteOp_ZeroDuration_RendersUnchanged()
    {
        // 依据：零时长选区 [1s,1s) → 时长仍约 4 秒，前部样本基本不变
        var src = MakeConst(4, 16000, 1, 0.42f);
        var plan = new EditPlan(src, new EditOp[]
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1)))
        });
        var result = plan.Render();
        Assert.InRange(result.Duration.TotalSeconds, 3.95, 4.05);

        // 前部样本（前 100 帧，远在淡化窗口外）应保持 0.42
        for (int f = 0; f < 100; f++)
        {
            Assert.Equal(0.42f, result.Samples[f], 4);
        }
    }

    [Fact]
    public void DeleteOp_Head_RendersApproxThreeAndHalfSeconds()
    {
        // 依据：删除 [0, 0.5) → 时长约 3.5 秒
        var src = MakeConst(4, 16000, 1, 0.3f);
        var plan = new EditPlan(src, new EditOp[]
        {
            new DeleteOp(new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(0.5)))
        });
        var result = plan.Render();
        Assert.InRange(result.Duration.TotalSeconds, 3.4, 3.6);
    }

    [Fact]
    public void DeleteOp_Tail_RendersApproxThreeAndHalfSeconds()
    {
        // 依据：删除 [3.5, 4) → 时长约 3.5 秒
        var src = MakeConst(4, 16000, 1, 0.3f);
        var plan = new EditPlan(src, new EditOp[]
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(3.5), TimeSpan.FromSeconds(4)))
        });
        var result = plan.Render();
        Assert.InRange(result.Duration.TotalSeconds, 3.4, 3.6);
    }

    private sealed record MysteryOp(TimeRange Range) : EditOp
    {
        public override TimeRange AffectedRange => Range;
    }

    [Fact]
    public void Render_UnknownEditOp_ThrowsNotSupportedException()
    {
        // 依据：未知 EditOp 子类 → Render 抛 NotSupportedException
        var src = MakeConst(4, 16000, 1, 0.1f);
        var plan = new EditPlan(src, new EditOp[]
        {
            new MysteryOp(new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)))
        });
        Assert.Throws<NotSupportedException>(() => plan.Render());
    }

    [Fact]
    public void AttenuateOp_EndToEnd_FadeEnvelope()
    {
        // 依据：[-6dB] 作用于 [0.5s,1.5s)，区间起点 appliedGain=1（样本 ≈ 0.5），
        // 区间中点 appliedGain 目标增益 → 0.5 * 10^(-6/20) ≈ 0.2506（精度 3 位）
        var src = MakeConst(2, 16000, 1, 0.5f);
        var plan = new EditPlan(src, new EditOp[]
        {
            new AttenuateOp(new TimeRange(TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(1.5)), -6f)
        });
        var result = plan.Render();
        Assert.InRange(result.Duration.TotalSeconds, 1.95, 2.05);

        int startFrame = (int)Math.Round(0.5 * 16000);
        int midFrame = (int)Math.Round(1.0 * 16000);

        // 起点帧：appliedGain = 1 → 0.5
        Assert.Equal(0.5f, result.Samples[startFrame], 3);
        // 中点帧：目标增益已完全达到
        Assert.Equal(0.2506f, result.Samples[midFrame], 3);
        // 区间外样本不变
        Assert.Equal(0.5f, result.Samples[0], 3);
        Assert.Equal(0.5f, result.Samples[result.Samples.Length - 1], 3);
    }

    [Fact]
    public void AttenuateOp_VeryShortRange_RendersWithoutThrow()
    {
        // 依据：极短区间 0.02 秒 < 2*50ms → Render 不抛，输出时长约 2 秒
        var src = MakeConst(2, 16000, 1, 0.5f);
        var plan = new EditPlan(src, new EditOp[]
        {
            new AttenuateOp(new TimeRange(TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(0.52)), -12f)
        });
        var result = plan.Render();
        Assert.InRange(result.Duration.TotalSeconds, 1.95, 2.05);
    }

    [Fact]
    public void AttenuateOp_LinearGain_Conversions()
    {
        // 依据：LinearGain 换算 Db=-6 → ≈0.50119；Db=0 → 1.0；Db=-20 → 0.1
        var r = new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1));
        var op1 = new AttenuateOp(r, -6f);
        Assert.InRange(op1.LinearGain, 0.50118f, 0.50120f);

        var op2 = new AttenuateOp(r, 0f);
        Assert.Equal(1.0f, op2.LinearGain, 4);

        var op3 = new AttenuateOp(r, -20f);
        Assert.Equal(0.1f, op3.LinearGain, 4);
    }

    [Fact]
    public void SecondToFrameRounding_DeleteRange_MatchesExpectedFrames()
    {
        // 依据：16000Hz 下 [0.333s, 0.666s) → round(5328), round(10656)；
        // 删除该区间后时长约 4 - 0.333 = 3.667 秒（±0.05）
        var src = MakeConst(4, 16000, 1, 0.25f);
        var plan = new EditPlan(src, new EditOp[]
        {
            new DeleteOp(new TimeRange(TimeSpan.FromSeconds(0.333), TimeSpan.FromSeconds(0.666)))
        });
        var result = plan.Render();
        Assert.InRange(result.Duration.TotalSeconds, 3.617, 3.717);
    }
}
