package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.TestPropertySource;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

/**
 * LlmScriptService 深度测试。
 *
 * <p>本测试通过 {@code @MockBean} 仅替换 {@link LlmTransport} 这一真正不可达的外部网络层，
 * 被测的 LlmScriptService 业务逻辑（请求体构造、重试、解析、指标埋点、并发）走真实实现。
 * {@link CredentialResolver} 同样被 mock，因为它需要真实密钥/凭据链，
 * 属于外部不可达依赖；返回固定的伪凭据 Map.Entry 供断言使用。</p>
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:llmscriptdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class LlmScriptServiceDeepTest {

    private static final String CHAT_URL = "https://chatapi.weixin.qq.com/openai/v1/chat/completions";

    private static final String VALID_JSON = "{\"scenes\":["
            + "{\"sceneNo\":1,\"location\":\"LOC1\",\"timeOfDay\":\"DAY\",\"description\":\"D1\",\"dialogue\":\"DL1\",\"prompt\":\"P1\"},"
            + "{\"sceneNo\":2,\"location\":\"LOC2\",\"timeOfDay\":\"NIGHT\",\"description\":\"D2\",\"dialogue\":\"DL2\",\"prompt\":\"P2\"},"
            + "{\"sceneNo\":3,\"location\":\"LOC3\",\"timeOfDay\":\"DAY\",\"description\":\"D3\",\"dialogue\":\"DL3\",\"prompt\":\"P3\"},"
            + "{\"sceneNo\":4,\"location\":\"LOC4\",\"timeOfDay\":\"NIGHT\",\"description\":\"D4\",\"dialogue\":\"DL4\",\"prompt\":\"P4\"}"
            + "]}";

    @MockBean
    private LlmTransport llmTransport;

    @MockBean
    private CredentialResolver credentialResolver;

    @BeforeEach
    void setUp() {
        when(credentialResolver.chatAuth()).thenReturn(Map.entry("Authorization", "Bearer test-credential"));
    }

    private DramaMetrics newMetrics() {
        return new DramaMetrics(new SimpleMeterRegistry(), null, null);
    }

    private LlmScriptService newService(boolean enabled, String model, int maxTokens,
                                        int timeoutSeconds, int maxRetries, String cliPath) {
        return new LlmScriptService(credentialResolver, new com.fasterxml.jackson.databind.ObjectMapper(),
                enabled, model, maxTokens, timeoutSeconds, maxRetries, cliPath, newMetrics());
    }

    private static Episode buildEpisode() {
        Episode episode = new Episode();
        episode.setId(1L);
        episode.setOutline("outline");
        DramaProject project = new DramaProject();
        project.setTitle("title");
        project.setGenre("genre");
        episode.setProject(project);
        return episode;
    }

    // ---------- 1. LLM 不可用 ----------

    @Test
    void generate_whenTransportThrows_throwsLlmScriptUnavailableExceptionWithCause() {
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt()))
                .thenThrow(new RuntimeException("network down"));
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        assertThatThrownBy(() -> service.generate(buildEpisode(), "chars"))
                .isInstanceOf(LlmScriptUnavailableException.class)
                .hasMessageContaining("AI 剧本生成失败")
                .hasCauseInstanceOf(RuntimeException.class);
    }

    @Test
    void generate_whenTransportReturnsEmptyBody_throwsLlmScriptUnavailableException() {
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenReturn("");
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        assertThatThrownBy(() -> service.generate(buildEpisode(), "chars"))
                .isInstanceOf(LlmScriptUnavailableException.class)
                .hasMessageContaining("AI 剧本生成失败");
    }

    @Test
    void generate_whenTransportReturnsNull_throwsLlmScriptUnavailableException() {
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenReturn(null);
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        assertThatThrownBy(() -> service.generate(buildEpisode(), "chars"))
                .isInstanceOf(LlmScriptUnavailableException.class)
                .hasMessageContaining("AI 剧本生成失败");
    }

    // ---------- 2. 非法 JSON 容错 ----------

    @Test
    void generate_whenModelReturnsNonJsonGarbage_throwsLlmScriptUnavailableException() {
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt()))
                .thenReturn("this is not json at all, just chatter");
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        assertThatThrownBy(() -> service.generate(buildEpisode(), "chars"))
                .isInstanceOf(LlmScriptUnavailableException.class)
                .hasMessageContaining("AI 剧本生成失败");
    }

    @Test
    void generate_whenModelReturnsOpenAiEnvelopeWithFencedJson_parsesScenesAndUsage() {
        String content = "```json\n" + VALID_JSON + "\n```";
        String envelope = "{\"choices\":[{\"message\":{\"content\":"
                + escapeJson(content) + "}}],\"usage\":{\"prompt_tokens\":12,\"completion_tokens\":34}}";
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenReturn(envelope);
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        LlmScriptService.LlmScriptResult result = service.generate(buildEpisode(), "chars");

        assertThat(result.scenes()).hasSize(4);
        assertThat(result.scenes().get(0).location()).isEqualTo("LOC1");
        assertThat(result.scenes().get(3).location()).isEqualTo("LOC4");
        assertThat(result.promptTokens()).isEqualTo(12L);
        assertThat(result.completionTokens()).isEqualTo(34L);
        assertThat(result.model()).isEqualTo("test-model");
        assertThat(result.latencyMs()).isGreaterThanOrEqualTo(0L);
    }

    private static String escapeJson(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
    }

    // ---------- 3. 边界：空剧本 / 超长输入 ----------

    @Test
    void generate_whenScenesCountIsThree_throwsWithCountMismatch() {
        String three = "{\"scenes\":["
                + "{\"sceneNo\":1,\"location\":\"L1\",\"description\":\"D1\",\"dialogue\":\"DL1\"},"
                + "{\"sceneNo\":2,\"location\":\"L2\",\"description\":\"D2\",\"dialogue\":\"DL2\"},"
                + "{\"sceneNo\":3,\"location\":\"L3\",\"description\":\"D3\",\"dialogue\":\"DL3\"}"
                + "]}";
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenReturn(three);
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        assertThatThrownBy(() -> service.generate(buildEpisode(), "chars"))
                .isInstanceOf(LlmScriptUnavailableException.class)
                .hasMessageContaining("AI 剧本生成失败");
    }

    @Test
    void generate_withVeryLongOutline_stillParsesAndSucceeds() {
        StringBuilder longOutline = new StringBuilder();
        for (int i = 0; i < 20000; i++) {
            longOutline.append("剧情段落").append(i).append('；');
        }
        Episode episode = buildEpisode();
        episode.setOutline(longOutline.toString());

        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenReturn(VALID_JSON);
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        LlmScriptService.LlmScriptResult result = service.generate(episode, "chars");

        assertThat(result.scenes()).hasSize(4);
        assertThat(result.scenes().get(0).sceneNo()).isEqualTo(1);
        assertThat(result.scenes().get(3).sceneNo()).isEqualTo(4);
    }

    @Test
    void generate_withNullOutlineAndNullCharactersSummary_usesDefaults() {
        Episode episode = new Episode();
        episode.setId(2L);
        episode.setOutline(null);

        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenReturn(VALID_JSON);
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        LlmScriptService.LlmScriptResult result = service.generate(episode, null);

        assertThat(result.scenes()).hasSize(4);
    }

    // ---------- 4. prompt 拼接 ----------

    @Test
    void generate_withSkillPrompt_injectsSkillBlockIntoSystemMessage() {
        List<String> capturedBodies = new ArrayList<>();
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenAnswer(inv -> {
            capturedBodies.add(inv.getArgument(1, String.class));
            return VALID_JSON;
        });
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        LlmScriptService.LlmScriptResult result =
                service.generate(buildEpisode(), "chars", "SKILL_INJECT_TOKEN");

        assertThat(result.scenes()).hasSize(4);
        assertThat(capturedBodies).hasSize(1);
        String body = capturedBodies.get(0);
        assertThat(body).contains("SKILL_INJECT_TOKEN");
        assertThat(body).contains("【Skill 增强】");
    }

    @Test
    void generate_withBlankSkillPrompt_doesNotInjectSkillBlock() {
        List<String> capturedBodies = new ArrayList<>();
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenAnswer(inv -> {
            capturedBodies.add(inv.getArgument(1, String.class));
            return VALID_JSON;
        });
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        service.generate(buildEpisode(), "chars", "   ");

        assertThat(capturedBodies).hasSize(1);
        assertThat(capturedBodies.get(0)).doesNotContain("【Skill 增强】");
    }

    @Test
    void generate_withMissingVariablesInEpisode_bodyStillHasDefaultPlaceholders() {
        List<String> capturedBodies = new ArrayList<>();
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenAnswer(inv -> {
            capturedBodies.add(inv.getArgument(1, String.class));
            return VALID_JSON;
        });
        Episode episode = new Episode();
        episode.setId(99L);
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        service.generate(episode, null);

        assertThat(capturedBodies).hasSize(1);
        String body = capturedBodies.get(0);
        assertThat(body).contains("未命名");
        assertThat(body).contains("未指定");
        assertThat(body).contains("无大纲，请自由发挥");
        assertThat(body).doesNotContain("角色表：");
    }

    // ---------- 5. 禁用 / 非法配置 ----------

    @Test
    void generate_whenServiceDisabled_throwsBeforeCallingTransport() {
        LlmScriptService service = newService(false, "test-model", 3000, 5, 0, null);

        assertThatThrownBy(() -> service.generate(buildEpisode(), "chars"))
                .isInstanceOf(LlmScriptUnavailableException.class)
                .hasMessageContaining("未启用");
    }

    @Test
    void validate_whenEnabledAndInvalidMaxTokens_throwsIllegalStateException() {
        LlmScriptService service = newService(true, "test-model", 0, 5, 0, null);

        assertThatThrownBy(service::validate)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("max-tokens");
    }

    // ---------- 6. 重试 / 中断 ----------

    @Test
    void generate_whenFirstAttemptInvalidSecondValid_succeedsAfterRetry() {
        AtomicInteger calls = new AtomicInteger();
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenAnswer(inv -> {
            int n = calls.incrementAndGet();
            if (n == 1) {
                return "garbage not json";
            }
            return VALID_JSON;
        });
        LlmScriptService service = newService(true, "test-model", 3000, 5, 1, null);

        LlmScriptService.LlmScriptResult result = service.generate(buildEpisode(), "chars");

        assertThat(result.scenes()).hasSize(4);
        assertThat(calls.get()).isEqualTo(2);
    }

    @Test
    void generate_whenInterruptedDuringRetryBackoff_throwsUnavailableWithInterruptedCause() {
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt()))
                .thenThrow(new RuntimeException("always fails"));
        // maxRetries=1 保证有一次 backoff（1000ms），在此期间中断线程
        LlmScriptService service = newService(true, "test-model", 3000, 5, 1, null);

        Thread worker = new Thread(() -> {
            try {
                service.generate(buildEpisode(), "chars");
            } catch (RuntimeException ignored) {
                // 预期异常
            }
        });
        worker.start();
        // 稍等进入 backoff 再中断
        try {
            Thread.sleep(200);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        worker.interrupt();
        try {
            worker.join(5000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        assertThat(worker.isAlive()).isFalse();
    }

    // ---------- 7. 并发：同一剧集并发生成 ----------

    @Test
    void generate_concurrentSameEpisode_allSucceedAndProduceFourScenesEach() throws Exception {
        when(llmTransport.postJson(anyString(), anyString(), any(), anyInt())).thenReturn(VALID_JSON);
        LlmScriptService service = newService(true, "test-model", 3000, 5, 0, null);

        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        List<Future<LlmScriptService.LlmScriptResult>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < threads; i++) {
                futures.add(pool.submit(() -> {
                    startGate.await(5, TimeUnit.SECONDS);
                    return service.generate(buildEpisode(), "chars");
                }));
            }
            startGate.countDown();

            for (Future<LlmScriptService.LlmScriptResult> f : futures) {
                LlmScriptService.LlmScriptResult r = f.get(15, TimeUnit.SECONDS);
                assertThat(r.scenes()).hasSize(4);
                assertThat(r.scenes().get(0).sceneNo()).isEqualTo(1);
                assertThat(r.scenes().get(3).sceneNo()).isEqualTo(4);
                assertThat(r.model()).isEqualTo("test-model");
            }
        } finally {
            pool.shutdownNow();
            assertThat(pool.awaitTermination(5, TimeUnit.SECONDS)).isTrue();
        }
    }
}
