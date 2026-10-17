package com.dramafactory;

import com.dramafactory.service.LlmScriptService;
import com.dramafactory.service.MvLyricsService;
import com.dramafactory.service.RecordingLlmScriptService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.ContextConfiguration;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = MvLyricsServiceDeepTest.TestConfig.class)
@ContextConfiguration(classes = MvLyricsServiceDeepTest.TestConfig.class)
@ExtendWith(OutputCaptureExtension.class)
class MvLyricsServiceDeepTest {

    @Configuration
    static class TestConfig {

        @Bean
        ObjectMapper objectMapper() {
            return new ObjectMapper();
        }

        @Bean
        @Primary
        LlmScriptService llmScriptService() {
            return new RecordingLlmScriptService();
        }

        @Bean
        MvLyricsService mvLyricsService(ObjectMapper objectMapper, LlmScriptService llmScriptService) {
            return new MvLyricsService(objectMapper, llmScriptService);
        }
    }

    @Autowired
    private MvLyricsService mvLyricsService;

    @Autowired
    private LlmScriptService llmScriptService;

    @Autowired
    private ObjectMapper objectMapper;

    private RecordingLlmScriptService recording;

    @BeforeEach
    void setUp() {
        recording = (RecordingLlmScriptService) llmScriptService;
        recording.nextResult.set(null);
        recording.nextFailure.set(null);
        recording.callCount.set(0);
        recording.lastRequest.set(null);
        recording.gate.set(null);
    }

    private LlmScriptService.ModelCallResult result(String content, long promptTokens, long completionTokens) {
        return new LlmScriptService.ModelCallResult(content, promptTokens, completionTokens);
    }

    private static final String VALID_JSON = "{\"title\":\"夜行\",\"sections\":["
            + "{\"name\":\"verse1\",\"lyrics\":\"第一行\\n第二行\",\"mood\":\"克制\",\"estSeconds\":25},"
            + "{\"name\":\"chorus1\",\"lyrics\":\"副歌一\\n副歌二\",\"mood\":\"释放\",\"estSeconds\":30},"
            + "{\"name\":\"verse2\",\"lyrics\":\"再一段\\n再两段\",\"mood\":\"沉\",\"estSeconds\":20},"
            + "{\"name\":\"chorus2\",\"lyrics\":\"副歌重复\\n收尾\",\"mood\":\"亮\",\"estSeconds\":35}"
            + "]}";

    @Test
    void generateReturnsParsedSectionsAndUsageTokens() {
        // given: 模型返回一段带围栏的合法 JSON，并给出 token 用量
        recording.nextResult.set(result("```json\n" + VALID_JSON + "\n```", 123L, 456L));

        // when: 调用 generate
        MvLyricsService.LyricsResult lyricsResult = mvLyricsService.generate("夜路", "克制", "民谣");

        // then: 段落被完整解析，token 用量透传，请求体结构与提示词正确
        assertEquals("夜行", lyricsResult.title());
        assertEquals(4, lyricsResult.sections().size());
        assertEquals("verse1", lyricsResult.sections().get(0).name());
        assertEquals("第一行\n第二行", lyricsResult.sections().get(0).lyrics());
        assertEquals("克制", lyricsResult.sections().get(0).mood());
        assertEquals(25, lyricsResult.sections().get(0).estSeconds());
        assertEquals(123L, lyricsResult.promptTokens());
        assertEquals(456L, lyricsResult.completionTokens());
        JsonNode request = recording.lastRequest.get();
        assertNotNull(request);
        assertEquals("deepseek-chat", request.path("model").asText());
        assertEquals(0.8, request.path("temperature").asDouble(), 0.0001);
        assertEquals(2, request.path("messages").size());
        assertEquals("system", request.path("messages").get(0).path("role").asText());
        assertTrue(request.path("messages").get(1).path("content").asText().contains("主题：夜路"));
        assertTrue(request.path("messages").get(1).path("content").asText().contains("情绪：克制"));
        assertTrue(request.path("messages").get(1).path("content").asText().contains("曲风：民谣"));
    }

    @Test
    void generateClampsEstSecondsToBoundaries() {
        // given: 模型返回的 estSeconds 低于下界、高于上界、等于边界
        String content = "{\"title\":\"边界\",\"sections\":["
                + "{\"name\":\"a\",\"lyrics\":\"词a\",\"mood\":\"m\",\"estSeconds\":1},"
                + "{\"name\":\"b\",\"lyrics\":\"词b\",\"mood\":\"m\",\"estSeconds\":999},"
                + "{\"name\":\"c\",\"lyrics\":\"词c\",\"mood\":\"m\",\"estSeconds\":5},"
                + "{\"name\":\"d\",\"lyrics\":\"词d\",\"mood\":\"m\",\"estSeconds\":60}"
                + "]}";
        recording.nextResult.set(result(content, 1L, 1L));

        // when: 调用 generate
        MvLyricsService.LyricsResult lyricsResult = mvLyricsService.generate("t", "m", "s");

        // then: 低于 5 抬到 5，高于 60 压到 60，边界值保持
        List<MvLyricsService.LyricSection> sections = lyricsResult.sections();
        assertEquals(4, sections.size());
        assertEquals(5, sections.get(0).estSeconds());
        assertEquals(60, sections.get(1).estSeconds());
        assertEquals(5, sections.get(2).estSeconds());
        assertEquals(60, sections.get(3).estSeconds());
    }

    @Test
    void generateThrowsWhenContentIsNotJson() {
        // given: 模型返回纯文本，不是 JSON
        recording.nextResult.set(result("这不是 JSON", 10L, 20L));

        // when: 调用 generate
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvLyricsService.generate("t", "m", "s"));

        // then: 抛出解析失败，且已经调过模型一次
        assertEquals("作词结果解析失败", ex.getMessage());
        assertEquals(1, recording.callCount.get());
    }

    @Test
    void generateThrowsWhenSectionsMissingOrEmpty() {
        // given: 模型返回合法 JSON 但没有 sections 数组
        recording.nextResult.set(result("{\"title\":\"空\"}", 10L, 20L));

        // when: 调用 generate
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvLyricsService.generate("t", "m", "s"));

        // then: 报解析失败，且没有返回任何结果
        assertEquals("作词结果解析失败", ex.getMessage());
        assertEquals(1, recording.callCount.get());
    }

    @Test
    void generateThrowsWhenSectionsIsEmptyArray() {
        // given: 模型返回 sections 为空数组
        recording.nextResult.set(result("{\"title\":\"空\",\"sections\":[]}", 10L, 20L));

        // when: 调用 generate
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvLyricsService.generate("t", "m", "s"));

        // then: 报解析失败，且模型只被调用一次
        assertEquals("作词结果解析失败", ex.getMessage());
        assertEquals(1, recording.callCount.get());
    }

    @Test
    void generateThrowsWhenAnySectionLyricsBlank() {
        // given: 其中一段的 lyrics 为空字符串
        String content = "{\"title\":\"缺词\",\"sections\":["
                + "{\"name\":\"a\",\"lyrics\":\"有词\",\"mood\":\"m\",\"estSeconds\":20},"
                + "{\"name\":\"b\",\"lyrics\":\"\",\"mood\":\"m\",\"estSeconds\":20}"
                + "]}";
        recording.nextResult.set(result(content, 10L, 20L));

        // when: 调用 generate
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> mvLyricsService.generate("t", "m", "s"));

        // then: 报解析失败，且模型调用次数为 1，说明没有做重试
        assertEquals("作词结果解析失败", ex.getMessage());
        assertEquals(1, recording.callCount.get());
    }

    @Test
    void generatePropagatesModelFailureAndDoesNotSwallowIt() {
        // given: 底层模型调用抛异常
        recording.nextFailure.set(new RuntimeException("上游超时"));

        // when: 调用 generate
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> mvLyricsService.generate("t", "m", "s"));

        // then: 原异常原样抛出，调用计数为 1，未设置任何返回结果
        assertEquals("上游超时", ex.getMessage());
        assertEquals(1, recording.callCount.get());
        assertEquals(null, recording.nextResult.get());
    }

    @Test
    void generateAcceptsNullThemeAndBlankMoodAndStyle() {
        // given: theme 为 null，mood 与 style 为空串
        recording.nextResult.set(result(VALID_JSON, 5L, 6L));

        // when: 调用 generate
        MvLyricsService.LyricsResult lyricsResult = mvLyricsService.generate(null, "  ", "");

        // then: 请求体里主题为空，且不包含情绪与曲风行，结果正常返回
        JsonNode request = recording.lastRequest.get();
        String userContent = request.path("messages").get(1).path("content").asText();
        assertTrue(userContent.contains("主题：\n"));
        assertFalse(userContent.contains("情绪："));
        assertFalse(userContent.contains("曲风："));
        assertEquals("夜行", lyricsResult.title());
        assertEquals(4, lyricsResult.sections().size());
    }

    @Test
    void generateTreatsSectionsWithMissingFieldsAsDefaults() {
        // given: 段落缺少 mood 与 estSeconds 字段
        String content = "{\"title\":\"缺字段\",\"sections\":["
                + "{\"name\":\"a\",\"lyrics\":\"词\"},"
                + "{\"name\":\"b\",\"lyrics\":\"词2\"}"
                + "]}";
        recording.nextResult.set(result(content, 5L, 6L));

        // when: 调用 generate
        MvLyricsService.LyricsResult lyricsResult = mvLyricsService.generate("t", "m", "s");

        // then: mood 为空串，estSeconds 默认 20，两段都在
        assertEquals(2, lyricsResult.sections().size());
        assertEquals("", lyricsResult.sections().get(0).mood());
        assertEquals(20, lyricsResult.sections().get(0).estSeconds());
        assertEquals("", lyricsResult.sections().get(1).mood());
        assertEquals(20, lyricsResult.sections().get(1).estSeconds());
    }

    @Test
    void generateIsIdempotentWhenCalledTwiceWithSameInput() {
        // given: 模型固定返回同一份内容
        recording.nextResult.set(result(VALID_JSON, 7L, 8L));

        // when: 连续调用两次 generate
        MvLyricsService.LyricsResult first = mvLyricsService.generate("夜路", "克制", "民谣");
        MvLyricsService.LyricsResult second = mvLyricsService.generate("夜路", "克制", "民谣");

        // then: 两次结果完全一致，模型被调用两次
        assertEquals(first.title(), second.title());
        assertEquals(first.sections().size(), second.sections().size());
        assertEquals(first.promptTokens(), second.promptTokens());
        assertEquals(first.completionTokens(), second.completionTokens());
        assertEquals(first.sections().get(0).lyrics(), second.sections().get(0).lyrics());
        assertEquals(2, recording.callCount.get());
    }

    @Test
    void concurrentGenerateCallsDoNotCorruptSharedState() throws Exception {
        // given: 两个线程同时推进同一个 Run 语义（同一份输入），模型返回固定内容
        recording.nextResult.set(result(VALID_JSON, 9L, 10L));
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch gate = new CountDownLatch(1);
        recording.gate.set(gate);

        Callable<MvLyricsService.LyricsResult> task = () -> {
            ready.countDown();
            ready.await(5, TimeUnit.SECONDS);
            return mvLyricsService.generate("夜路", "克制", "民谣");
        };

        try {
            Future<MvLyricsService.LyricsResult> f1 = pool.submit(task);
            Future<MvLyricsService.LyricsResult> f2 = pool.submit(task);
            assertTrue(ready.await(5, TimeUnit.SECONDS));
            gate.countDown();
            MvLyricsService.LyricsResult r1 = f1.get(10, TimeUnit.SECONDS);
            MvLyricsService.LyricsResult r2 = f2.get(10, TimeUnit.SECONDS);

            // then: 两个线程拿到一致的结果，段数、标题、歌词都对得上，没有交叉污染
            assertEquals(4, r1.sections().size());
            assertEquals(4, r2.sections().size());
            assertEquals("夜行", r1.title());
            assertEquals("夜行", r2.title());
            assertEquals(r1.sections().get(3).lyrics(), r2.sections().get(3).lyrics());
            assertEquals(2, recording.callCount.get());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void concurrentFailureInjectionKeepsCallerResultsIsolated() throws Exception {
        // given: 一个线程走成功路径，一个线程走失败路径，两者共用同一 Run 语义输入
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch gate = new CountDownLatch(1);
        recording.gate.set(gate);
        recording.nextResult.set(result(VALID_JSON, 11L, 12L));

        AtomicReference<MvLyricsService.LyricsResult> okRef = new AtomicReference<>();
        AtomicReference<RuntimeException> errRef = new AtomicReference<>();

        Callable<Void> okTask = () -> {
            ready.countDown();
            ready.await(5, TimeUnit.SECONDS);
            okRef.set(mvLyricsService.generate("夜路", "克制", "民谣"));
            return null;
        };

        Callable<Void> failTask = () -> {
            ready.countDown();
            ready.await(5, TimeUnit.SECONDS);
            try {
                mvLyricsService.generate("夜路", "克制", "民谣");
            } catch (RuntimeException e) {
                errRef.set(e);
            }
            return null;
        };

        try {
            Future<Void> f1 = pool.submit(okTask);
            Future<Void> f2 = pool.submit(failTask);
            assertTrue(ready.await(5, TimeUnit.SECONDS));
            gate.countDown();
            f1.get(10, TimeUnit.SECONDS);
            f2.get(10, TimeUnit.SECONDS);

            // then: 成功线程拿到完整结果，模型被调用两次（一次成功路径，一次失败路径），
            // 两个线程的结果互不影响
            MvLyricsService.LyricsResult ok = okRef.get();
            assertNotNull(ok);
            assertEquals("夜行", ok.title());
            assertEquals(4, ok.sections().size());
            assertEquals(11L, ok.promptTokens());
            assertEquals(12L, ok.completionTokens());
            assertEquals(2, recording.callCount.get());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void toJsonSerializesAllSectionFields() {
        // given: 模型返回合法 JSON
        recording.nextResult.set(result(VALID_JSON, 3L, 4L));
        MvLyricsService.LyricsResult lyricsResult = mvLyricsService.generate("夜路", "克制", "民谣");

        // when: 调用 toJson
        String json = mvLyricsService.toJson(lyricsResult);

        // then: JSON 里包含标题与所有段落字段
        JsonNode root;
        try {
            root = objectMapper.readTree(json);
        } catch (Exception e) {
            throw new AssertionError("toJson 输出不是合法 JSON", e);
        }
        assertEquals("夜行", root.path("title").asText());
        JsonNode sections = root.path("sections");
        assertTrue(sections.isArray());
        assertEquals(4, sections.size());
        assertEquals("verse1", sections.get(0).path("name").asText());
        assertEquals("第一行\n第二行", sections.get(0).path("lyrics").asText());
        assertEquals("克制", sections.get(0).path("mood").asText());
        assertEquals(25, sections.get(0).path("estSeconds").asInt());
        assertEquals("chorus2", sections.get(3).path("name").asText());
        assertEquals(35, sections.get(3).path("estSeconds").asInt());
    }
}
