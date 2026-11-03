package com.dramafactory.service.byok;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.byok.ImageProvider.PollResult;
import com.dramafactory.service.byok.ImageProvider.RemoteStatus;
import com.dramafactory.service.byok.ImageProvider.SubmitResult;
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
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DashScopeImageProviderBranchTest {

    private CredentialResolver resolver;
    private RecordingGateway gateway;
    private DashScopeImageProvider provider;

    static class RecordingGateway implements ByokHttpGateway {
        private final Deque<GatewayResponse> responses = new ArrayDeque<>();
        HttpRequest lastRequest;

        void enqueue(int statusCode, String body) {
            responses.add(new GatewayResponse(statusCode, body));
        }

        @Override
        public GatewayResponse exchange(HttpRequest request) {
            this.lastRequest = request;
            if (responses.isEmpty()) {
                throw new IllegalStateException("no recorded response left");
            }
            return responses.poll();
        }
    }

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.dashscopeByokAuth(any(), any()))
                .thenReturn(Map.entry("Authorization", "Bearer test"));
        gateway = new RecordingGateway();
        provider = new DashScopeImageProvider(resolver, new ObjectMapper(), gateway);
    }

    private DashScopeImageProvider providerWithExplodingGateway() {
        ByokHttpGateway exploding = req -> {
            throw new RuntimeException("boom");
        };
        return new DashScopeImageProvider(resolver, new ObjectMapper(), exploding);
    }

    @Test
    void submitNullSizeThrows() {
        // 分支：submit/size == null -> IllegalArgumentException
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> provider.submit("key", "https://example.com", "m", "p", null));
        assertTrue(ex.getMessage().contains("不支持的图片尺寸"));
    }

    @Test
    void submitNoCredentialThrows() {
        // 分支：submit/credential == null -> IllegalStateException 未配置密钥
        when(resolver.dashscopeByokAuth(any(), any())).thenReturn(null);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.submit("key", "https://example.com", "m", "p", "1024*1024"));
        assertTrue(ex.getMessage().contains("未配置密钥"));
    }

    @Test
    void submitGatewayThrows() {
        // 分支：submit/网关抛异常 -> RuntimeException 网络不可达
        DashScopeImageProvider p = providerWithExplodingGateway();
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> p.submit("key", "https://example.com", "m", "p", "1024*1024"));
        assertTrue(ex.getMessage().contains("网络不可达"));
    }

    @Test
    void submitHttp500Throws() {
        // 分支：submit/code 非 2xx -> RuntimeException HTTP 500
        gateway.enqueue(500, "boom");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("key", "https://example.com", "m", "p", "1024*1024"));
        assertTrue(ex.getMessage().contains("HTTP 500"));
    }

    @Test
    void submitNullBodyParseFails() {
        // 分支：submit/responseBody == null 回落 "" -> readTree("") 返回 MissingNode（Jackson 2.17 实测不抛异常）
        // -> task_id 缺失 -> RuntimeException 未返回 task_id
        gateway.enqueue(200, null);
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("key", "https://example.com", "m", "p", "1024*1024"));
        assertTrue(ex.getMessage().contains("未返回 task_id"));
    }

    @Test
    void submitMissingTaskIdThrows() {
        // 分支：submit/output 缺 task_id -> RuntimeException 未返回 task_id
        gateway.enqueue(200, "{\"output\":{}}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("key", "https://example.com", "m", "p", "1024*1024"));
        assertTrue(ex.getMessage().contains("未返回 task_id"));
    }

    @Test
    void submitBlankTaskIdThrows() {
        // 分支：submit/task_id 为空白 -> RuntimeException 未返回 task_id
        gateway.enqueue(200, "{\"output\":{\"task_id\":\" \"}}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("key", "https://example.com", "m", "p", "1024*1024"));
        assertTrue(ex.getMessage().contains("未返回 task_id"));
    }

    @Test
    void submitTruncatesLongBody() {
        // 分支：submit/HTTP 非 2xx 且 body 超长 -> truncate 截断到 300
        String longBody = "x".repeat(400);
        gateway.enqueue(500, longBody);
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("key", "https://example.com", "m", "p", "1024*1024"));
        assertTrue(ex.getMessage().contains("HTTP 500"));
        assertTrue(ex.getMessage().length() < 400 + 50);
    }

    @Test
    void submitNullBaseUsesDefault() {
        // 分支：base/apiBase == null -> DEFAULT_BASE
        gateway.enqueue(200, "{\"output\":{\"task_id\":\"t1\"}}");
        SubmitResult result = provider.submit("key", null, "m", "p", "1024*1024");
        assertEquals("t1", result.taskId());
        assertTrue(gateway.lastRequest.uri().toString()
                .startsWith("https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"));
    }

    @Test
    void submitBlankBaseUsesDefault() {
        // 分支：base/apiBase 为空白 -> DEFAULT_BASE
        gateway.enqueue(200, "{\"output\":{\"task_id\":\"t1\"}}");
        SubmitResult result = provider.submit("key", " ", "m", "p", "1024*1024");
        assertEquals("t1", result.taskId());
        assertTrue(gateway.lastRequest.uri().toString()
                .startsWith("https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"));
    }

    @Test
    void submitTrailingSlashesStripped() {
        // 分支：base/末尾斜杠循环剥离
        gateway.enqueue(200, "{\"output\":{\"task_id\":\"t1\"}}");
        SubmitResult result = provider.submit("key", "https://example.com///", "m", "p", "1024*1024");
        assertEquals("t1", result.taskId());
        assertEquals("https://example.com/api/v1/services/aigc/text2image/image-synthesis",
                gateway.lastRequest.uri().toString());
    }

    @Test
    void submitApiV1SuffixStripped() {
        // 分支：base/末尾 /api/v1 剥离，避免路径重复
        gateway.enqueue(200, "{\"output\":{\"task_id\":\"t1\"}}");
        SubmitResult result = provider.submit("key", "https://example.com/api/v1", "m", "p", "1024*1024");
        assertEquals("t1", result.taskId());
        assertEquals("https://example.com/api/v1/services/aigc/text2image/image-synthesis",
                gateway.lastRequest.uri().toString());
    }

    @Test
    void pollGatewayThrows() {
        // 分支：poll/网关抛异常 -> RuntimeException 网络不可达
        DashScopeImageProvider p = providerWithExplodingGateway();
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> p.poll("key", "https://example.com", "t1"));
        assertTrue(ex.getMessage().contains("网络不可达"));
    }

    @Test
    void pollHttp500Throws() {
        // 分支：poll/code 非 2xx -> RuntimeException HTTP 500
        gateway.enqueue(500, "x");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("key", "https://example.com", "t1"));
        assertTrue(ex.getMessage().contains("HTTP 500"));
    }

    @Test
    void pollNullBodyParseFails() {
        // 分支：poll/responseBody == null 回落 "" -> readTree("") 返回 MissingNode（Jackson 2.17 实测不抛异常）
        // -> task_status 为 "" -> default -> QUEUED，全程不抛异常
        gateway.enqueue(200, null);
        PollResult result = provider.poll("key", "https://example.com", "t1");
        assertEquals(RemoteStatus.QUEUED, result.status());
    }

    @Test
    void pollSucceededMissingResults() {
        // 分支：poll/SUCCEEDED 且 results 缺失 -> RuntimeException 缺少 results
        gateway.enqueue(200, "{\"output\":{\"task_status\":\"SUCCEEDED\"}}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("key", "https://example.com", "t1"));
        assertTrue(ex.getMessage().contains("缺少 results"));
    }

    @Test
    void pollSucceededEmptyResults() {
        // 分支：poll/SUCCEEDED 且 results 为空数组 -> RuntimeException 缺少 results
        gateway.enqueue(200, "{\"output\":{\"task_status\":\"SUCCEEDED\",\"results\":[]}}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("key", "https://example.com", "t1"));
        assertTrue(ex.getMessage().contains("缺少 results"));
    }

    @Test
    void pollSucceededMissingUrl() {
        // 分支：poll/SUCCEEDED 且 results[0] 缺 url -> RuntimeException 缺少图片 URL
        gateway.enqueue(200, "{\"output\":{\"task_status\":\"SUCCEEDED\",\"results\":[{}]}}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("key", "https://example.com", "t1"));
        assertTrue(ex.getMessage().contains("缺少图片 URL"));
    }

    @Test
    void pollFailedNullMessage() {
        // 分支：poll/FAILED 且 message 缺失 -> errorMessage 为 null
        gateway.enqueue(200, "{\"output\":{\"task_status\":\"FAILED\"}}");
        PollResult result = provider.poll("key", "https://example.com", "t1");
        assertEquals(RemoteStatus.FAILED, result.status());
        assertNull(result.errorMessage());
    }

    @Test
    void pollPendingAndRunning() {
        // 分支：poll/PENDING、RUNNING -> PROCESSING
        gateway.enqueue(200, "{\"output\":{\"task_status\":\"PENDING\"}}");
        PollResult pending = provider.poll("key", "https://example.com", "t1");
        assertEquals(RemoteStatus.PROCESSING, pending.status());

        gateway.enqueue(200, "{\"output\":{\"task_status\":\"RUNNING\"}}");
        PollResult running = provider.poll("key", "https://example.com", "t2");
        assertEquals(RemoteStatus.PROCESSING, running.status());
    }

    @Test
    void pollUnknownAndDefault() {
        // 分支：poll/UNKNOWN 与 default -> QUEUED
        gateway.enqueue(200, "{\"output\":{\"task_status\":\"UNKNOWN\"}}");
        PollResult unknown = provider.poll("key", "https://example.com", "t1");
        assertEquals(RemoteStatus.QUEUED, unknown.status());

        gateway.enqueue(200, "{\"output\":{\"task_status\":\"SUSPENDED\"}}");
        PollResult suspended = provider.poll("key", "https://example.com", "t2");
        assertEquals(RemoteStatus.QUEUED, suspended.status());
    }

    @Test
    void probeGatewayThrows() {
        // 分支：probe/网关抛异常 -> UNREACHABLE
        DashScopeImageProvider p = providerWithExplodingGateway();
        ImageProvider.ConnectivityResult result = p.probe("key", "https://example.com");
        assertEquals(VideoProvider.ConnectivityStatus.UNREACHABLE, result.status());
    }

    @Test
    void probeRateLimited() {
        // 分支：probe/code == 429 -> RATE_LIMITED
        gateway.enqueue(429, "");
        ImageProvider.ConnectivityResult result = provider.probe("key", "https://example.com");
        assertEquals(VideoProvider.ConnectivityStatus.RATE_LIMITED, result.status());
    }

    @Test
    void probeOk200() {
        // 分支：probe/code 2xx 非 404 -> OK
        gateway.enqueue(200, "{}");
        ImageProvider.ConnectivityResult result = provider.probe("key", "https://example.com");
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
    }

    @Test
    void probeProviderError() {
        // 分支：probe/其他状态码 -> PROVIDER_ERROR
        gateway.enqueue(500, "");
        ImageProvider.ConnectivityResult result = provider.probe("key", "https://example.com");
        assertEquals(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, result.status());
    }
}
