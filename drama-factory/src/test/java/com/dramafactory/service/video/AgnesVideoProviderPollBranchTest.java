package com.dramafactory.service.video;

import com.dramafactory.service.CredentialResolver;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpRequest;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AgnesVideoProviderPollBranchTest {

    private CredentialResolver resolver;
    private RecordingGateway gateway;
    private AgnesVideoProvider provider;

    static class RecordingGateway implements VideoHttpGateway {
        HttpRequest lastRequest;
        private final Deque<GatewayResponse> queue = new ArrayDeque<>();
        void enqueue(int statusCode, String body) { queue.add(new GatewayResponse(statusCode, body)); }
        @Override
        public GatewayResponse exchange(HttpRequest request) {
            this.lastRequest = request;
            GatewayResponse next = queue.poll();
            if (next == null) { throw new IllegalStateException("no recorded response left"); }
            return next;
        }
    }

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.agnesAuth(anyString())).thenReturn(Map.entry("Authorization", "Bearer test"));
        gateway = new RecordingGateway();
        provider = new AgnesVideoProvider(resolver, gateway);
    }

    @Test
    void poll_authMissing_throwsIllegalState() {
        when(resolver.agnesAuth(anyString())).thenReturn(null);
        IllegalStateException ex = assertThrows(IllegalStateException.class, () -> provider.poll("t1"));
        assertTrue(ex.getMessage().contains("未配置 Agnes 密钥"));
    }

    @Test
    void poll_gatewayThrows_wrapped() {
        VideoHttpGateway throwing = request -> { throw new RuntimeException("boom"); };
        AgnesVideoProvider p = new AgnesVideoProvider(resolver, throwing);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> p.poll("t1"));
        assertTrue(ex.getMessage().contains("请求 Agnes 查询接口失败"));
    }

    @Test
    void poll_429_throwsRateLimited() {
        gateway.enqueue(429, "");
        RateLimitedException ex = assertThrows(RateLimitedException.class, () -> provider.poll("t1"));
        assertEquals(60, ex.getRetryAfterSeconds());
    }

    @Test
    void poll_500_nullBody() {
        gateway.enqueue(500, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.poll("t1"));
        assertTrue(ex.getMessage().contains("状态码: 500"));
    }

    @Test
    void poll_500_longBody_truncated() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 400; i++) { sb.append('x'); }
        gateway.enqueue(500, sb.toString());
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.poll("t1"));
        String expected300 = "x".repeat(300);
        assertTrue(ex.getMessage().contains(expected300));
        assertFalse(ex.getMessage().contains("x".repeat(310)));
    }

    @Test
    void poll_500_shortBody() {
        gateway.enqueue(500, "bad gateway");
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.poll("t1"));
        assertTrue(ex.getMessage().contains("bad gateway"));
    }

    @Test
    void poll_200_invalidJson() {
        gateway.enqueue(200, "{not json");
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.poll("t1"));
        assertTrue(ex.getMessage().contains("解析 Agnes 查询响应失败"));
    }

    @Test
    void poll_statusMissing_treatedAsProcessing() {
        gateway.enqueue(200, "{\"foo\":1}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.PROCESSING, r.status());
        assertEquals(0, r.progress());
    }

    @Test
    void poll_statusNull_treatedAsProcessing() {
        gateway.enqueue(200, "{\"status\":null}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.PROCESSING, r.status());
    }

    @Test
    void poll_completed_metadataUrl() {
        gateway.enqueue(200, "{\"status\":\"completed\",\"metadata\":{\"url\":\"http://v/x.mp4\"}}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, r.status());
        assertEquals("http://v/x.mp4", r.videoUrl());
        assertEquals(100, r.progress());
    }

    @Test
    void poll_completed_rootUrlFallback() {
        gateway.enqueue(200, "{\"status\":\"COMPLETED\",\"url\":\"http://v/y.mp4\"}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, r.status());
        assertEquals("http://v/y.mp4", r.videoUrl());
    }

    @Test
    void poll_completed_noUrl() {
        gateway.enqueue(200, "{\"status\":\"completed\"}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, r.status());
        assertNull(r.videoUrl());
    }

    @Test
    void poll_completed_metadataNullUrl_rootFallback() {
        gateway.enqueue(200, "{\"status\":\"completed\",\"metadata\":{\"url\":null},\"url\":\"http://v/z.mp4\"}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, r.status());
        assertEquals("http://v/z.mp4", r.videoUrl());
    }

    @Test
    void poll_failed_message() {
        gateway.enqueue(200, "{\"status\":\"failed\",\"message\":\"oops\"}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.FAILED, r.status());
        assertEquals("oops", r.errorMessage());
    }

    @Test
    void poll_failed_errorFallback() {
        gateway.enqueue(200, "{\"status\":\"FAILED\",\"error\":\"e2\"}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.FAILED, r.status());
        assertEquals("e2", r.errorMessage());
    }

    @Test
    void poll_failed_noMessage() {
        gateway.enqueue(200, "{\"status\":\"failed\"}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.FAILED, r.status());
        assertNull(r.errorMessage());
    }

    @Test
    void poll_processing_numericProgress() {
        gateway.enqueue(200, "{\"status\":\"processing\",\"progress\":42}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.PROCESSING, r.status());
        assertEquals(42, r.progress());
    }

    @Test
    void poll_processing_textProgress() {
        gateway.enqueue(200, "{\"status\":\"processing\",\"progress\":\"77\"}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.PROCESSING, r.status());
        assertEquals(77, r.progress());
    }

    @Test
    void poll_processing_garbageProgress() {
        gateway.enqueue(200, "{\"status\":\"processing\",\"progress\":\"abc\"}");
        VideoProvider.ProbeResult r = provider.poll("t1");
        assertEquals(VideoProvider.RemoteStatus.PROCESSING, r.status());
        assertEquals(0, r.progress());
    }

    @Test
    void poll_taskIdUrlEncoded() {
        gateway.enqueue(200, "{\"status\":\"processing\"}");
        provider.poll("a b/c");
        URI uri = gateway.lastRequest.uri();
        assertTrue(uri.toString().contains("video_id=a+b%2Fc"));
        assertTrue(gateway.lastRequest.headers().firstValue("Authorization").isPresent());
    }
}
