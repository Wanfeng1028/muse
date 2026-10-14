package com.dramafactory.service.byok;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.video.VideoProvider;
import java.net.http.HttpRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DashScopeImageProviderTest {

    static class RecordingGateway implements ByokHttpGateway {
        HttpRequest lastRequest;
        private final Deque<GatewayResponse> queue = new ArrayDeque<>();

        void enqueue(int statusCode, String body) {
            queue.add(new GatewayResponse(statusCode, body));
        }

        @Override
        public GatewayResponse exchange(HttpRequest request) {
            this.lastRequest = request;
            GatewayResponse next = queue.poll();
            if (next == null) {
                throw new IllegalStateException("no recorded response left");
            }
            return next;
        }
    }

    private CredentialResolver resolver;
    private RecordingGateway gateway;
    private DashScopeImageProvider provider;

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.dashscopeByokAuth(any(), any()))
                .thenReturn(Map.entry("Authorization", "Bearer <redacted>"));
        gateway = new RecordingGateway();
        provider = new DashScopeImageProvider(resolver, new ObjectMapper(), gateway);
    }

    @Test
    void nameIsDashscopeImage() {
        assertEquals("dashscope-image", provider.name());
    }

    @Test
    void submitOk() {
        gateway.enqueue(200, "{\"output\":{\"task_id\":\"task-123\",\"task_status\":\"PENDING\"}}");
        ImageProvider.SubmitResult result = provider.submit(
                "k", "https://dashscope.aliyuncs.com", "wan2.5-t2i-preview", "一只猫", "1024*1024");
        assertEquals("task-123", result.taskId());
        assertNotNull(gateway.lastRequest);
        assertTrue(gateway.lastRequest.uri().toString().contains("image-synthesis"),
                "URI should contain image-synthesis but was: " + gateway.lastRequest.uri());
        assertEquals("POST", gateway.lastRequest.method());
    }

    @Test
    void submitBadSize() {
        assertThrows(IllegalArgumentException.class, () -> provider.submit(
                "k", "https://dashscope.aliyuncs.com", "wan2.5-t2i-preview", "一只猫", "999*999"));
    }

    @Test
    void submitLogicError() {
        gateway.enqueue(200, "{\"code\":\"InvalidParameter\",\"message\":\"bad\"}");
        assertThrows(RuntimeException.class, () -> provider.submit(
                "k", "https://dashscope.aliyuncs.com", "wan2.5-t2i-preview", "一只猫", "1024*1024"));
    }

    @Test
    void pollSucceeded() {
        gateway.enqueue(200, "{\"output\":{\"task_id\":\"t\",\"task_status\":\"SUCCEEDED\",\"results\":[{\"url\":\"https://x/y.png\"}]}}");
        ImageProvider.PollResult result = provider.poll(
                "k", "https://dashscope.aliyuncs.com", "t");
        assertEquals(ImageProvider.RemoteStatus.SUCCEEDED, result.status());
        assertEquals("https://x/y.png", result.imageUrl());
    }

    @Test
    void pollFailed() {
        gateway.enqueue(200, "{\"output\":{\"task_id\":\"t\",\"task_status\":\"FAILED\",\"message\":\"nsfw\",\"code\":\"E1\"}}");
        ImageProvider.PollResult result = provider.poll(
                "k", "https://dashscope.aliyuncs.com", "t");
        assertEquals(ImageProvider.RemoteStatus.FAILED, result.status());
    }

    @Test
    void probeOk() {
        gateway.enqueue(404, "");
        ImageProvider.ConnectivityResult result = provider.probe(
                "k", "https://dashscope.aliyuncs.com");
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
    }

    @Test
    void probeAuthFailed() {
        gateway.enqueue(401, "");
        ImageProvider.ConnectivityResult result = provider.probe(
                "k", "https://dashscope.aliyuncs.com");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    @Test
    void probeNoKey() {
        when(resolver.dashscopeByokAuth(any(), any())).thenReturn(null);
        ImageProvider.ConnectivityResult result = provider.probe(
                null, "https://dashscope.aliyuncs.com");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }
}
