package com.dramafactory.service.byok;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.video.VideoProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.net.http.HttpRequest;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DashScopeImageProviderV221CTest {

    private static final class RecordingGateway implements ByokHttpGateway {
        int status;
        String body;

        @Override
        public GatewayResponse exchange(HttpRequest request) {
            return new GatewayResponse(status, body);
        }
    }

    private CredentialResolver okResolver() {
        CredentialResolver resolver = mock(CredentialResolver.class);
        when(resolver.dashscopeByokAuth(any(), any()))
                .thenReturn(Map.entry("Authorization", "Bearer test-key"));
        return resolver;
    }

    private DashScopeImageProvider provider(CredentialResolver resolver, RecordingGateway gateway) {
        return new DashScopeImageProvider(resolver, new ObjectMapper(), gateway);
    }

    @Test
    void submitWithNullTaskIdThrows() {
        CredentialResolver resolver = okResolver();
        RecordingGateway gateway = new RecordingGateway();
        gateway.status = 200;
        gateway.body = "{\"output\":{\"task_id\":null}}";
        DashScopeImageProvider provider = provider(resolver, gateway);

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("k", "https://x.test", "wanx", "p", "1024*1024"));
        assertEquals("DashScope 图片提交失败, 未返回 task_id, 响应: {\"output\":{\"task_id\":null}}",
                ex.getMessage());
    }

    @Test
    void pollWithNullCredentialThrows() {
        CredentialResolver resolver = mock(CredentialResolver.class);
        when(resolver.dashscopeByokAuth(any(), any())).thenReturn(null);
        RecordingGateway gateway = new RecordingGateway();
        gateway.status = 200;
        gateway.body = "{}";
        DashScopeImageProvider provider = provider(resolver, gateway);

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.poll("k", "https://x.test", "t1"));
        assertEquals("未配置密钥：请先在通道管理填写该供应商的 API Key", ex.getMessage());
    }

    @Test
    void pollSucceededWithNullUrlThrows() {
        CredentialResolver resolver = okResolver();
        RecordingGateway gateway = new RecordingGateway();
        gateway.status = 200;
        String body = "{\"output\":{\"task_status\":\"SUCCEEDED\",\"results\":[{\"url\":null}]}}";
        gateway.body = body;
        DashScopeImageProvider provider = provider(resolver, gateway);

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("k", "https://x.test", "t1"));
        assertEquals("DashScope 图片轮询失败, 成功响应缺少图片 URL, 响应: " + body, ex.getMessage());
    }

    @Test
    void pollFailedWithNullMessageReturnsNullErrorMessage() {
        CredentialResolver resolver = okResolver();
        RecordingGateway gateway = new RecordingGateway();
        gateway.status = 200;
        gateway.body = "{\"output\":{\"task_status\":\"FAILED\",\"message\":null}}";
        DashScopeImageProvider provider = provider(resolver, gateway);

        ImageProvider.PollResult result = provider.poll("k", "https://x.test", "t1");

        assertEquals(ImageProvider.RemoteStatus.FAILED, result.status());
        assertNull(result.imageUrl());
        assertNull(result.errorMessage());
        assertEquals(100, result.progress());
    }

    @Test
    void probeWithHttp200ReturnsOk() {
        CredentialResolver resolver = okResolver();
        RecordingGateway gateway = new RecordingGateway();
        gateway.status = 200;
        gateway.body = "{}";
        DashScopeImageProvider provider = provider(resolver, gateway);

        ImageProvider.ConnectivityResult result = provider.probe("k", "https://x.test");

        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
        assertEquals("密钥有效，链路畅通", result.detail());
    }

    /*
     * 诚实跳过论证（经源码级论证不可达，不写测试）：
     *
     * L242 —— truncate 的 `value == null` 臂不可达。
     *   truncate 的两个调用点传入的都是 responseBody，而 responseBody 在调用前
     *   已被 `response.body() == null ? "" : response.body()` 规范化为非 null 字符串，
     *   故 value 恒非 null，该 null 臂词法不可达。
     */
}
