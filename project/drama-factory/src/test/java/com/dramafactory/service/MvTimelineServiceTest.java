package com.dramafactory.service;

import java.util.List;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import com.dramafactory.service.MvTimelineService.Timeline;
import com.dramafactory.service.MvTimelineService.TimedLine;
import com.dramafactory.service.MvTimelineService.TimedSection;

class MvTimelineServiceTest {

    private JsonNode parse(String json) throws Exception {
        return new ObjectMapper().readTree(json);
    }

    private final MvTimelineService service = new MvTimelineService();

    @Test
    void testScaleFactorAndLineDurations() throws Exception {
        JsonNode root = parse("{\"title\":\"t\",\"sections\":["
                + "{\"name\":\"verse1\",\"lyrics\":\"aa\\nbbbb\\n\",\"mood\":\"m\",\"estSeconds\":10},"
                + "{\"name\":\"chorus1\",\"lyrics\":\"cc\\n\",\"mood\":\"m\",\"estSeconds\":10}]}");
        Timeline t = service.align(root, 40000L);
        Assertions.assertEquals(2.0, t.scaleFactor(), 1e-9);
        List<TimedSection> secs = t.sections();
        List<TimedLine> verse1 = secs.get(0).lines();
        Assertions.assertEquals(6667L, verse1.get(0).endMs() - verse1.get(0).startMs());
    }

    @Test
    void testAudioDurationZeroGivesScaleOne() throws Exception {
        JsonNode root = parse("{\"sections\":["
                + "{\"name\":\"v\",\"lyrics\":\"aa\\nbbbb\\n\",\"estSeconds\":10},"
                + "{\"name\":\"c\",\"lyrics\":\"cc\\n\",\"estSeconds\":10}]}");
        Timeline t = service.align(root, 0L);
        Assertions.assertEquals(1.0, t.scaleFactor(), 1e-9);
    }

    @Test
    void testAudioDurationZeroTotalMs() throws Exception {
        JsonNode root = parse("{\"sections\":["
                + "{\"name\":\"v\",\"lyrics\":\"aa\\nbbbb\\n\",\"estSeconds\":10},"
                + "{\"name\":\"c\",\"lyrics\":\"cc\\n\",\"estSeconds\":10}]}");
        Timeline t = service.align(root, 0L);
        Assertions.assertEquals(20000L, t.totalMs());
    }

    @Test
    void testBlankLinesAreDropped() throws Exception {
        JsonNode root = parse("{\"sections\":[{\"name\":\"v\",\"lyrics\":\"a\\n\\n\\nb\\n\",\"estSeconds\":10}]}");
        Timeline t = service.align(root, 0L);
        Assertions.assertEquals(2, t.sections().get(0).lines().size());
    }

    @Test
    void testEmptySectionThrows() throws Exception {
        JsonNode root = parse("{\"sections\":[{\"name\":\"v\",\"lyrics\":\"\\n\\n\",\"estSeconds\":10}]}");
        Assertions.assertThrows(IllegalArgumentException.class, () -> service.align(root, 0L));
    }

    @Test
    void testEmptySectionsThrows() throws Exception {
        JsonNode root = parse("{\"sections\":[]}");
        Assertions.assertThrows(IllegalArgumentException.class, () -> service.align(root, 0L));
    }

    @Test
    void testLastLineEndEqualsTotalMs() throws Exception {
        JsonNode root = parse("{\"sections\":[{\"name\":\"v\",\"lyrics\":\"a\\nb\\nc\\n\",\"estSeconds\":7}]}");
        Timeline t = service.align(root, 12345L);
        List<TimedLine> last = t.sections().get(t.sections().size() - 1).lines();
        Assertions.assertEquals(t.totalMs(), last.get(last.size() - 1).endMs());
    }

    @Test
    void testTinyLineClampedThenScaledBack() throws Exception {
        JsonNode root = parse("{\"sections\":[{\"name\":\"v\",\"lyrics\":\"a\\n\",\"estSeconds\":5}]}");
        Timeline t = service.align(root, 500L);
        TimedLine line = t.sections().get(0).lines().get(0);
        Assertions.assertEquals(0L, line.startMs());
        Assertions.assertEquals(500L, line.endMs());
    }

    @Test
    void testWeightRatioByCodePoints() throws Exception {
        JsonNode root = parse("{\"sections\":[{\"name\":\"v\",\"lyrics\":\"ab\\nabcd\\n\",\"estSeconds\":30}]}");
        Timeline t = service.align(root, 0L);
        List<TimedLine> lines = t.sections().get(0).lines();
        long d1 = lines.get(0).endMs() - lines.get(0).startMs();
        long d2 = lines.get(1).endMs() - lines.get(1).startMs();
        Assertions.assertEquals(2L * d1, d2, 2L);
    }

    @Test
    void testChineseWeightByCodePoints() throws Exception {
        JsonNode root = parse("{\"sections\":[{\"name\":\"v\",\"lyrics\":\"\u4f60\u597d\\n\u4f60\u597d\u4e16\u754c\\n\",\"estSeconds\":30}]}");
        Timeline t = service.align(root, 0L);
        List<TimedLine> lines = t.sections().get(0).lines();
        long d1 = lines.get(0).endMs() - lines.get(0).startMs();
        long d2 = lines.get(1).endMs() - lines.get(1).startMs();
        Assertions.assertEquals(2L * d1, d2, 2L);
    }

    @Test
    void testToJsonContainsFieldNames() throws Exception {
        JsonNode root = parse("{\"sections\":[{\"name\":\"v\",\"lyrics\":\"a\\n\",\"estSeconds\":10}]}");
        Timeline t = service.align(root, 0L);
        String json = service.toJson(t);
        Assertions.assertTrue(json.contains("\"totalMs\"")
                && json.contains("\"scaleFactor\"")
                && json.contains("\"sections\"")
                && json.contains("\"lines\"")
                && json.contains("\"text\""));
    }

    @Test
    void testShrinkMonotonicAndExactTotal() throws Exception {
        JsonNode root = parse("{\"sections\":["
                + "{\"name\":\"v\",\"lyrics\":\"a\\nb\\nc\\nd\\n\",\"estSeconds\":60}]}");
        Timeline t = service.align(root, 1000L);
        List<TimedLine> lines = t.sections().get(0).lines();
        boolean monotonic = true;
        for (int i = 1; i < lines.size(); i++) {
            if (lines.get(i).startMs() < lines.get(i - 1).endMs()) {
                monotonic = false;
                break;
            }
        }
        long lastEnd = lines.get(lines.size() - 1).endMs();
        Assertions.assertTrue(monotonic && lastEnd == t.totalMs());
    }

    @Test
    void testSectionBoundsMatchFirstAndLastLine() throws Exception {
        JsonNode root = parse("{\"sections\":["
                + "{\"name\":\"v\",\"lyrics\":\"a\\nb\\n\",\"estSeconds\":10},"
                + "{\"name\":\"c\",\"lyrics\":\"c\\nd\\n\",\"estSeconds\":10}]}");
        Timeline t = service.align(root, 20000L);
        for (TimedSection s : t.sections()) {
            List<TimedLine> lines = s.lines();
            Assertions.assertEquals(lines.get(0).startMs(), s.startMs());
            Assertions.assertEquals(lines.get(lines.size() - 1).endMs(), s.endMs());
        }
    }

    @Test
    void testEstSecondsMissingDefaultsToTwenty() throws Exception {
        JsonNode root = parse("{\"sections\":[{\"name\":\"v\",\"lyrics\":\"a\\n\"}]}");
        Timeline t = service.align(root, 0L);
        Assertions.assertEquals(20000L, t.totalMs());
    }

    @Test
    void testSectionsMissingThrows() throws Exception {
        JsonNode root = parse("{}");
        Assertions.assertThrows(IllegalArgumentException.class, () -> service.align(root, 0L));
    }
}
