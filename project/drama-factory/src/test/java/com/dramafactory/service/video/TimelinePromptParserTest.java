package com.dramafactory.service.video;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * TimelinePromptParser 单元测试。
 */
class TimelinePromptParserTest {

    @Test
    void parse_basicTimeline_twoSections() {
        String script = """
                [0-10s]
                @R1 穿过安静的走廊，镜头跟随

                [10-20s]
                @R2 从右边入场，镜头转向 @R2
                """;
        List<TimelinePromptParser.TimelineSection> sections =
                TimelinePromptParser.parse(script, 2);

        assertEquals(2, sections.size());
        assertEquals(1, sections.get(0).index());
        assertEquals(0.0, sections.get(0).startSec());
        assertEquals(10.0, sections.get(0).endSec());
        assertTrue(sections.get(0).prompt().contains("穿过安静的走廊"));
        assertEquals(List.of("R1"), sections.get(0).refTags());

        assertEquals(2, sections.get(1).index());
        assertEquals(List.of("R2"), sections.get(1).refTags());
    }

    @Test
    void parse_preamble_appliesToAllSections() {
        String script = """
                电影感，暖色调

                [0-5s]
                人物走入画面

                [5-10s]
                人物坐下
                """;
        List<TimelinePromptParser.TimelineSection> sections =
                TimelinePromptParser.parse(script, 2);

        assertEquals(2, sections.size());
        assertTrue(sections.get(0).prompt().startsWith("电影感，暖色调"),
                "前言应拼到每段前面，实际: " + sections.get(0).prompt());
        assertTrue(sections.get(1).prompt().startsWith("电影感，暖色调"));
    }

    @Test
    void parse_chunkHeader_style() {
        String script = """
                [Chunk 1]
                第一段动作

                [Chunk 2]
                第二段动作
                """;
        List<TimelinePromptParser.TimelineSection> sections =
                TimelinePromptParser.parse(script, 2);
        assertEquals(2, sections.size());
        assertTrue(sections.get(0).prompt().contains("第一段动作"));
        assertTrue(sections.get(1).prompt().contains("第二段动作"));
    }

    @Test
    void parse_invalidTimeRange_throws() {
        String script = """
                [10-5s]
                时间倒流
                """;
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> TimelinePromptParser.parse(script, 1));
        assertTrue(ex.getMessage().contains("结束时间必须大于起始时间"));
    }

    @Test
    void parse_emptySection_throws() {
        String script = """
                [0-10s]

                [10-20s]
                有内容
                """;
        assertThrows(IllegalArgumentException.class,
                () -> TimelinePromptParser.parse(script, 2));
    }

    @Test
    void parse_noHeader_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> TimelinePromptParser.parse("纯文本没有时间头", 1));
    }

    @Test
    void parse_blankScript_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> TimelinePromptParser.parse("  ", 1));
    }

    @Test
    void extractRefTags_dedupAndOrder() {
        List<String> tags = TimelinePromptParser.extractRefTags(
                "@R2 先出现，@R1 后出现，@R2 又出现一次");
        assertEquals(List.of("R2", "R1"), tags);
    }

    @Test
    void extractRefTags_none() {
        assertTrue(TimelinePromptParser.extractRefTags("没有参考标记").isEmpty());
        assertTrue(TimelinePromptParser.extractRefTags(null).isEmpty());
    }

    @Test
    void hasTimelineHeader_detects() {
        assertTrue(TimelinePromptParser.hasTimelineHeader("[0-10s]\n内容"));
        assertTrue(TimelinePromptParser.hasTimelineHeader("[Chunk 1]\n内容"));
        assertTrue(!TimelinePromptParser.hasTimelineHeader("纯文本"));
        assertTrue(!TimelinePromptParser.hasTimelineHeader(null));
    }

    @Test
    void parse_autoChunkCount() {
        String script = "[0-5s]\nA\n\n[5-10s]\nB\n\n[10-15s]\nC";
        List<TimelinePromptParser.TimelineSection> sections =
                TimelinePromptParser.parse(script);
        assertEquals(3, sections.size());
    }
}
