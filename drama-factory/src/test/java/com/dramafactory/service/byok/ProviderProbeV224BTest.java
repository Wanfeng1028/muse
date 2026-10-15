package com.dramafactory.service.byok;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.video.VideoProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;

/**
 * V224B 供应商探针分支补充（由 BranchMixedV224BTest 拆分，包可见构造器需同包）。
 */
class ProviderProbeV224BTest {

    private HttpServer aceServer;

    @AfterEach
    void tearDownAceServer() {
        if (aceServer != null) {
            aceServer.stop(0);
            aceServer = null;
        }
    }

    @Test
    void generate_musicProviderHttp500_throwsIllegalStateWithPrefix() throws Exception {
        AtomicReference<Integer> nextStatus = new AtomicReference<>(500);
        AtomicReference<String> nextBody = new AtomicReference<>("{\"error\":\"x\"}");

        aceServer = HttpServer.create(new InetSocketAddress("::1", 0), 0);
        aceServer.createContext("/api/v1/generate", exchange -> {
            byte[] resp = nextBody.get().getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(nextStatus.get(), resp.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(resp);
            }
        });
        aceServer.start();

        String base = "http://[::1]:" + aceServer.getAddress().getPort();
        AceStepMusicProvider provider = new AceStepMusicProvider();

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", base, "ace-step", "p", "l", false));
        assertTrue(ex.getMessage().startsWith("作曲接口返回异常（HTTP 500）："),
                "message 应以 作曲接口返回异常（HTTP 500）： 开头，实际=" + ex.getMessage());
    }

    // ---------------------------------------------------------------
    // 2. DashScopeImageProvider#probe 2xx 成功臂
    // ---------------------------------------------------------------

    @Test
    void probe_dashScopeHttp200_returnsOkStatus() throws Exception {
        CredentialResolver resolver = mock(CredentialResolver.class);
        ByokHttpGateway gateway = mock(ByokHttpGateway.class);

        lenient().when(resolver.dashscopeByokAuth(any(), any()))
                .thenReturn(Map.entry("Authorization", "Bearer test-key-123"));

        ByokHttpGateway.GatewayResponse response =
                new ByokHttpGateway.GatewayResponse(200, "{\"ok\":true}");
        doReturn(response).when(gateway).exchange(any());

        DashScopeImageProvider provider =
                new DashScopeImageProvider(resolver, new ObjectMapper(), gateway);

        ImageProvider.ConnectivityResult result = provider.probe("k", "http://x");
        assertNotNull(result);
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
    }

    // ---------------------------------------------------------------
}
