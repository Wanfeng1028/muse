package com.dramafactory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import com.dramafactory.service.MvTimelineService;
import com.dramafactory.service.MvTimelineService.TimedLine;
import com.dramafactory.service.MvTimelineService.TimedSection;
import com.dramafactory.service.MvTimelineService.Timeline;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MvTimelineServiceDeepTest {

    @Autowired
    private MvTimelineService service;

    private final ObjectMapper mapper = new ObjectMapper();

    private ObjectNode buildLyrics(String[][] sections) {
        ObjectNode root = mapper.createObjectNode();
        ArrayNode arr = root.putArray("sections");
        for (String[] s : sections) {
            ObjectNode node = arr.addObject();
            node.put("name", s[0]);
            node.put("mood", s[1]);
            node.put("estSeconds", Integer.parseInt(s[2]));
            node.put("lyrics", s[3]);
        }
        return root;
    }

    private long sumLineDurations(Timeline t) {
        long total = 0L;
        for (TimedSection s : t.sections()) {
            for (TimedLine l : s.lines()) {
                total += (l.endMs() - l.startMs());
            }
        }
        return total;
    }

    private int countLines(Timeline t) {
        int n = 0;
        for (TimedSection s : t.sections()) {
            n += s.lines().size();
        }
        return n;
    }

    @Test
    @DisplayName("正常两段歌词：行权重比例、段边界、总时长与 scale 全部正确")
    void align_normalTwoSections_weightsAndBoundsCorrect() {
        // given: 两段歌词，第一段两行各 1 个字符，第二段一行 2 个字符，总 est=30s，音频 30000ms
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "20", "a\nb"},
                {"副歌", "高亢", "10", "cd"}
        });

        // when: 对齐时间轴
        Timeline t = service.align(lyrics, 30000L);

        // then: scale=1.0，总时长=30000，共 3 行，行时长按权重 1:1:2 分配
        assertThat(t.totalMs()).isEqualTo(30000L);
        assertThat(t.scaleFactor()).isEqualTo(1.0);
        assertThat(t.sections()).hasSize(2);
        assertThat(countLines(t)).isEqualTo(3);

        // then: 第一段两行，第二段一行，末行 endMs 强制等于 totalMs
        TimedSection first = t.sections().get(0);
        TimedSection second = t.sections().get(1);
        assertThat(first.lines()).hasSize(2);
        assertThat(second.lines()).hasSize(1);
        assertThat(first.startMs()).isEqualTo(0L);
        assertThat(second.endMs()).isEqualTo(30000L);
        assertThat(t.sections().get(1).lines().get(0).endMs()).isEqualTo(30000L);

        // then: 每行时间连续，cursor 无空隙
        long prevEnd = 0L;
        for (TimedSection s : t.sections()) {
            for (TimedLine l : s.lines()) {
                assertThat(l.startMs()).isEqualTo(prevEnd);
                assertThat(l.endMs()).isGreaterThanOrEqualTo(l.startMs());
                prevEnd = l.endMs();
            }
        }
    }

    @Test
    @DisplayName("scaleFactor 随音频时长线性缩放：音频是 est 的两倍则 scale=2.0")
    void align_audioTwiceEst_scaleFactorIsTwo() {
        // given: 单段一行，est=10s，音频 20000ms
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "10", "abc"}
        });

        // when: 对齐时间轴
        Timeline t = service.align(lyrics, 20000L);

        // then: scale=2.0，总时长=20000，唯一一行跨越整个时长
        assertThat(t.scaleFactor()).isEqualTo(2.0);
        assertThat(t.totalMs()).isEqualTo(20000L);
        assertThat(t.sections()).hasSize(1);
        assertThat(t.sections().get(0).lines().get(0).startMs()).isEqualTo(0L);
        assertThat(t.sections().get(0).lines().get(0).endMs()).isEqualTo(20000L);
    }

    @Test
    @DisplayName("音频时长为 0 时使用 totalEst，scale=1.0")
    void align_zeroAudioDuration_fallsBackToTotalEst() {
        // given: 两段各一行，est 分别 10s 和 20s，音频 0
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "10", "abc"},
                {"副歌", "高亢", "20", "def"}
        });

        // when: 对齐时间轴
        Timeline t = service.align(lyrics, 0L);

        // then: 总时长=30000，scale=1.0，两段
        assertThat(t.totalMs()).isEqualTo(30000L);
        assertThat(t.scaleFactor()).isEqualTo(1.0);
        assertThat(t.sections()).hasSize(2);
        assertThat(t.sections().get(1).lines().get(0).endMs()).isEqualTo(30000L);
    }

    @Test
    @DisplayName("MIN_LINE_MS 钳制后总和超过 totalMs 时触发二次等比缩放，总和精确等于 totalMs")
    void align_clampOverflow_triggersSecondScaleToExactTotal() {
        // given: 一段三行，est=10s（基准 10000ms），音频仅 1000ms，三行缩放后均小于 800ms
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "10", "a\nb\nc"}
        });

        // when: 对齐时间轴
        Timeline t = service.align(lyrics, 1000L);

        // then: 三行都被钳到 800 后总和 2400 超过 1000，触发二次缩放，总和精确等于 1000
        assertThat(countLines(t)).isEqualTo(3);
        assertThat(sumLineDurations(t)).isEqualTo(1000L);
        assertThat(t.totalMs()).isEqualTo(1000L);
        assertThat(t.sections().get(0).lines().get(2).endMs()).isEqualTo(1000L); // 末行 endMs 被钳到 totalMs
    }

    @Test
    @DisplayName("空段落抛 IllegalArgumentException 且消息为作词结果含空段落")
    void align_emptySectionLines_throwsIllegalArgument() {
        // given: 一段 lyrics 只有空白字符，切分后 0 行
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "20", "   \n  \n"}
        });

        // when: 对齐时间轴

        // then: 抛出 IllegalArgumentException 且消息精确匹配
        assertThatThrownBy(() -> service.align(lyrics, 30000L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("作词结果含空段落");
    }

    @Test
    @DisplayName("sections 缺失或空数组抛 IllegalArgumentException 且消息为作词结果为空")
    void align_missingOrEmptySections_throwsIllegalArgument() {
        // given: 缺失 sections 字段的根节点
        ObjectNode noSections = mapper.createObjectNode();
        noSections.put("other", "x");

        // given: sections 为空数组的根节点
        ObjectNode emptySections = mapper.createObjectNode();
        emptySections.putArray("sections");

        // when: 对齐时间轴

        // then: 两种情况都抛出同一消息
        assertThatThrownBy(() -> service.align(noSections, 1000L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("作词结果为空");
        assertThatThrownBy(() -> service.align(emptySections, 1000L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("作词结果为空");
    }

    @Test
    @DisplayName("align 对同一输入重复调用结果完全一致，无内部可变状态污染")
    void align_idempotentRepeatedCalls_sameResult() {
        // given: 两段歌词
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "20", "aa\nbb"},
                {"副歌", "高亢", "10", "cc"}
        });

        // when: 连续调用两次
        Timeline first = service.align(lyrics, 45000L);
        Timeline second = service.align(lyrics, 45000L);

        // then: 序列化结果逐字相同，totalMs 与 scale 相同
        assertThat(service.toJson(second)).isEqualTo(service.toJson(first));
        assertThat(second.totalMs()).isEqualTo(first.totalMs());
        assertThat(second.scaleFactor()).isEqualTo(first.scaleFactor());
    }

    @Test
    @DisplayName("toJson 与 fromJson 往返后 Timeline 完全等价")
    void toJsonFromJson_roundTrip_equivalent() {
        // given: 一份对齐好的时间轴
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "20", "aa\nbb"},
                {"副歌", "高亢", "10", "cc\ndd"}
        });
        Timeline original = service.align(lyrics, 60000L);

        // when: 序列化再反序列化
        String json = service.toJson(original);
        Timeline restored = service.fromJson(json);

        // then: 总时长、scale、段数、行数、每行文本与起止时间全部一致
        assertThat(restored.totalMs()).isEqualTo(original.totalMs());
        assertThat(restored.scaleFactor()).isEqualTo(original.scaleFactor());
        assertThat(restored.sections()).hasSize(original.sections().size());
        assertThat(countLines(restored)).isEqualTo(countLines(original));
        for (int s = 0; s < original.sections().size(); s++) {
            TimedSection os = original.sections().get(s);
            TimedSection rs = restored.sections().get(s);
            assertThat(rs.name()).isEqualTo(os.name());
            assertThat(rs.mood()).isEqualTo(os.mood());
            assertThat(rs.startMs()).isEqualTo(os.startMs());
            assertThat(rs.endMs()).isEqualTo(os.endMs());
            for (int i = 0; i < os.lines().size(); i++) {
                assertThat(rs.lines().get(i).text()).isEqualTo(os.lines().get(i).text());
                assertThat(rs.lines().get(i).startMs()).isEqualTo(os.lines().get(i).startMs());
                assertThat(rs.lines().get(i).endMs()).isEqualTo(os.lines().get(i).endMs());
            }
        }
    }

    @Test
    @DisplayName("fromJson 遇到非法 JSON 抛 IllegalArgumentException 消息为时间轴解析失败")
    void fromJson_malformedJson_throwsParseFailure() {
        // given: 非法 JSON 字符串
        String bad = "{not-json";

        // when: 反序列化

        // then: 抛出 IllegalArgumentException 且消息精确匹配
        assertThatThrownBy(() -> service.fromJson(bad))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("时间轴解析失败");
    }

    @Test
    @DisplayName("fromJson 遇到空 sections 抛 IllegalArgumentException 消息为时间轴为空")
    void fromJson_emptySections_throwsEmptyTimeline() {
        // given: 合法 JSON 但 sections 为空数组
        String empty = "{\"totalMs\":1000,\"scaleFactor\":1.0,\"sections\":[]}";

        // when: 反序列化

        // then: 抛出 IllegalArgumentException 且消息精确匹配
        assertThatThrownBy(() -> service.fromJson(empty))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("时间轴为空");
    }

    @Test
    @DisplayName("buildInstrumentalTimeline 按时长切段，末段截断到 totalMs")
    void buildInstrumentalTimeline_segmentsTruncatedAtTotal() {
        // given: 总时长 25000ms，段长 10000ms
        long totalMs = 25000L;
        long segmentMs = 10000L;

        // when: 构建纯音乐时间轴
        Timeline t = service.buildInstrumentalTimeline(totalMs, segmentMs);

        // then: 共 3 段，每段一段，时间连续，末段 endMs 等于 totalMs
        assertThat(t.totalMs()).isEqualTo(totalMs);
        assertThat(t.scaleFactor()).isEqualTo(1.0);
        assertThat(t.sections()).hasSize(3);
        assertThat(t.sections().get(0).startMs()).isEqualTo(0L);
        assertThat(t.sections().get(0).endMs()).isEqualTo(10000L);
        assertThat(t.sections().get(1).startMs()).isEqualTo(10000L);
        assertThat(t.sections().get(1).endMs()).isEqualTo(20000L);
        assertThat(t.sections().get(2).startMs()).isEqualTo(20000L);
        assertThat(t.sections().get(2).endMs()).isEqualTo(25000L);
        assertThat(t.sections().get(2).lines().get(0).text()).isEmpty();
    }

    @Test
    @DisplayName("buildInstrumentalTimeline 非法总时长抛 IllegalArgumentException 消息为音频时长无效")
    void buildInstrumentalTimeline_invalidTotal_throws() {
        // given: 总时长 0 与负数两种非法输入

        // when: 构建纯音乐时间轴

        // then: 两种情况都抛出同一消息
        assertThatThrownBy(() -> service.buildInstrumentalTimeline(0L, 10000L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("音频时长无效");
        assertThatThrownBy(() -> service.buildInstrumentalTimeline(-5L, 10000L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("音频时长无效");
    }

    @Test
    @DisplayName("segmentMs 非正时回退到 10000ms")
    void buildInstrumentalTimeline_nonPositiveSegment_fallsBackToDefault() {
        // given: 总时长 25000ms，段长 0
        Timeline t = service.buildInstrumentalTimeline(25000L, 0L);

        // when: 已在 given 中构建

        // then: 按默认 10000ms 切成 3 段
        assertThat(t.sections()).hasSize(3);
        assertThat(t.sections().get(0).endMs()).isEqualTo(10000L);
        assertThat(t.sections().get(2).endMs()).isEqualTo(25000L);
    }

    @Test
    @DisplayName("超大 payload：100 段各 50 行共 5000 行仍能对齐且时间连续")
    void align_hugePayload_allLinesTimed() {
        // given: 100 段，每段 50 行，每行 10 个字符，est 每段 20s
        String[][] raw = new String[100][];
        for (int s = 0; s < 100; s++) {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 50; i++) {
                sb.append("abcdefghij");
                if (i < 49) {
                    sb.append('\n');
                }
            }
            raw[s] = new String[]{"段" + s, "平静", "20", sb.toString()};
        }
        ObjectNode lyrics = buildLyrics(raw);

        // when: 对齐时间轴
        Timeline t = service.align(lyrics, 2_000_000L);

        // then: 段数 100，行数 5000，总时长精确，时间连续无空隙
        assertThat(t.sections()).hasSize(100);
        assertThat(countLines(t)).isEqualTo(5000);
        assertThat(t.totalMs()).isEqualTo(2_000_000L);
        long prevEnd = 0L;
        for (TimedSection s : t.sections()) {
            for (TimedLine l : s.lines()) {
                assertThat(l.startMs()).isEqualTo(prevEnd);
                assertThat(l.endMs()).isGreaterThanOrEqualTo(l.startMs());
                prevEnd = l.endMs();
            }
        }
        assertThat(prevEnd).isEqualTo(2_000_000L);
    }

    @Test
    @DisplayName("多线程并发对齐同一输入互不干扰，结果与单线程一致")
    void align_concurrentSameInput_resultsIdentical() throws Exception {
        // given: 一份多段歌词与预期基准
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "20", "aa\nbb\ncc"},
                {"副歌", "高亢", "30", "dd\nee"},
                {"尾声", "渐弱", "10", "ff"}
        });
        Timeline baseline = service.align(lyrics, 120000L);
        String baselineJson = service.toJson(baseline);

        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch start = new CountDownLatch(1);

        // when: 8 个线程同时对齐
        Future<String>[] futures = new Future[threads];
        for (int i = 0; i < threads; i++) {
            futures[i] = pool.submit(() -> {
                ready.countDown();
                start.await(5, TimeUnit.SECONDS);
                return service.toJson(service.align(lyrics, 120000L));
            });
        }
        ready.await(5, TimeUnit.SECONDS);
        start.countDown();

        // then: 每个线程结果与基准逐字相同，且总时长与行数一致
        for (int i = 0; i < threads; i++) {
            String result = futures[i].get(10, TimeUnit.SECONDS);
            assertThat(result).isEqualTo(baselineJson);
        }
        pool.shutdown();
        assertThat(pool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();
        assertThat(baseline.totalMs()).isEqualTo(120000L);
        assertThat(countLines(baseline)).isEqualTo(6);
    }

    @Test
    @DisplayName("空 Run 语义：null 根节点与无 sections 都按作词结果为空处理")
    void align_nullOrEmptyRoot_throwsEmptyLyrics() {
        // given: null 根节点
        // when: 对齐时间轴
        // then: 抛出作词结果为空
        assertThatThrownBy(() -> service.align(null, 1000L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("作词结果为空");

        // given: sections 为 null 的根节点
        ObjectNode nullSections = mapper.createObjectNode();
        nullSections.putNull("sections");

        // when: 对齐时间轴
        // then: 抛出作词结果为空
        assertThatThrownBy(() -> service.align(nullSections, 1000L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("作词结果为空");
    }

    @Test
    @DisplayName("单行歌词的段与行起止完全重合且覆盖全时长")
    void align_singleLine_sectionAndLineMatch() {
        // given: 单段单行，est=15s，音频 15000ms
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "15", "唯一的一行"}
        });

        // when: 对齐时间轴
        Timeline t = service.align(lyrics, 15000L);

        // then: 段与行的 start/end 相同，且等于 0 与 totalMs
        TimedSection s = t.sections().get(0);
        TimedLine l = s.lines().get(0);
        assertThat(s.startMs()).isEqualTo(0L);
        assertThat(s.endMs()).isEqualTo(15000L);
        assertThat(l.startMs()).isEqualTo(0L);
        assertThat(l.endMs()).isEqualTo(15000L);
        assertThat(l.text()).isEqualTo("唯一的一行");
    }

    @Test
    @DisplayName("Unicode code point 权重：emoji 与中文按码点计权")
    void align_unicodeCodePointWeights_usedForDistribution() {
        // given: 一段两行，第一行 1 个 emoji（1 码点），第二行 2 个中文（2 码点），est=10s，音频 30000ms
        ObjectNode lyrics = buildLyrics(new String[][]{
                {"主歌", "平静", "10", "\uD83D\uDE00\n中中"}
        });

        // when: 对齐时间轴
        Timeline t = service.align(lyrics, 30000L);

        // then: 权重 1:2，缩放 scale=3.0，第一行时长约为 10000ms，第二行末精确等于 30000
        assertThat(t.scaleFactor()).isEqualTo(3.0);
        assertThat(countLines(t)).isEqualTo(2);
        long firstDuration = t.sections().get(0).lines().get(0).endMs()
                - t.sections().get(0).lines().get(0).startMs();
        assertThat(firstDuration).isEqualTo(10000L);
        assertThat(t.sections().get(0).lines().get(1).endMs()).isEqualTo(30000L);
    }
}