package com.dramafactory.service.byok;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.video.VideoProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DidAvatarProviderBranchTest {

    static class RecordingGateway implements ByokHttpGateway {
        final Deque<GatewayResponse> responses = new ArrayDeque<>();
        final Deque<HttpRequest> requests = new ArrayDeque<>();

        void enqueue(int statusCode, String body) {
            responses.add(new GatewayResponse(statusCode, body));
        }

        @Override
        public GatewayResponse exchange(HttpRequest request) {
            requests.add(request);
            GatewayResponse next = responses.poll();
            if (next == null) {
                throw new IllegalStateException("no stubbed response");
            }
            return next;
        }
    }

    private CredentialResolver resolver;
    private RecordingGateway gateway;
    private DidAvatarProvider provider;

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.didAuth(any())).thenReturn(Map.entry("Authorization", "Basic <redacted>"));
        gateway = new RecordingGateway();
        provider = new DidAvatarProvider(resolver, new ObjectMapper(), gateway);
    }

    private DidAvatarProvider explodingProvider() {
        ByokHttpGateway exploding = req -> {
            throw new RuntimeException("boom");
        };
        return new DidAvatarProvider(resolver, new ObjectMapper(), exploding);
    }

    @Test
    void submitBlankStringsThrow() {
        // 分支：submit/audioUrl 与 script 均为空白 -> IllegalArgumentException
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> provider.submit("k", "http://img", " ", " "));
        assertEquals("请提供音频 URL 或文案", ex.getMessage());
    }

    @Test
    void submitGatewayThrows() {
        // 分支：submit/网关抛异常 -> RuntimeException
        DidAvatarProvider p = explodingProvider();
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> p.submit("k", "http://img", "http://a", null));
        assertTrue(ex.getMessage().contains("D-ID 提交失败"));
    }

    @Test
    void submitHttp500Throws() {
        // 分支：submit/HTTP 非 2xx -> RuntimeException
        gateway.enqueue(500, "err");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("k", "http://img", "http://a", null));
        assertTrue(ex.getMessage().contains("HTTP 500"));
    }

    @Test
    void submitNullBodyParseFails() {
        // 分支：submit/响应体为 null -> readTree((String) null) 抛 IllegalArgumentException，
        // 被 catch (RuntimeException e) { throw e;} 原样 rethrow（实测消息为 argument "content" is null）
        gateway.enqueue(200, null);
        assertThrows(IllegalArgumentException.class,
                () -> provider.submit("k", "http://img", "http://a", null));
    }

    @Test
    void submitMissingIdThrows() {
        // 分支：submit/idNode == null -> RuntimeException
        gateway.enqueue(200, "{\"status\":\"created\"}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("k", "http://img", "http://a", null));
        assertTrue(ex.getMessage().contains("缺少 id"));
    }

    @Test
    void submitNullIdThrows() {
        // 分支：submit/idNode.isNull() -> RuntimeException
        gateway.enqueue(200, "{\"id\":null}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("k", "http://img", "http://a", null));
        assertTrue(ex.getMessage().contains("缺少 id"));
    }

    @Test
    void submitBlankIdThrows() {
        // 分支：submit/idNode.asText().isBlank() -> RuntimeException
        gateway.enqueue(200, "{\"id\":\" \"}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("k", "http://img", "http://a", null));
        assertTrue(ex.getMessage().contains("缺少 id"));
    }

    @Test
    void pollGatewayThrows() {
        // 分支：poll/网关抛异常 -> RuntimeException
        DidAvatarProvider p = explodingProvider();
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> p.poll("k", "t1"));
        assertTrue(ex.getMessage().contains("D-ID 轮询失败"));
    }

    @Test
    void pollHttp500Throws() {
        // 分支：poll/HTTP 非 2xx -> RuntimeException
        gateway.enqueue(500, "x");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("k", "t1"));
        assertTrue(ex.getMessage().contains("HTTP 500"));
    }

    @Test
    void pollNullBodyParseFails() {
        // 分支：poll/响应体为 null，readTree 抛异常 -> RuntimeException
        gateway.enqueue(200, null);
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("k", "t1"));
        assertTrue(ex.getMessage().contains("响应解析失败"));
    }

    @Test
    void pollDoneMissingUrlThrows() {
        // 分支：poll/done 状态 resultUrl == null -> RuntimeException
        gateway.enqueue(200, "{\"status\":\"done\"}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("k", "t1"));
        assertTrue(ex.getMessage().contains("缺少 result_url"));
    }

    @Test
    void pollDoneNullUrlThrows() {
        // 分支：poll/done 状态 resultUrl.isNull() -> RuntimeException
        gateway.enqueue(200, "{\"status\":\"done\",\"result_url\":null}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("k", "t1"));
        assertTrue(ex.getMessage().contains("缺少 result_url"));
    }

    @Test
    void pollDoneBlankUrlThrows() {
        // 分支：poll/done 状态 resultUrl.asText().isBlank() -> RuntimeException
        gateway.enqueue(200, "{\"status\":\"done\",\"result_url\":\" \"}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("k", "t1"));
        assertTrue(ex.getMessage().contains("缺少 result_url"));
    }

    @Test
    void pollErrorBlankMessageDefaults() {
        // 分支：poll/error 状态 message.isBlank() -> 默认文案
        gateway.enqueue(200, "{\"status\":\"error\"}");
        AvatarProvider.PollResult result = provider.poll("k", "t1");
        assertEquals(AvatarProvider.RemoteStatus.FAILED, result.status());
        assertEquals("D-ID 生成失败", result.errorMessage());
    }

    @Test
    void pollErrorNullMessageDefaults() {
        // 分支：poll/error 状态 message 为 null（path 返回 MissingNode，asText("") 为 ""）-> 默认文案
        gateway.enqueue(200, "{\"status\":\"error\",\"message\":null}");
        AvatarProvider.PollResult result = provider.poll("k", "t1");
        assertEquals(AvatarProvider.RemoteStatus.FAILED, result.status());
        assertEquals("D-ID 生成失败", result.errorMessage());
    }

    @Test
    void pollCreatedAndStartedProcessing() {
        // 分支：poll/status 为 "created" 或 "started" -> PROCESSING
        gateway.enqueue(200, "{\"status\":\"created\"}");
        AvatarProvider.PollResult created = provider.poll("k", "t1");
        assertEquals(AvatarProvider.RemoteStatus.PROCESSING, created.status());

        gateway.enqueue(200, "{\"status\":\"started\"}");
        AvatarProvider.PollResult started = provider.poll("k", "t1");
        assertEquals(AvatarProvider.RemoteStatus.PROCESSING, started.status());
    }

    @Test
    void pollUnknownStatusQueued() {
        // 分支：poll/未知 status -> default QUEUED
        gateway.enqueue(200, "{\"status\":\"weird\"}");
        AvatarProvider.PollResult result = provider.poll("k", "t1");
        assertEquals(AvatarProvider.RemoteStatus.QUEUED, result.status());
        assertNull(result.videoUrl());
        assertNull(result.errorMessage());
    }

    @Test
    void probeNoAuthEntry() {
        // 分支：probe/auth == null -> AUTH_FAILED
        when(resolver.didAuth(any())).thenReturn(null);
        AvatarProvider.ConnectivityResult result = provider.probe("k");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    @Test
    void probeGatewayThrows() {
        // 分支：probe/网关抛异常 -> UNREACHABLE
        DidAvatarProvider p = explodingProvider();
        AvatarProvider.ConnectivityResult result = p.probe("k");
        assertEquals(VideoProvider.ConnectivityStatus.UNREACHABLE, result.status());
        assertTrue(result.detail().contains("D-ID 探针异常"));
    }

    @Test
    void probeRateLimited() {
        // 分支：probe/HTTP 429 -> RATE_LIMITED
        gateway.enqueue(429, "");
        AvatarProvider.ConnectivityResult result = provider.probe("k");
        assertEquals(VideoProvider.ConnectivityStatus.RATE_LIMITED, result.status());
        assertNotNull(result.detail());
    }

    @Test
    void probeServerError() {
        // 分支：probe/HTTP 500 -> PROVIDER_ERROR
        gateway.enqueue(500, "");
        AvatarProvider.ConnectivityResult result = provider.probe("k");
        assertEquals(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, result.status());
        assertTrue(result.detail().contains("HTTP 500"));
    }
}
