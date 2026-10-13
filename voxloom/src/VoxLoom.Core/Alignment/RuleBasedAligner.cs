using System;
using System.Collections.Generic;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Alignment;

/// <summary>
/// 轻量规则对齐器（v1 占位，二期替换为 ONNX 声学模型）。
/// 流程：能量 VAD 检测语音段 → 按字符权重将词映射到最近的语音段。
/// </summary>
public static class RuleBasedAligner
{
    private const double FrameMs = 20.0;
    private const double HangoverMs = 200.0;
    private const double ThresholdRatio = 0.3;

    /// <summary>对粗估转写稿进行时间精修。</summary>
    public static TranscriptDoc Refine(AudioClip clip, TranscriptDoc rough)
    {
        ArgumentNullException.ThrowIfNull(clip);
        ArgumentNullException.ThrowIfNull(rough);

        if (rough.Words.Count == 0)
        {
            return rough;
        }

        var mono = clip.GetMonoSamples();
        if (mono.Length == 0)
        {
            return rough;
        }

        var segments = DetectSpeechSegments(mono, clip.SampleRate);
        if (segments.Count == 0)
        {
            // 无语音段时保持原样。
            return rough;
        }

        return RemapWords(rough, segments, clip.Duration);
    }

    private static TranscriptDoc RemapWords(TranscriptDoc rough, List<TimeRange> segments, TimeSpan clipDuration)
    {
        var words = rough.Words;
        var newWords = new List<TranscriptWord>(words.Count);

        // 为每个词分配最近的语音段：按词粗估中心与段中心距离最小者。
        // 若词中心落入某个段内，直接使用该段。
        var assign = new int[words.Count];
        for (int i = 0; i < words.Count; i++)
        {
            var w = words[i];
            var center = TimeSpan.FromTicks((w.Start.Ticks + w.End.Ticks) / 2);

            int best = 0;
            double bestDist = double.MaxValue;
            bool inside = false;

            for (int s = 0; s < segments.Count; s++)
            {
                var seg = segments[s];
                if (center >= seg.Start && center < seg.End)
                {
                    best = s;
                    inside = true;
                    break;
                }
                var segCenter = TimeSpan.FromTicks((seg.Start.Ticks + seg.End.Ticks) / 2);
                double d = Math.Abs((center - segCenter).TotalSeconds);
                if (d < bestDist)
                {
                    bestDist = d;
                    best = s;
                }
            }

            _ = inside;
            assign[i] = best;
        }

        // 按段分组并保持词序单调。
        int idx = 0;
        int segIdx = 0;
        while (idx < words.Count)
        {
            int targetSeg = assign[idx];
            // 若分配落后于当前段指针，则前进到目标段。
            if (targetSeg < segIdx) targetSeg = segIdx;
            segIdx = targetSeg;
            if (segIdx >= segments.Count) segIdx = segments.Count - 1;

            // 收集本段连续词（分配到同一段）。
            int startIdx = idx;
            while (idx < words.Count && assign[idx] <= segIdx)
            {
                idx++;
            }
            // 若该段没有词，跳过。
            if (idx == startIdx)
            {
                idx = startIdx + 1;
                continue;
            }

            var seg = segments[segIdx];
            double totalWeight = 0;
            for (int k = startIdx; k < idx; k++)
            {
                totalWeight += Math.Max(1, words[k].Text.Length);
            }
            if (totalWeight <= 0) totalWeight = 1;

            var segDur = seg.End - seg.Start;
            TimeSpan cursor = seg.Start;
            for (int k = startIdx; k < idx; k++)
            {
                double w = Math.Max(1, words[k].Text.Length) / totalWeight;
                var pieceDur = TimeSpan.FromTicks((long)(segDur.Ticks * w));
                var end = cursor + pieceDur;
                if (end > seg.End) end = seg.End;
                if (end < cursor) end = cursor;
                newWords.Add(new TranscriptWord(words[k].Text, cursor, end, words[k].Confidence));
                cursor = end;
            }
        }

        // 兜底：若有未处理词（理论上不会），保持原时间追加。
        if (newWords.Count < words.Count)
        {
            for (int i = newWords.Count; i < words.Count; i++)
            {
                newWords.Add(words[i]);
            }
        }

        return new TranscriptDoc(newWords, clipDuration);
    }

    private static List<TimeRange> DetectSpeechSegments(float[] mono, int sampleRate)
    {
        var result = new List<TimeRange>();
        if (sampleRate <= 0) return result;

        int frameSize = Math.Max(1, (int)(sampleRate * FrameMs / 1000.0));
        int frameCount = (mono.Length + frameSize - 1) / frameSize;
        if (frameCount == 0) return result;

        var rms = new double[frameCount];
        double globalSum = 0;

        for (int f = 0; f < frameCount; f++)
        {
            int start = f * frameSize;
            int end = Math.Min(start + frameSize, mono.Length);
            double sum = 0;
            for (int i = start; i < end; i++)
            {
                double v = mono[i];
                sum += v * v;
            }
            int n = end - start;
            rms[f] = n > 0 ? Math.Sqrt(sum / n) : 0;
            globalSum += rms[f];
        }

        double globalRms = globalSum / frameCount;
        double threshold = globalRms * ThresholdRatio;
        if (threshold <= 0)
        {
            // 全静音。
            return result;
        }

        int hangoverFrames = Math.Max(1, (int)(HangoverMs / FrameMs));
        int minSpeechFrames = Math.Max(1, (int)(100.0 / FrameMs));

        int speechStart = -1;
        int hangCount = 0;

        for (int f = 0; f < frameCount; f++)
        {
            bool voiced = rms[f] >= threshold;
            if (voiced)
            {
                if (speechStart < 0) speechStart = f;
                hangCount = 0;
            }
            else if (speechStart >= 0)
            {
                hangCount++;
                if (hangCount >= hangoverFrames)
                {
                    int speechEnd = f - hangCount + 1;
                    if (speechEnd - speechStart >= minSpeechFrames)
                    {
                        result.Add(FramesToRange(speechStart, speechEnd, frameSize, sampleRate, mono.Length));
                    }
                    speechStart = -1;
                    hangCount = 0;
                }
            }
        }

        if (speechStart >= 0)
        {
            int speechEnd = frameCount;
            if (speechEnd - speechStart >= minSpeechFrames)
            {
                result.Add(FramesToRange(speechStart, speechEnd, frameSize, sampleRate, mono.Length));
            }
        }

        // 合并相邻过近的段（间隔 < 200ms）。
        if (result.Count > 1)
        {
            var merged = new List<TimeRange> { result[0] };
            for (int i = 1; i < result.Count; i++)
            {
                var last = merged[^1];
                var cur = result[i];
                if (cur.Start - last.End < TimeSpan.FromMilliseconds(HangoverMs))
                {
                    merged[^1] = new TimeRange(last.Start, cur.End);
                }
                else
                {
                    merged.Add(cur);
                }
            }
            result = merged;
        }

        return result;
    }

    private static TimeRange FramesToRange(int startFrame, int endFrame, int frameSize, int sampleRate, int totalSamples)
    {
        int startSample = startFrame * frameSize;
        int endSample = Math.Min(endFrame * frameSize, totalSamples);
        if (startSample > totalSamples) startSample = totalSamples;
        if (endSample < startSample) endSample = startSample;

        double startSec = (double)startSample / sampleRate;
        double endSec = (double)endSample / sampleRate;
        return new TimeRange(TimeSpan.FromSeconds(startSec), TimeSpan.FromSeconds(endSec));
    }
}
