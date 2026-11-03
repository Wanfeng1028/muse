package com.dramafactory.service.byok;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.video.VideoProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.net.http.HttpRequest;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DashScopeImageProviderV221ETest {

    @Test
    void probe_status302_returnsProviderError() {
        CredentialResolver resolver = mock(CredentialResolver.class);
        when(resolver.dashscopeByokAuth(any(), any()))
                .thenReturn(Map.entry("Authorization", "Bearer test-key"));

        RecordingGateway gateway = new RecordingGateway(302, "{}");

        DashScopeImageProvider provider =
                new DashScopeImageProvider(resolver, new ObjectMapper(), gateway);

        ImageProvider.ConnectivityResult result = provider.probe("k", "https://x.test");

        assertEquals(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, result.status());
        assertEquals("服务方返回异常状态码：302", result.detail());
    }

    private static final class RecordingGateway implements ByokHttpGateway {

        private final int status;
        private final String body;

        private RecordingGateway(int status, String body) {
            this.status = status;
            this.body = body;
        }

        @Override
        public GatewayResponse exchange(HttpRequest request) {
            return new GatewayResponse(status, body);
        }
    }
}
