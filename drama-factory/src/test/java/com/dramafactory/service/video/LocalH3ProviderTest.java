package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.CredentialResolver;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.http.HttpRequest;
import java.util.ArrayDeque;
import java.util.Deque;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

/**
 * LocalH3Provider 单元测试：录制回放网关，全程无 socket。
 * 验证本地 Provider 复用 MiniMax 兼容接口格式（POST /v1/video_generation）。
 */
class LocalH3ProviderTest {

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

    private static final String BASE = "http://localhost:8188";

    private RecordingGateway gateway;
    private LocalH3Provider provider;

    @BeforeEach
    void setUp() {
        gateway = new RecordingGateway();
        CredentialResolver resolver = mock(CredentialResolver.class);
        provider = new LocalH3Provider(resolver, BASE, "", "MiniMax-H3", "768P", gateway);
    }

    @Test
    void name_isLocalH3() {
        assertEquals("local-h3", provider.name());
    }

    @Test
    void probeConnectivity_noBaseUrl_authFailed() {
        CredentialResolver resolver = mock(CredentialResolver.class);
        LocalH3Provider p = new LocalH3Provider(resolver, "", "", "MiniMax-H3", "768P", gateway);
        VideoProvider.ConnectivityResult result = p.probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
        assertTrue(result.detail().contains("local-h3.base-url"), "实际: " + result.detail());
    }

    @Test
    void probeConnectivity_ok_noAuthHeader() {
        gateway.enqueue(200, "{\"status\":\"failed\","
                + "\"base_resp\":{\"status_code\":1004,\"status_msg\":\"task not found\"}}");
        VideoProvider.ConnectivityResult result = provider.probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
        // 无 api-key 时不带 Authorization 头
        assertTrue(gateway.lastRequest.headers().firstValue("Authorization").isEmpty(),
                "本地无密钥时不应带鉴权头");
    }

    @Test
    void probeConnectivity_withApiKey_sendsBearer() {
        CredentialResolver resolver = mock(CredentialResolver.class);
        LocalH3Provider p = new LocalH3Provider(resolver, BASE, "secret123",
                "MiniMax-H3", "768P", gateway);
        gateway.enqueue(200, "{\"status\":\"failed\",\"base_resp\":{\"status_code\":1004}}");
        p.probeConnectivity();
        assertEquals("Bearer secret123",
                gateway.lastRequest.headers().firstValue("Authorization").orElse(""));
    }

    @Test
    void submit_postsToLocalBaseUrl() {
        gateway.enqueue(200, "{\"task_id\":\"local-1\",\"base_resp\":{\"status_code\":0}}");
        Shot shot = new Shot();
        shot.setDescription("本地测试镜头");

        String taskId = provider.submit(shot, 6);

        assertEquals("local-1", taskId);
        assertEquals(BASE + "/v1/video_generation",
                gateway.lastRequest.uri().toString());
        assertEquals("POST", gateway.lastRequest.method());
    }

    @Test
    void submit_notConfigured_throws() {
        CredentialResolver resolver = mock(CredentialResolver.class);
        LocalH3Provider p = new LocalH3Provider(resolver, "  ", "", "MiniMax-H3", "768P", gateway);
        assertThrows(IllegalStateException.class, () -> p.submit(new Shot(), 6));
    }

    @Test
    void poll_queriesLocalBaseUrl() {
        gateway.enqueue(200, "{\"status\":\"success\",\"file_id\":\"f1\","
                + "\"base_resp\":{\"status_code\":0}}");
        VideoProvider.ProbeResult result = provider.poll("local-1");
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertTrue(gateway.lastRequest.uri().toString()
                .startsWith(BASE + "/v1/query/video_generation/"),
                "实际: " + gateway.lastRequest.uri());
    }
}
