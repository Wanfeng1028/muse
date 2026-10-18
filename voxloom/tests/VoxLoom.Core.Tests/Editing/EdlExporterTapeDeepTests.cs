using System;
using System.Collections.Generic;
using VoxLoom.Core.Editing;
using VoxLoom.Core.Transcript;
using Xunit;

namespace VoxLoom.Core.Tests.Editing
{
    public class EdlExporterTapeDeepTests
    {
        private static List<(TimeRange SourceRange, TimeSpan RecordStart)> SingleEvent(TimeSpan s, TimeSpan e, TimeSpan rec)
            => new() { (new TimeRange(s, e), rec) };

        [Fact]
        public void TapeName_Whitespace_ProducesUntitled()
        {
            // 依据：string.IsNullOrWhiteSpace("   ") == true，title 取 "UNTITLED"
            var output = EdlExporter.ExportCmx3600("   ", SingleEvent(TimeSpan.Zero, TimeSpan.FromSeconds(1), TimeSpan.Zero), 48000);
            var firstLine = output.Split('\n')[0];
            Assert.Equal("TITLE: UNTITLED", firstLine);
        }

        [Fact]
        public void FourEvents_IndicesIncrementTo004()
        {
            // 依据：{0:000} 三位序号，index 从 1 起每次 ++
            var events = new List<(TimeRange, TimeSpan)>
            {
                (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)), TimeSpan.Zero),
                (new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)), TimeSpan.FromSeconds(1)),
                (new TimeRange(TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(3)), TimeSpan.FromSeconds(2)),
                (new TimeRange(TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(4)), TimeSpan.FromSeconds(3)),
            };
            var output = EdlExporter.ExportCmx3600("T", events, 48000);
            Assert.Contains("001  ", output);
            Assert.Contains("002  ", output);
            Assert.Contains("003  ", output);
            Assert.Contains("004  ", output);
        }

        [Fact]
        public void RecordContinuity_RecOutEqualsNextRecIn()
        {
            // 事件1：src [0s,1s] recStart 0s → duration=1s，recEnd=0s+1s=1s
            //   recIn=ToTimecode(0s)="00:00:00:00"，recOut=ToTimecode(1s)="00:00:01:00"
            // 事件2：src [10s,12s] recStart 1s → duration=2s，recEnd=1s+2s=3s
            //   recIn=ToTimecode(1s)="00:00:01:00"，recOut=ToTimecode(3s)="00:00:03:00"
            // 事件1 的 recOut 与事件2 的 recIn 同为 "00:00:01:00"
            var events = new List<(TimeRange, TimeSpan)>
            {
                (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)), TimeSpan.Zero),
                (new TimeRange(TimeSpan.FromSeconds(10), TimeSpan.FromSeconds(12)), TimeSpan.FromSeconds(1)),
            };
            var output = EdlExporter.ExportCmx3600("T", events, 48000);
            var lines = output.Split('\n');
            // 第0行 TITLE，第1行 FCM，第2行 001 事件行，第3行 FROM CLIP NAME，第4行 002 事件行
            // 注意：事件1 行内 "00:00:01:00" 出现两次（srcOut 与 recOut 都是 1s），
            // 事件2 行内出现一次（recIn=1s）。全输出共 3 次。
            var line1 = lines[2];
            var line2 = lines[4];
            Assert.EndsWith("00:00:01:00", line1.TrimEnd('\r'));
            Assert.Contains("00:00:01:00", line2);
            Assert.Equal(2, CountOccurrences(line1, "00:00:01:00"));
            Assert.Equal(1, CountOccurrences(line2, "00:00:01:00"));
            Assert.Equal(3, CountOccurrences(output, "00:00:01:00"));
        }

        [Fact]
        public void Over24Hours_Timecode()
        {
            // 90000 秒 → 90000/3600 = 25 小时（整数除法），分钟 (90000%3600)/60 = 0，秒 90000%60 = 0
            // srcIn = "25:00:00:00"；srcEnd = 90001s → hours 25，min 0，sec 1 → "25:00:01:00"
            var events = SingleEvent(TimeSpan.FromSeconds(90000), TimeSpan.FromSeconds(90001), TimeSpan.Zero);
            var output = EdlExporter.ExportCmx3600("T", events, 48000);
            Assert.Contains("25:00:00:00", output);
            Assert.Contains("25:00:01:00", output);
        }

        [Fact]
        public void HalfSecond_FifteenFrames()
        {
            // 0.5s → totalSeconds=0，fractional=0.5，frames=Round(0.5*30)=Round(15.0)=15
            // frames(15) < 30，不触发进位；srcOut = "00:00:00:15"
            var events = SingleEvent(TimeSpan.Zero, TimeSpan.FromSeconds(0.5), TimeSpan.Zero);
            var output = EdlExporter.ExportCmx3600("T", events, 48000);
            Assert.Contains("00:00:00:15", output);
        }

        [Fact]
        public void ClipNameLine_UsesGivenTapeName()
        {
            // 每个事件后追加 "* FROM CLIP NAME: " + title，title=tapeName
            var events = new List<(TimeRange, TimeSpan)>
            {
                (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(1)), TimeSpan.Zero),
                (new TimeRange(TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)), TimeSpan.FromSeconds(1)),
                (new TimeRange(TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(3)), TimeSpan.FromSeconds(2)),
            };
            var output = EdlExporter.ExportCmx3600("MyTape", events, 48000);
            Assert.Equal(events.Count, CountOccurrences(output, "* FROM CLIP NAME: MyTape"));
        }

        [Fact]
        public void SampleRateParam_DoesNotAffectTimecode()
        {
            // 源码中 sampleRate 未参与任何时间码计算，仅作参数传递
            var events = new List<(TimeRange, TimeSpan)>
            {
                (new TimeRange(TimeSpan.Zero, TimeSpan.FromSeconds(2)), TimeSpan.Zero),
                (new TimeRange(TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(7)), TimeSpan.FromSeconds(2)),
            };
            var a = EdlExporter.ExportCmx3600("T", events, 44100);
            var b = EdlExporter.ExportCmx3600("T", events, 48000);
            Assert.Equal(a, b);
        }

        private static int CountOccurrences(string haystack, string needle)
        {
            int count = 0;
            int i = 0;
            while ((i = haystack.IndexOf(needle, i, StringComparison.Ordinal)) >= 0)
            {
                count++;
                i += needle.Length;
            }
            return count;
        }
    }
}
