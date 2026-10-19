using System;
using System.Linq;
using Xunit;
using VoxLoom.Core.Transcript;

namespace VoxLoom.Core.Tests.Transcript
{
    public class TranscriptImporterLrcDeepTests
    {
        // 事实来源：ParseLrcCore 中 if (string.IsNullOrWhiteSpace(lrc)) 之前对每行 raw.Trim() 处理，
        // string.Trim() 会去掉 \uFEFF（char.IsWhiteSpace('\uFEFF') 为 true），因此 BOM 前缀行仍能匹配标签正则 \[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]。
        // 依据 ParseLrcCore 中文本取最后一个标签之后全部内容，"[00:01.00]你好" 应解析出 2 个词，首词 Start 为 1 秒。
        [Fact]
        public void ParseLrc_BomPrefix_StrippedAndParsed()
        {
            var doc = TranscriptImporter.ParseLrc("\uFEFF[00:01.00]你好");

            Assert.Equal(2, doc.Words.Count);
            Assert.Equal(TimeSpan.FromSeconds(1), doc.Words[0].Start);
        }

        // 事实来源：ParseLrcCore 中条目按 Start 升序 Sort，第 i 个条目 end = 下一条目 Start，
        // 两条相同时间戳排序后首条目 end == 下一条目 Start == start，均分后每词时长为 0 tick，
        // 词 Start==End==1 秒。
        [Fact]
        public void ParseLrc_DuplicateTimestamps_FirstEntryZeroDuration()
        {
            var doc = TranscriptImporter.ParseLrc("[00:01.00]你\n[00:01.00]好");

            Assert.Equal(2, doc.Words.Count);
            Assert.All(doc.Words, w => Assert.Equal(w.Start, w.End));
        }

        // 事实来源：ParseLrcCore 中厘秒解析组3长度>=3取前两位 cs[..2]，
        // "[00:01.123]" 的 cs 为 "123"，取前两位 "12"，var ts = new TimeSpan(0, 0, mm, ss, centis * 10) 得 1.12 秒。
        [Fact]
        public void ParseLrc_ThreeDigitFraction_TakesFirstTwo()
        {
            var doc = TranscriptImporter.ParseLrc("[00:01.123]你好");

            Assert.Equal(TimeSpan.FromSeconds(1.12), doc.Words[0].Start);
        }

        // 事实来源：ParseLrcCore 中厘秒解析组3长度>=3取前两位 cs[..2]，
        // "[00:01.1234]" 的 cs 为 "1234"，取前两位 "12"，var ts = new TimeSpan(0, 0, mm, ss, centis * 10) 得 1.12 秒。
        [Fact]
        public void ParseLrc_FourDigitFraction_TakesFirstTwo()
        {
            var doc = TranscriptImporter.ParseLrc("[00:01.1234]你好");

            Assert.Equal(TimeSpan.FromSeconds(1.12), doc.Words[0].Start);
        }

        // 事实来源：ParseLrcCore 中标签正则 \[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\] 允许 "." 或 ":" 作分隔符，
        // "[00:01:50]" 的组3为 "50"，长度2直接用，var ts = new TimeSpan(0, 0, mm, ss, centis * 10) 得 1.5 秒。
        [Fact]
        public void ParseLrc_ColonSeparator_CentisecondsParsed()
        {
            var doc = TranscriptImporter.ParseLrc("[00:01:50]你好");

            Assert.Equal(TimeSpan.FromSeconds(1.5), doc.Words[0].Start);
        }

        // 事实来源：ParseLrcCore 中每行文本取最后一个标签之后全部内容，
        // "[00:01.00][00:02.00][00:03.00]你好" 正则匹配三个标签，文本为 "你好"，产生 3 个条目，
        // 排序后三条 Start 分别为 1/2/3 秒；每条"你好"按 SplitByCharWeight 拆 2 词，总词数 6。
        [Fact]
        public void ParseLrc_ThreeTagsOneLine_YieldsThreeEntries()
        {
            var doc = TranscriptImporter.ParseLrc("[00:01.00][00:02.00][00:03.00]你好");

            Assert.Equal(6, doc.Words.Count);
            Assert.Equal(TimeSpan.FromSeconds(1), doc.Words[0].Start);
            Assert.Equal(TimeSpan.FromSeconds(2), doc.Words[2].Start);
            Assert.Equal(TimeSpan.FromSeconds(3), doc.Words[4].Start);
        }

        // 事实来源：ParseLrcCore 中无标签行 continue，"[ti:标题]" 与 "[ar:歌手]" 不含数字标签不匹配，
        // 只有 "[00:01.00]你好" 被解析，词数 2。
        [Fact]
        public void ParseLrc_MetadataLines_Ignored()
        {
            var doc = TranscriptImporter.ParseLrc("[ti:标题]\n[ar:歌手]\n[00:01.00]你好");

            Assert.Equal(2, doc.Words.Count);
        }

        // 事实来源：ParseLrcCore 中标签正则 \[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\] 只接受半角冒号与点号，
        // "[00：01.00]" 使用全角冒号不匹配，无有效条目时 throw new TranscriptFormatException("LRC 中未找到任何有效的时间标签行。")。
        [Fact]
        public void ParseLrc_FullwidthColon_NoMatch_Throws()
        {
            Assert.Throws<TranscriptFormatException>(() => TranscriptImporter.ParseLrc("[00：01.00]你好"));
        }

        // 事实来源：ParseLrcCore 中文本取最后一个标签之后全部内容，Trim 后为空则 continue，
        // "[00:01.00]" 与 "[00:02.00]" 文本均为空被跳过，无有效条目时 throw new TranscriptFormatException("LRC 中未找到任何有效的时间标签行。")。
        [Fact]
        public void ParseLrc_TagOnlyLines_Skipped_Throws()
        {
            var ex = Assert.Throws<TranscriptFormatException>(() => TranscriptImporter.ParseLrc("[00:01.00]\n[00:02.00]"));
            Assert.Contains("未找到任何有效的时间标签行", ex.Message);
        }

        // 事实来源：ParseLrcCore 中文本取最后一个标签之后全部内容，"[吃]" 不是数字标签不匹配，
        // "[00:01.00]今天[吃]了" 文本为 "今天[吃]了"，string.Concat 词文本应等于原文。
        [Fact]
        public void ParseLrc_BracketInText_KeptInText()
        {
            var doc = TranscriptImporter.ParseLrc("[00:01.00]今天[吃]了");

            Assert.Equal("今天[吃]了", string.Concat(doc.Words.Select(w => w.Text)));
        }

        // 事实来源：ParseLrcCore 中每行 raw.Trim()，空行 continue，
        // "\n\n  \n[00:01.00]你\n\n[00:02.00]好\n" 的空白行被跳过，两条有效条目各拆 1 词，
        // 首词 Start 1 秒、末词 Start 2 秒。
        [Fact]
        public void ParseLrc_BlankLines_Skipped()
        {
            var doc = TranscriptImporter.ParseLrc("\n\n  \n[00:01.00]你\n\n[00:02.00]好\n");

            Assert.Equal(2, doc.Words.Count);
            Assert.Equal(TimeSpan.FromSeconds(1), doc.Words[0].Start);
            Assert.Equal(TimeSpan.FromSeconds(2), doc.Words[1].Start);
        }

        // 事实来源：ParseLrcCore 中 var ts = new TimeSpan(0, 0, mm, ss, centis * 10)，TimeSpan 构造允许 mm>=60 自动进位，
        // "[65:00.00]" 的 mm 为 65，得 1 小时 5 分即 3900 秒。
        [Fact]
        public void ParseLrc_MinutesOver59_CarriesToHours()
        {
            var doc = TranscriptImporter.ParseLrc("[65:00.00]你好");

            Assert.Equal(TimeSpan.FromSeconds(3900), doc.Words[0].Start);
        }
    }
}
