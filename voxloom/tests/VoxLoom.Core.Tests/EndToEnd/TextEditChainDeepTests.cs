using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using VoxLoom.Core.Audio;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.EndToEnd
{
    public class TextEditChainDeepTests
    {
        // 合成音频 helper：16000Hz 单声道，s[i] = 0.5f * sin(2*pi*freq*i/16000)
        static AudioClip Synth(double seconds, double freq = 440.0)
        {
            int sampleRate = 16000;
            int frames = (int)(seconds * sampleRate);
            var samples = new float[frames];
            for (int i = 0; i < frames; i++)
            {
                samples[i] = 0.5f * (float)Math.Sin(2.0 * Math.PI * freq * i / sampleRate);
            }
            return new AudioClip(sampleRate, 1, samples);
        }

        // RMS helper：对 samples[from, to) 求均方根
        static double Rms(float[] s, int from, int to)
        {
            double sum = 0.0;
            int n = to - from;
            for (int i = from; i < to; i++)
            {
                sum += s[i] * (double)s[i];
            }
            return Math.Sqrt(sum / n);
        }

        [Fact]
        public void LrcImport_FillerDetect_Attenuate_Render_EdlExport_Chain()
        {
            // 事实来源：TranscriptImporter.ParseLrc 返回 TranscriptDoc，Words 为 IReadOnlyList<TranscriptWord>
            string lrc = "[00:00.00]大家好嗯\n[00:01.00]欢迎来到工坊";
            TranscriptDoc doc = TranscriptImporter.ParseLrc(lrc);
            Assert.NotEmpty(doc.Words);

            // 事实来源：FillerWordDetector.Detect 从 TranscriptDoc 中命中语气词区间
            IReadOnlyList<TimeRange> ranges = FillerWordDetector.Detect(doc);
            Assert.True(ranges.Count >= 1);

            // 事实来源：ToAttenuateOps 对每个 TimeRange 生成一个 EditOp
            EditOp[] ops = FillerWordDetector.ToAttenuateOps(ranges);
            Assert.Equal(ranges.Count, ops.Length);

            // 事实来源：EditPlan(clip, ops).Render() 返回等价时长音频
            AudioClip clip = Synth(4.0);
            var plan = new EditPlan(clip, ops);
            AudioClip rendered = plan.Render();
            Assert.True(Math.Abs(rendered.Duration.TotalSeconds - clip.Duration.TotalSeconds) < 0.1);

            // 事实来源：EdlExporter.ExportCmx3600 生成含 "TITLE: <tape>" 的文本
            var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>();
            TimeSpan recordStart = TimeSpan.Zero;
            foreach (var op in ops)
            {
                events.Add((op.AffectedRange, recordStart));
                recordStart += TimeSpan.FromSeconds(0.1);
            }
            string edl = EdlExporter.ExportCmx3600("TAPE01", events, 16000);
            Assert.Contains("TITLE: TAPE01", edl);
        }

        [Fact]
        public void AttenuateOp_Render_ReducesRmsInsideRange_PreservesOutside()
        {
            // 事实来源：AttenuateOp(TimeRange, float) 为 sealed record，作用于 AffectedRange
            AudioClip clip = Synth(2.0, 440.0);
            var range = new TimeRange(TimeSpan.FromSeconds(0.5), TimeSpan.FromSeconds(1.5));
            var op = new AttenuateOp(range, -20f);
            var plan = new EditPlan(clip, new EditOp[] { op });
            AudioClip rendered = plan.Render();

            int sr = clip.SampleRate;
            int flatFrom = (int)(0.7 * sr);
            int flatTo = (int)(1.3 * sr);
            int outFrom = (int)(1.6 * sr);
            int outTo = (int)(1.9 * sr);

            double origFlat = Rms(clip.Samples, flatFrom, flatTo);
            double rendFlat = Rms(rendered.Samples, flatFrom, flatTo);
            Assert.True(rendFlat < 0.15 * origFlat);

            double origOut = Rms(clip.Samples, outFrom, outTo);
            double rendOut = Rms(rendered.Samples, outFrom, outTo);
            double delta = Math.Abs(rendOut - origOut) / origOut;
            Assert.True(delta < 0.05);
        }

        [Fact]
        public void EmptyRanges_ToAttenuateOps_ReturnsEmpty_AndEmptyOpsRenderEqualsOriginal()
        {
            // 事实来源：空 ranges 时 ToAttenuateOps 返回空数组
            var emptyRanges = new List<TimeRange>();
            EditOp[] ops = FillerWordDetector.ToAttenuateOps(emptyRanges);
            Assert.Empty(ops);

            // 事实来源：无 op 时 EditPlan.Render 返回等价音频样本
            AudioClip clip = Synth(1.0);
            var plan = new EditPlan(clip, ops);
            AudioClip rendered = plan.Render();
            Assert.Equal(clip.Samples.Length, rendered.Samples.Length);
            for (int i = 0; i < clip.Samples.Length; i++)
            {
                Assert.Equal(clip.Samples[i], rendered.Samples[i]);
            }
        }

        [Fact]
        public void ExportCmx3600_WithZeroEvents_StillReturnsValidText()
        {
            // 事实来源：EDL 事件为 0 时 ExportCmx3600 仍返回含 TITLE 的文本
            var events = new List<(TimeRange SourceRange, TimeSpan RecordStart)>();
            string edl = EdlExporter.ExportCmx3600("TAPE00", events, 16000);
            Assert.Contains("TITLE", edl);
        }
    }
}
