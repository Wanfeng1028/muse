package com.dramafactory.service;

import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ScriptSplitterCallModelTest {

    private EpisodeRepository episodeRepository;
    private ShotRepository shotRepository;
    private VideoTaskRepository videoTaskRepository;
    private CredentialResolver credentialResolver;
    private ObjectMapper objectMapper;
    private CapturingExchange fakeExchange;
    private ScriptSplitterService service;

    static final String VALID_JSON = "[{\"shotNo\":1,\"shotSize\":\"中景\",\"cameraMove\":\"固定机位\",\"description\":\"雨夜街头\",\"durationSeconds\":5,\"dialogue\":\"\",\"videoPrompt\":\"cinematic street night 16:9\"}]";

    static class CapturingExchange implements ScriptSplitterService.HttpExchange {
        private final Deque<Object> queue = new ArrayDeque<>();
        private final Deque<HttpRequest> requests = new ArrayDeque<>();

        void enqueueResponse(HttpResponse<String> response) {
            queue.add(response);
        }

        void enqueueThrow(RuntimeException ex) {
            queue.add(ex);
        }

        HttpRequest lastRequest() {
            return requests.peekLast();
        }

        @Override
        public HttpResponse<String> send(HttpRequest request) throws Exception {
            requests.add(request);
            Object next = queue.poll();
            if (next instanceof RuntimeException) {
                throw (RuntimeException) next;
            }
            @SuppressWarnings("unchecked")
            HttpResponse<String> response = (HttpResponse<String>) next;
            return response;
        }
    }

    @SuppressWarnings("unchecked")
    static HttpResponse<String> response(int status, String body) {
        HttpResponse<String> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(status);
        when(response.body()).thenReturn(body);
        return response;
    }

    static HttpResponse<String> okChoices(String content) {
        String escaped = content.replace("\\", "\\\\").replace("\"", "\\\"");
        return response(200, "{\"choices\":[{\"message\":{\"content\":\"" + escaped + "\"}}]}");
    }

    static String bodyOf(HttpRequest request) {
        final StringBuilder sb = new StringBuilder();
        request.bodyPublisher().ifPresent(publisher -> publisher.subscribe(new java.util.concurrent.Flow.Subscriber<>() {
            public void onSubscribe(java.util.concurrent.Flow.Subscription s) { s.request(Long.MAX_VALUE); }
            public void onNext(java.nio.ByteBuffer b) { byte[] bts = new byte[b.remaining()]; b.get(bts); sb.append(new String(bts, java.nio.charset.StandardCharsets.UTF_8)); }
            public void onError(Throwable t) { }
            public void onComplete() { }
        }));
        return sb.toString();
    }

    @BeforeEach
    void setUp() {
        episodeRepository = mock(EpisodeRepository.class);
        shotRepository = mock(ShotRepository.class);
        videoTaskRepository = mock(VideoTaskRepository.class);
        credentialResolver = mock(CredentialResolver.class);
        objectMapper = new ObjectMapper();
        fakeExchange = new CapturingExchange();
        service = new ScriptSplitterService(episodeRepository, shotRepository, videoTaskRepository,
                credentialResolver, mock(SkillService.class), objectMapper, "Deepseek-v4-flash", 3000, fakeExchange, null);


        Episode episode = new Episode();
        episode.setId(1L);
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of());
        when(shotRepository.save(any())).thenAnswer(inv -> inv.getArgument(0));
        when(videoTaskRepository.findByShotIdOrderByIdDesc(any())).thenReturn(List.of());
    }

    @Test
    void success_returnsParsedShots() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(okChoices(VALID_JSON));

        var result = service.splitFromScript(1L, "剧本");

        assertThat(result).hasSize(1);
        assertThat(result.get(0).shotNo()).isEqualTo(1);
        verify(shotRepository).save(any());
    }

    @Test
    void authHeaderInjected() {
        when(credentialResolver.chatAuth()).thenReturn(Map.entry("Authorization", "Bearer x"));
        fakeExchange.enqueueResponse(okChoices(VALID_JSON));

        service.splitFromScript(1L, "剧本");

        HttpRequest request = fakeExchange.lastRequest();
        assertThat(request.headers().firstValue("Authorization")).hasValue("Bearer x");
    }

    @Test
    void authNull_noHeader() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(okChoices(VALID_JSON));

        var result = service.splitFromScript(1L, "剧本");

        assertThat(result).hasSize(1);
        HttpRequest request = fakeExchange.lastRequest();
        assertThat(request.headers().firstValue("Authorization")).isEmpty();
    }

    @Test
    void exchangeThrows_wrapped() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueThrow(new RuntimeException("boom"));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("调用大模型失败");
    }

    @Test
    void status500_nullBody() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(response(500, null));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("状态码 500");
    }

    @Test
    void status500_longBody_truncated() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        String longBody = "x".repeat(400);
        fakeExchange.enqueueResponse(response(500, longBody));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("x".repeat(300))
                .hasMessageNotContaining("x".repeat(310));
    }

    @Test
    void status500_shortBody() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(response(500, "oops"));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("oops");
    }

    @Test
    void invalidJson() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(response(200, "{bad"));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("解析大模型响应失败");
    }

    @Test
    void choicesMissing() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(response(200, "{}"));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("大模型返回内容为空");
    }

    @Test
    void choicesNotArray() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(response(200, "{\"choices\":{}}"));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("大模型返回内容为空");
    }

    @Test
    void choicesEmpty() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(response(200, "{\"choices\":[]}"));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("大模型返回内容为空");
    }

    @Test
    void messageNull() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(response(200, "{\"choices\":[{\"foo\":1}]}"));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("大模型返回内容为空");
    }

    @Test
    void contentNull() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(response(200, "{\"choices\":[{\"message\":{\"content\":null}}]}"));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("大模型返回内容为空");
    }

    @Test
    void contentBlank() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(okChoices("   "));

        assertThatThrownBy(() -> service.splitFromScript(1L, "剧本"))
                .isInstanceOf(RuntimeException.class)
                .hasMessageContaining("大模型返回内容为空");
    }

    @Test
    void requestBodyShape() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(okChoices(VALID_JSON));

        service.splitFromScript(1L, "剧本");

        String body = bodyOf(fakeExchange.lastRequest());
        assertThat(body).contains("Deepseek-v4-flash");
        assertThat(body).contains("max_tokens");
        assertThat(body).contains("剧本");
    }

    @Test
    void episodeStatusUpdated() {
        when(credentialResolver.chatAuth()).thenReturn(null);
        fakeExchange.enqueueResponse(okChoices(VALID_JSON));

        service.splitFromScript(1L, "剧本");

        ArgumentCaptor<Episode> captor = ArgumentCaptor.forClass(Episode.class);
        verify(episodeRepository).save(captor.capture());
        assertThat(captor.getValue().getStatus()).isEqualTo(EpisodeStatus.SCRIPTED);
    }
}
