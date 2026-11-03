package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.CredentialResolver;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.http.HttpRequest;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.Flow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * MiniMaxH3VideoProvider 单元测试：录制回放网关，全程无 socket。
 */
class MiniMaxH3VideoProviderTest {

    static class RecordingGateway implements VideoHttpGateway {
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

    static String bodyOf(HttpRequest request) {
        final StringBuilder sb = new StringBuilder();
        request.bodyPublisher().ifPresent(publisher ->
                publisher.subscribe(new Flow.Subscriber<>() {
                    @Override
                    public void onSubscribe(Flow.Subscription subscription) {
                        subscription.request(Long.MAX_VALUE);
                    }

                    @Override
                    public void onNext(ByteBuffer item) {
                        byte[] bytes = new byte[item.remaining()];
                        item.get(bytes);
                        sb.append(new String(bytes, StandardCharsets.UTF_8));
                    }

                    @Override
                    public void onError(Throwable throwable) {
                    }

                    @Override
                    public void onComplete() {
                    }
                }));
        return sb.toString();
    }

    private RecordingGateway gateway;
    private CredentialResolver resolver;
    private MiniMaxH3VideoProvider provider;

    @BeforeEach
    void setUp() {
        gateway = new RecordingGateway();
        resolver = mock(CredentialResolver.class);
        when(resolver.minimaxAuth(any())).thenReturn(Map.entry("Authorization", "Bearer <redacted>"));
        provider = new MiniMaxH3VideoProvider(resolver, "MiniMax-H3", "768P", gateway);
    }

    private Shot newShot() {
        Shot shot = new Shot();
        shot.setDescription("男主在雨中奔跑");
        return shot;
    }

    @Test
    void name_isMinimax() {
        assertEquals("minimax", provider.name());
    }

    @Test
    void submit_success_returnsTaskId() {
        gateway.enqueue(200, "{\"task_id\":\"106916112212032\","
                + "\"base_resp\":{\"status_code\":0,\"status_msg\":\"success\"}}");

        String taskId = provider.submit(newShot(), 6);

        assertEquals("106916112212032", taskId);
        assertEquals("https://api.minimax.io/v1/video_generation",
                gateway.lastRequest.uri().toString());
        assertEquals("POST", gateway.lastRequest.method());
        String body = bodyOf(gateway.lastRequest);
        assertTrue(body.contains("\"model\":\"MiniMax-H3\""), "实际: " + body);
        assertTrue(body.contains("\"duration\":6"), "实际: " + body);
        assertTrue(body.contains("\"resolution\":\"768P\""), "实际: " + body);
        assertTrue(body.contains("男主在雨中奔跑"), "实际: " + body);
    }

    @Test
    void submit_durationClampedTo4_15() {
        gateway.enqueue(200, "{\"task_id\":\"1\",\"base_resp\":{\"status_code\":0}}");
        provider.submit(newShot(), 30);
        assertTrue(bodyOf(gateway.lastRequest).contains("\"duration\":15"));

        gateway.enqueue(200, "{\"task_id\":\"2\",\"base_resp\":{\"status_code\":0}}");
        provider.submit(newShot(), 1);
        assertTrue(bodyOf(gateway.lastRequest).contains("\"duration\":4"));
    }

    @Test
    void submit_authMissing_throwsIllegalState() {
        when(resolver.minimaxAuth(any())).thenReturn(null);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.submit(newShot(), 6));
        assertTrue(ex.getMessage().contains("未配置 MiniMax 密钥"), "实际: " + ex.getMessage());
    }

    @Test
    void submit_429_throwsRateLimited() {
        gateway.enqueue(429, "{\"base_resp\":{\"status_code\":1008}}");
        assertThrows(RateLimitedException.class, () -> provider.submit(newShot(), 6));
    }

    @Test
    void submit_5xx_throwsWithSnippet() {
        gateway.enqueue(500, "{\"error\":\"internal\"}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit(newShot(), 6));
        assertTrue(ex.getMessage().contains("500"), "实际: " + ex.getMessage());
    }

    @Test
    void poll_success_returnsCompleted() {
        gateway.enqueue(200, "{\"status\":\"success\",\"file_id\":\"file_abc123\","
                + "\"base_resp\":{\"status_code\":0}}");
        VideoProvider.ProbeResult result = provider.poll("106916112212032");
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertTrue(result.videoUrl().contains("file_abc123"), "实际: " + result.videoUrl());
        assertEquals(100, result.progress());
        assertTrue(gateway.lastRequest.uri().toString()
                .contains("/v1/query/video_generation/106916112212032"));
    }

    @Test
    void poll_processing_returnsProcessing() {
        gateway.enqueue(200, "{\"status\":\"processing\",\"base_resp\":{\"status_code\":0}}");
        VideoProvider.ProbeResult result = provider.poll("task1");
        assertEquals(VideoProvider.RemoteStatus.PROCESSING, result.status());
    }

    @Test
    void poll_failed_returnsFailedWithReason() {
        gateway.enqueue(200, "{\"status\":\"failed\","
                + "\"base_resp\":{\"status_code\":2013,\"status_msg\":\"内容审核未通过\"}}");
        VideoProvider.ProbeResult result = provider.poll("task1");
        assertEquals(VideoProvider.RemoteStatus.FAILED, result.status());
        assertTrue(result.errorMessage().contains("内容审核未通过"),
                "实际: " + result.errorMessage());
    }

    @Test
    void probeConnectivity_ok() {
        // 负向探测：未知 task_id 返回业务错误（非 401/429），即判 OK
        gateway.enqueue(200, "{\"status\":\"failed\","
                + "\"base_resp\":{\"status_code\":1004,\"status_msg\":\"task not found\"}}");
        VideoProvider.ConnectivityResult result = provider.probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
    }

    @Test
    void probeConnectivity_authFailed() {
        gateway.enqueue(401, "{\"base_resp\":{\"status_code\":1002}}");
        VideoProvider.ConnectivityResult result = provider.probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    @Test
    void probeConnectivity_noKey() {
        when(resolver.minimaxAuth(any())).thenReturn(null);
        VideoProvider.ConnectivityResult result = provider.probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
        assertTrue(!result.detail().contains("<redacted>"), "detail 不得含密钥");
    }

    @Test
    void probeConnectivity_unreachable() {
        gateway = new RecordingGateway() {
            @Override
            public GatewayResponse exchange(HttpRequest request) {
                throw new RuntimeException("connection refused");
            }
        };
        provider = new MiniMaxH3VideoProvider(resolver, "MiniMax-H3", "768P", gateway);
        VideoProvider.ConnectivityResult result = provider.probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.UNREACHABLE, result.status());
    }
}
