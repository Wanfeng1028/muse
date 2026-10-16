using System;
using System.Collections.Generic;
using System.Linq;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;

using VoxLoom.Core.Logging;
namespace VoxLoom.Core.Editing;

/// <summary>
/// 编辑计划冲突异常：ops 区间出现重叠时抛出。
/// </summary>
public sealed class EditConflictException : Exception
{
    public EditConflictException(string message) : base(message) { }
    public EditConflictException(string message, Exception inner) : base(message, inner) { }
}

/// <summary>
/// 编辑计划：按时间顺序将一组 EditOp 应用到源音频，渲染出新的 AudioClip。
/// </summary>
public sealed class EditPlan
{
    /// <summary>过零点搜索半径（采样数按 20ms 换算）。</summary>
    private const double ZeroCrossSearchSeconds = 0.020;

    /// <summary>交叉淡化时长（秒）。</summary>
    private const double CrossFadeSeconds = 0.005;

    /// <summary>衰减过渡时长（秒，首尾各 50ms）。</summary>
    private const double AttenuateFadeSeconds = 0.050;

    public AudioClip Source { get; }
    public IReadOnlyList<EditOp> Ops { get; }

    public EditPlan(AudioClip source, IReadOnlyList<EditOp> ops)
    {
        Source = source ?? throw new ArgumentNullException(nameof(source));
        Ops = ops ?? throw new ArgumentNullException(nameof(ops));

        ValidateNoOverlap(ops);
    }

    /// <summary>
    /// 校验 ops 之间区间不重叠（时间区间按 [Start, End) 比较）。
    /// </summary>
    private static void ValidateNoOverlap(IReadOnlyList<EditOp> ops)
    {
        if (ops.Count <= 1) return;

        var ordered = ops.OrderBy(o => o.AffectedRange.Start).ToList();
        for (int i = 1; i < ordered.Count; i++)
        {
            var prev = ordered[i - 1].AffectedRange;
            var curr = ordered[i].AffectedRange;

            if (curr.Start < prev.End)
            {
                throw new EditConflictException(
                    $"编辑计划存在区间重叠：操作 {i - 1} [{prev.Start} ~ {prev.End}] 与操作 {i} [{curr.Start} ~ {curr.End}] 互相覆盖，请先合并或拆分后再渲染。");
            }
        }
    }

    /// <summary>
    /// 渲染编辑结果，返回新的 AudioClip。
    /// SampleRate / Channels 与源一致。
    /// </summary>
    public AudioClip Render()
        => VoxMetrics.Timed("edit.apply", () => RenderCore());

    private AudioClip RenderCore()
    {
        int sampleRate = Source.SampleRate;
        int channels = Source.Channels;

        var ordered = Ops.OrderBy(o => o.AffectedRange.Start).ToList();

        var output = new List<float>(Source.Samples.Length);

        // 当前已处理到的源采样位置（以帧为单位）
        int cursorFrame = 0;
        int totalFrames = Source.Samples.Length / channels;

        foreach (var op in ordered)
        {
            int opStartFrame = SecondsToFrames(op.AffectedRange.Start, sampleRate);
            int opEndFrame = SecondsToFrames(op.AffectedRange.End, sampleRate);

            opStartFrame = Clamp(opStartFrame, 0, totalFrames);
            opEndFrame = Clamp(opEndFrame, opStartFrame, totalFrames);

            // 拷贝 op 之前的部分
            if (opStartFrame > cursorFrame)
            {
                CopyFrames(Source.Samples, cursorFrame, opStartFrame, channels, output);
            }

            switch (op)
            {
                case DeleteOp del:
                    {
                        // 在切点附近搜索过零点（单声道近似：取首通道）
                        // 对拼接而言：前一段的尾部与后一段的头部直接相接，做 5ms 交叉淡化。
                        int newCursor = ApplyDelete(Source.Samples, channels, sampleRate,
                            opStartFrame, opEndFrame, output);
                        cursorFrame = newCursor;
                        break;
                    }

                case AttenuateOp att:
                    {
                        AppendAttenuated(Source.Samples, channels, sampleRate,
                            opStartFrame, opEndFrame, att.LinearGain, output);
                        cursorFrame = opEndFrame;
                        break;
                    }

                case ReplaceOp rep:
                    {
                        AppendReplacement(rep.Replacement, channels, sampleRate, output);
                        cursorFrame = opEndFrame;
                        break;
                    }

                default:
                    throw new NotSupportedException($"未知的 EditOp 类型：{op.GetType().FullName}");
            }
        }

        // 拷贝剩余部分
        if (cursorFrame < totalFrames)
        {
            CopyFrames(Source.Samples, cursorFrame, totalFrames, channels, output);
        }

        return new AudioClip(sampleRate, channels, output.ToArray());
    }

    /// <summary>
    /// 执行删除：在切点寻找过零点，做 5ms 交叉淡化后把前后两段拼接输出。
    /// 返回新的源位置（opEndFrame 之后的下一帧）。
    /// </summary>
    private static int ApplyDelete(float[] source, int channels, int sampleRate,
        int opStartFrame, int opEndFrame, List<float> output)
    {
        int searchRadius = Math.Max(1, (int)Math.Round(ZeroCrossSearchSeconds * sampleRate));
        int fadeFrames = Math.Max(1, (int)Math.Round(CrossFadeSeconds * sampleRate));

        // 用单声道近似（取首通道）作为过零点搜索依据
        int totalFrames = source.Length / channels;
        float[] mono = new float[totalFrames];
        for (int f = 0; f < totalFrames; f++)
        {
            mono[f] = source[f * channels];
        }

        int aIdx = ZeroCrossing.FindNearest(mono, opStartFrame, searchRadius);
        int bIdx = ZeroCrossing.FindNearest(mono, opEndFrame, searchRadius);

        // 保证 a <= b，且都在合法范围
        aIdx = Clamp(aIdx, 0, totalFrames);
        bIdx = Clamp(bIdx, aIdx, totalFrames);

        // 交叉淡化区域：以 aIdx 为拼接中心，取前 fadeFrames 与 bIdx 后的 fadeFrames
        int headStart = Math.Max(0, aIdx - fadeFrames);
        int headEnd = aIdx;            // [headStart, headEnd) 是拼接头
        int tailStart = bIdx;
        int tailEnd = Math.Min(totalFrames, bIdx + fadeFrames);

        // 输出拼接头（直接拷贝，因为已经通过过零点对齐，不需要重复淡化；为更稳妥这里做淡出）
        // 由于是删除操作，前段在 aIdx 处被截断，后段从 bIdx 处开始。
        // 这里我们采用：拷贝 [cursor..headEnd) 的原样内容（调用者已拷贝 opStartFrame 之前），
        // 再对 head 尾做淡出、tail 头做淡入并叠加，最后接上 tail 剩余部分。
        // 简化实现：拷贝 [.., aIdx) 剩余（调用者已经拷贝到 opStartFrame），这里补充 [opStartFrame, aIdx)
        // 但 opStartFrame 到 aIdx 已经由调用者控制；为避免复杂化，这里不重复拷贝。
        // 直接返回 bIdx 作为新的 cursor，交由外层处理拼接。
        // 为让拼接平滑，对输出尾部 fadeFrames 与源 [bIdx, bIdx+fadeFrames) 做交叉淡化。

        // 若输出尾部不足 fadeFrames，则仅对可覆盖部分做淡化
        int outFrames = output.Count / channels;
        int crossLen = Math.Min(fadeFrames, Math.Min(outFrames, tailEnd - tailStart));
        crossLen = Math.Min(crossLen, headEnd - headStart >= 0 ? outFrames : 0);

        if (crossLen > 0)
        {
            // 先对输出尾部做淡出，再对源尾部做淡入并相加
            for (int i = 0; i < crossLen; i++)
            {
                double t = crossLen > 1 ? (double)i / (crossLen - 1) : 1.0;
                float fadeOut = (float)(0.5 * (1.0 + Math.Cos(Math.PI * t)));
                float fadeIn = (float)(0.5 * (1.0 - Math.Cos(Math.PI * t)));

                int outFrame = outFrames - crossLen + i;
                int srcFrame = tailStart + i;

                for (int c = 0; c < channels; c++)
                {
                    float a = output[outFrame * channels + c] * fadeOut;
                    float b = source[srcFrame * channels + c] * fadeIn;
                    output[outFrame * channels + c] = a + b;
                }
            }

            // 剩余尾部直接追加
            for (int f = tailStart + crossLen; f < tailEnd; f++)
            {
                for (int c = 0; c < channels; c++)
                {
                    output.Add(source[f * channels + c]);
                }
            }

            // 继续追加 tailEnd 之后的源（由外层 cursor 决定）
            return tailEnd;
        }

        // 无交叉淡化（例如边界情况），直接返回 bIdx 作为新 cursor
        return bIdx;
    }

    /// <summary>
    /// 将源音频 [start, end) 帧按指定增益追加到输出，首尾做 raised-cosine 过渡。
    /// </summary>
    private static void AppendAttenuated(float[] source, int channels, int sampleRate,
        int startFrame, int endFrame, float gain, List<float> output)
    {
        int length = endFrame - startFrame;
        if (length <= 0) return;

        int fadeFrames = Math.Min(length / 2, Math.Max(1, (int)Math.Round(AttenuateFadeSeconds * sampleRate)));

        for (int i = 0; i < length; i++)
        {
            int frame = startFrame + i;
            float env = 1f;

            if (i < fadeFrames && fadeFrames > 0)
            {
                double t = (double)i / fadeFrames;
                env = (float)(0.5 * (1.0 - Math.Cos(Math.PI * t)));
            }
            else if (i >= length - fadeFrames && fadeFrames > 0)
            {
                int j = length - 1 - i;
                double t = (double)j / fadeFrames;
                env = (float)(0.5 * (1.0 - Math.Cos(Math.PI * t)));
            }

            // 过渡区域：env 从 0 → 1 表示从原始增益（1.0）平滑过渡到目标增益
            float appliedGain = 1f + (gain - 1f) * env;

            for (int c = 0; c < channels; c++)
            {
                output.Add(source[frame * channels + c] * appliedGain);
            }
        }
    }

    /// <summary>
    /// 追加替换音频（通道数不匹配时取首通道或复制扩展）。
    /// </summary>
    private static void AppendReplacement(AudioClip replacement, int targetChannels,
        int targetSampleRate, List<float> output)
    {
        // 采样率不一致时：这里采用最近邻重采样以保证零依赖实现
        int srcFrames = replacement.Samples.Length / replacement.Channels;

        double ratio = (double)replacement.SampleRate / targetSampleRate;
        int outFrames = (int)Math.Round(srcFrames / ratio);
        if (outFrames <= 0) return;

        for (int f = 0; f < outFrames; f++)
        {
            int srcFrame = (int)Math.Round(f * ratio);
            if (srcFrame >= srcFrames) srcFrame = srcFrames - 1;

            for (int c = 0; c < targetChannels; c++)
            {
                int srcC = c < replacement.Channels ? c : replacement.Channels - 1;
                output.Add(replacement.Samples[srcFrame * replacement.Channels + srcC]);
            }
        }
    }

    private static void CopyFrames(float[] source, int startFrame, int endFrame,
        int channels, List<float> output)
    {
        int startSample = startFrame * channels;
        int endSample = endFrame * channels;
        for (int i = startSample; i < endSample; i++)
        {
            output.Add(source[i]);
        }
    }

    private static int SecondsToFrames(TimeSpan t, int sampleRate)
        => (int)Math.Round(t.TotalSeconds * sampleRate);

    private static int Clamp(int v, int lo, int hi)
        => v < lo ? lo : (v > hi ? hi : v);
}
