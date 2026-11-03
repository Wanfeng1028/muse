package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.CredentialResolver;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpRequest;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * AgnesVideoProvider 连接自检契约测试：全程走录制回放网关，零真实网络。
 */
class AgnesProbeTest {

    private CredentialResolver resolver;
    private RecordingGateway gateway;

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.agnesAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer <redacted>"));
        gateway = new RecordingGateway();
    }

    private AgnesVideoProvider provider() {
        return new AgnesVideoProvider(resolver, gateway);
    }

    @Test
    void probe404IsOk() {
        gateway.next(404, "{\"error\":\"task not found\"}");
        VideoProvider.ConnectivityResult r = provider().probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.OK, r.status());
        assertFalse(r.detail().contains("失败"));
        assertNotNull(gateway.lastRequest);
        URI uri = gateway.lastRequest.uri();
        assertEquals("apihub.agnes-ai.com", uri.getHost());
        assertEquals("/agnesapi", uri.getPath());
        assertTrue(uri.getQuery().contains("video_id=__connectivity_probe__"));
        assertEquals("GET", gateway.lastRequest.method());
        assertNotNull(gateway.lastRequest.headers().firstValue("Authorization").orElse(null));
    }

    @Test
    void probe401IsAuthFailed() {
        gateway.next(401, "{}");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED,
                provider().probeConnectivity().status());
    }

    @Test
    void probe403IsAuthFailed() {
        gateway.next(403, "{}");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED,
                provider().probeConnectivity().status());
    }

    @Test
    void probe429IsRateLimited() {
        gateway.next(429, "{}");
        assertEquals(VideoProvider.ConnectivityStatus.RATE_LIMITED,
                provider().probeConnectivity().status());
    }

    @Test
    void probeGatewayThrowsIsUnreachable() {
        gateway.nextThrow(new RuntimeException("boom"));
        VideoProvider.ConnectivityResult r = provider().probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.UNREACHABLE, r.status());
        assertFalse(r.detail().contains("boom"));
    }

    @Test
    void probe500IsProviderError() {
        gateway.next(500, "{}");
        assertEquals(VideoProvider.ConnectivityStatus.PROVIDER_ERROR,
                provider().probeConnectivity().status());
    }

    @Test
    void probeNullAuthIsAuthFailed() {
        CredentialResolver nullResolver = mock(CredentialResolver.class);
        when(nullResolver.agnesAuth(anyString())).thenReturn(null);
        AgnesVideoProvider p = new AgnesVideoProvider(nullResolver, gateway);
        VideoProvider.ConnectivityResult r = p.probeConnectivity();
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, r.status());
        assertTrue(r.detail().contains("未配置"));
    }

    @Test
    void submitNullAuthThrows() {
        CredentialResolver nullResolver = mock(CredentialResolver.class);
        when(nullResolver.agnesAuth(anyString())).thenReturn(null);
        AgnesVideoProvider p = new AgnesVideoProvider(nullResolver, gateway);
        Shot shot = new Shot();
        shot.setVideoPrompt("p");
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> p.submit(shot, 5));
        assertTrue(ex.getMessage().contains("未配置"));
    }

    @Test
    void pollNullAuthThrows() {
        CredentialResolver nullResolver = mock(CredentialResolver.class);
        when(nullResolver.agnesAuth(anyString())).thenReturn(null);
        AgnesVideoProvider p = new AgnesVideoProvider(nullResolver, gateway);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> p.poll("task-1"));
        assertTrue(ex.getMessage().contains("未配置"));
    }

    /** 极简录制回放网关：按预设脚本返回响应，不发起真实网络请求。 */
    static final class RecordingGateway implements VideoHttpGateway {
        int statusCode = 200;
        String body = "";
        RuntimeException toThrow;
        HttpRequest lastRequest;

        void next(int code, String responseBody) {
            this.statusCode = code;
            this.body = responseBody;
            this.toThrow = null;
        }

        void nextThrow(RuntimeException e) {
            this.toThrow = e;
        }

        @Override
        public GatewayResponse exchange(HttpRequest request) {
            this.lastRequest = request;
            if (toThrow != null) {
                throw toThrow;
            }
            return new GatewayResponse(statusCode, body);
        }
    }
}
