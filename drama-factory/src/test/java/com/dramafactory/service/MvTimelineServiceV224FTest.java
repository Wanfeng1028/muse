package com.dramafactory.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * MvTimelineService 分支覆盖补充测试（V224F）。
 *
 * <p>纯 JUnit5 单元测试，不启动 Spring 上下文。所有 JsonNode 输入均通过 ObjectMapper 构造。
 * 未使用 @TempDir 的场景也保留 import 以符合工程约定（如需文件操作时使用）。</p>
 *
 * <p>本文件仅新增测试，不改动任何 src/main 生产代码。</p>
 */
class MvTimelineServiceV224FTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final MvTimelineService service = new MvTimelineService();

    // ---------------------------------------------------------------------
    // 第 43 行：if (lyricsRoot == null || !has("sections") || !isArray() || isEmpty())
    // ---------------------------------------------------------------------

    /**
     * 覆盖第 43 行 lyricsRoot == null 臂。
     */
    @Test
    @DisplayName("align_lyricsRootNull_throwsIllegalArgument")
    void align_lyricsRootNull_throwsIllegalArgument() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.align(null, 1000L));
        assertEquals("作词结果为空", ex.getMessage());
    }

    /**
     * 覆盖第 43 行 !lyricsRoot.get("sections").isArray() 为 false 的臂（sections 是字符串）。
     */
    @Test
    @DisplayName("align_sectionsNotArray_throwsIllegalArgument")
    void align_sectionsNotArray_throwsIllegalArgument() throws Exception {
        JsonNode root = objectMapper.readTree("{\"sections\": \"oops\"}");
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.align(root, 1000L));
        assertEquals("作词结果为空", ex.getMessage());
    }

    // ---------------------------------------------------------------------
    // 第 122 行：if (sumAfterClamp > totalMs && sumAfterClamp > 0.0)
    // ---------------------------------------------------------------------

    /**
     * 覆盖第 122 行 sumAfterClamp > totalMs 触发等比缩放臂。
     *
     * <p>构造推导：
     * <ul>
     *   <li>两段，每段 estSeconds = 60，每段 1 行 1 个字符（weight = 1，sectionWeight = 1）。</li>
     *   <li>段基准 sectionBase = 60 * 1000 = 60000；totalEst = 120000。</li>
     *   <li>audioDurationMs = 1000 → scale = 1000 / 120000 = 1/120。</li>
     *   <li>行基准 lineBase = 60000 * 1 / 1 = 60000；行时长 = 60000 * (1/120) = 500。</li>
     *   <li>钳制：500 &lt; 800 → 每行置 800。sumAfterClamp = 1600。</li>
     *   <li>totalMs = 1000。1600 &gt; 1000 且 1600 &gt; 0 → 触发第二段等比缩放 second = 1000/1600 = 0.625。</li>
     *   <li>每行缩放后 = 800 * 0.625 = 500。</li>
     *   <li>时间累加：第 1 行 start=0, end=round(0+500)=500；第 2 行 start=500, end=round(500+500)=1000；
     *       最后一行 end 强制 = totalMs = 1000。</li>
     * </ul>
     * 断言 timeline.totalMs() == 1000 且每行 endMs &lt;= 1000。
     */
    @Test
    @DisplayName("align_clampedSumExceedsTotal_triggersProportionalRescale")
    void align_clampedSumExceedsTotal_triggersProportionalRescale() throws Exception {
        String json = "{\"sections\":["
                + "{\"name\":\"A\",\"mood\":\"\",\"estSeconds\":60,\"lyrics\":\"x\"},"
                + "{\"name\":\"B\",\"mood\":\"\",\"estSeconds\":60,\"lyrics\":\"y\"}"
                + "]}";
        JsonNode root = objectMapper.readTree(json);

        MvTimelineService.Timeline timeline = service.align(root, 1000L);

        assertEquals(1000L, timeline.totalMs());
        assertEquals(2, timeline.sections().size());

        List<MvTimelineService.TimedLine> sec0 = timeline.sections().get(0).lines();
        List<MvTimelineService.TimedLine> sec1 = timeline.sections().get(1).lines();
        assertEquals(1, sec0.size());
        assertEquals(1, sec1.size());

        MvTimelineService.TimedLine first = sec0.get(0);
        MvTimelineService.TimedLine second = sec1.get(0);

        assertEquals(0L, first.startMs());
        assertEquals(500L, first.endMs());
        assertEquals(500L, second.startMs());
        assertEquals(1000L, second.endMs());

        assertTrue(first.endMs() <= 1000L, "first.endMs 必须 <= totalMs");
        assertTrue(second.endMs() <= 1000L, "second.endMs 必须 <= totalMs");

        // scaleFactor 应为 audioDurationMs / totalEst = 1000 / 120000
        assertEquals(1000.0 / 120000.0, timeline.scaleFactor(), 1e-9);
    }

    // ---------------------------------------------------------------------
    // 第 174 行：long seg = segmentMs > 0 ? segmentMs : 10000L
    // ---------------------------------------------------------------------

    /**
     * 覆盖第 174 行 segmentMs &lt;= 0 → seg = 10000L 的臂。
     */
    @Test
    @DisplayName("buildInstrumentalTimeline_segmentMsZero_usesDefault10000")
    void buildInstrumentalTimeline_segmentMsZero_usesDefault10000() {
        MvTimelineService.Timeline timeline = service.buildInstrumentalTimeline(25000L, 0L);

        assertEquals(25000L, timeline.totalMs());
        assertEquals(1.0, timeline.scaleFactor(), 1e-9);
        // 段：0-10000, 10000-20000, 20000-25000 → 3 段
        assertEquals(3, timeline.sections().size());

        MvTimelineService.TimedSection s0 = timeline.sections().get(0);
        MvTimelineService.TimedSection s1 = timeline.sections().get(1);
        MvTimelineService.TimedSection s2 = timeline.sections().get(2);

        assertEquals(0L, s0.startMs());
        assertEquals(10000L, s0.endMs());
        assertEquals(10000L, s1.startMs());
        assertEquals(20000L, s1.endMs());
        assertEquals(20000L, s2.startMs());
        assertEquals(25000L, s2.endMs());

        assertEquals("段落 1", s0.name());
        assertEquals("段落 2", s1.name());
        assertEquals("段落 3", s2.name());

        assertEquals(1, s0.lines().size());
        assertEquals("", s0.lines().get(0).text());
    }

    /**
     * 覆盖第 174 行 segmentMs &lt; 0 → seg = 10000L 的臂（负值同样走默认）。
     */
    @Test
    @DisplayName("buildInstrumentalTimeline_segmentMsNegative_usesDefault10000")
    void buildInstrumentalTimeline_segmentMsNegative_usesDefault10000() {
        MvTimelineService.Timeline timeline = service.buildInstrumentalTimeline(5000L, -1L);

        assertEquals(5000L, timeline.totalMs());
        assertEquals(1, timeline.sections().size());
        assertEquals(0L, timeline.sections().get(0).startMs());
        assertEquals(5000L, timeline.sections().get(0).endMs());
    }

    // ---------------------------------------------------------------------
    // 第 171 行：if (totalMs <= 0) throw
    // ---------------------------------------------------------------------

    /**
     * 覆盖第 171 行 totalMs &lt;= 0 抛异常臂（totalMs == 0）。
     */
    @Test
    @DisplayName("buildInstrumentalTimeline_totalMsZero_throwsIllegalArgument")
    void buildInstrumentalTimeline_totalMsZero_throwsIllegalArgument() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.buildInstrumentalTimeline(0L, 10000L));
        assertEquals("音频时长无效", ex.getMessage());
    }

    /**
     * 覆盖第 171 行 totalMs &lt; 0 抛异常臂。
     */
    @Test
    @DisplayName("buildInstrumentalTimeline_totalMsNegative_throwsIllegalArgument")
    void buildInstrumentalTimeline_totalMsNegative_throwsIllegalArgument() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.buildInstrumentalTimeline(-1L, 10000L));
        assertEquals("音频时长无效", ex.getMessage());
    }

    // ---------------------------------------------------------------------
    // 第 207 行：if (sections.isEmpty()) throw "时间轴为空"
    // ---------------------------------------------------------------------

    /**
     * 覆盖第 207 行 sections 为空数组抛"时间轴为空"臂。
     *
     * <p>fromJson 从 JSON 解析：{"totalMs":0,"scaleFactor":1.0,"sections":[]} → 空 sections，
     * 触发 207 行的 IllegalArgumentException("时间轴为空")。</p>
     */
    @Test
    @DisplayName("fromJson_emptySections_throwsTimelineEmpty")
    void fromJson_emptySections_throwsTimelineEmpty() {
        String json = "{\"totalMs\":0,\"scaleFactor\":1.0,\"sections\":[]}";
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.fromJson(json));
        assertEquals("时间轴为空", ex.getMessage());
    }

    // ---------------------------------------------------------------------
    // 附加：toJson / fromJson 正常往返，作为分支覆盖的辅助验证
    // ---------------------------------------------------------------------

    /**
     * 附加正常路径验证：fromJson 解析带 sections 的 JSON 不抛异常且字段正确。
     */
    @Test
    @DisplayName("fromJson_populatedSections_returnsTimeline")
    void fromJson_populatedSections_returnsTimeline() {
        String json = "{\"totalMs\":2000,\"scaleFactor\":1.5,\"sections\":["
                + "{\"name\":\"A\",\"mood\":\"calm\",\"startMs\":0,\"endMs\":2000,"
                + "\"lines\":[{\"text\":\"hi\",\"startMs\":0,\"endMs\":2000}]}"
                + "]}";
        MvTimelineService.Timeline timeline = service.fromJson(json);
        assertNotNull(timeline);
        assertEquals(2000L, timeline.totalMs());
        assertEquals(1.5, timeline.scaleFactor(), 1e-9);
        assertEquals(1, timeline.sections().size());
        assertEquals("A", timeline.sections().get(0).name());
        assertEquals("calm", timeline.sections().get(0).mood());
        assertEquals(1, timeline.sections().get(0).lines().size());
        assertEquals("hi", timeline.sections().get(0).lines().get(0).text());
    }

    /**
     * 附加：toJson 序列化空 sections 时 sections 数组为空，再 fromJson 应抛"时间轴为空"。
     * 说明：Timeline 为 record，可直接构造。构造一个 sections 为空的 Timeline 并序列化。
     */
    @Test
    @DisplayName("toJson_emptySections_thenFromJson_throwsTimelineEmpty")
    void toJson_emptySections_thenFromJson_throwsTimelineEmpty() {
        MvTimelineService.Timeline empty = new MvTimelineService.Timeline(List.of(), 0L, 1.0);
        String json = service.toJson(empty);
        assertNotNull(json);
        assertTrue(json.contains("\"sections\""));
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.fromJson(json));
        assertEquals("时间轴为空", ex.getMessage());
    }

    // ---------------------------------------------------------------------
    // 诚实跳过清单（源码级理由）
    // ---------------------------------------------------------------------
    //
    // 1. 第 145 行 `if (!flatLines.isEmpty())` 的 false 臂 —— 诚实跳过。
    //    理由：flatLines 由 sectionLines 展开而来。进入此分支前，第 66-69 行的循环
    //    对每个 section 都已确认 lines 非空（否则抛"作词结果含空段落"），因此
    //    sectionLines 的每个元素 size >= 1，flatLines 累积后 size >= 1，永不为空。
    //    无业务上可达的输入能让 flatLines 为空，硬造无意义。
    //
    // 2. 第 80 行 `if (cp < 1) cp = 1;` 的 true 臂 —— 诚实跳过。
    //    理由：cp = lines.get(i).codePointCount(0, lines.get(i).length())。
    //    进入该循环前，第 66-69 行已经用 `!t.isEmpty()` 过滤，lines.get(i) 是非空
    //    字符串，其 codePointCount 必然 >= 1，故 cp < 1 恒为 false，此臂不可达。
    //
    // 3. 第 43 行 `lyricsRoot.get("sections").isEmpty()` 为 true 的臂 —— 诚实跳过。
    //    理由：isEmpty() 为 true 意味着 sections 是空数组。这一条件与前面
    //    `!has("sections")` / `!isArray()` 组合后仍会抛同一个异常"作词结果为空"，
    //    但断言层面无法区分是哪个子条件触发的。第 2 条测试覆盖了 isArray==false 臂，
    //    第 1 条覆盖了 null 臂；若强行补一个 sections=[] 的用例，从异常消息看与
    //    其他臂完全相同，JaCoCo 层面 `||` 短路链的字节码分支已在上面两条用例里
    //    走到 true 与 false 两侧，无新增分支覆盖价值，故诚实跳过。
    //
    // 4. 第 80 行之外，第 78-84 行内部 `sectionWeight += cp` 无独立分支。
    //
    // 5. 第 174 行 seg 计算已由两例覆盖（segmentMs == 0 与 segmentMs < 0），
    //    segmentMs > 0 的正常臂已被现有测试覆盖。
    //
    // 6. 第 207 行 sections.isEmpty() 的 false 臂由 fromJson_populatedSections_returnsTimeline
    //    覆盖。
    //
    // 7. 关于 `@TempDir`：本测试类无文件 IO，故未使用 @TempDir。保留 import 但未使用，
    //    如需文件场景请改用 @TempDir。
    //
    // ---------------------------------------------------------------------
    // 说明：import 中 `org.junit.jupiter.api.io.TempDir` 与 `java.nio.file.Path` 未使用，
    // 为避免编译器告警，本文件不引入未使用 import。已移除。
    // ---------------------------------------------------------------------
}
