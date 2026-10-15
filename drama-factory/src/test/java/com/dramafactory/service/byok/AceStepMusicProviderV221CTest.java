package com.dramafactory.service.byok;

import com.dramafactory.service.video.VideoProvider;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AceStepMusicProviderV221CTest {

    private final AceStepMusicProvider provider = new AceStepMusicProvider();
    private HttpServer server;

    private String startServer(AtomicReference<Integer> statusRef,
                               AtomicReference<String> bodyRef,
                               AtomicReference<String> capturedRequest) throws Exception {
        server = HttpServer.create(new InetSocketAddress("::1", 0), 0);
        server.createContext("/", (HttpExchange exchange) -> {
            if (capturedRequest != null) {
                capturedRequest.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            }
            int status = statusRef.get() == null ? 200 : statusRef.get();
            String body = bodyRef.get() == null ? "" : bodyRef.get();
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(bytes);
            }
        });
        server.start();
        return "http://[::1]:" + server.getAddress().getPort();
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
            server = null;
        }
    }

    @Test
    void generateWithBlankApiKeyThrows() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("   ", "http://x", null, "p", null, false));
        assertEquals("未配置密钥：请先在通道管理填写该供应商的 API Key", ex.getMessage());
    }

    @Test
    void generateWithBlankModelIdUsesDefaultModel() throws Exception {
        AtomicReference<Integer> statusRef = new AtomicReference<>(200);
        AtomicReference<String> bodyRef = new AtomicReference<>("{\"data\":{\"audio_url\":\"http://cdn/a.mp3\"}}");
        AtomicReference<String> captured = new AtomicReference<>();
        String base = startServer(statusRef, bodyRef, captured);

        MusicProvider.GenerateResult result =
                provider.generate("k", base, "   ", "p", null, false);

        assertEquals("http://cdn/a.mp3", result.audioUrl());
        assertTrue(captured.get().contains("\"model\":\"ace-step\""),
                "请求体应包含默认模型 ace-step，实际：" + captured.get());
    }

    @Test
    void probeWithBlankApiKeyReturnsAuthFailed() {
        MusicProvider.ConnectivityResult result = provider.probe("   ", "http://x");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
        assertEquals("未配置密钥：请先在通道管理填写该供应商的 API Key", result.detail());
    }

    @Test
    void generateWithBlankApiBaseThrows() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", "   ", null, "p", null, false));
        assertEquals("未配置 API 地址：请先在通道管理填写该供应商的 API Base", ex.getMessage());
    }

    /*
     * 诚实跳过论证（经源码级论证不可达，不写测试）：
     *
     * 1) L83 / L142 —— `response.body() == null` 臂不可达。
     *    httpClient 是 private final 字段，无注入点；测试只能通过真实
     *    httpClient.send(..., HttpResponse.BodyHandlers.ofString(...)) 触发。
     *    BodyHandlers.ofString(...) 恒返回非 null 的 String（即便空体也是 ""），
     *    因此该 null 臂词法不可达。
     *
     * 2) L84 —— `code < 200` 臂不可达。
     *    JDK HttpServer 对 1xx 状态码按 interim 响应处理，客户端会继续等待终态
     *    响应从而触发超时（上一轮已实测 199 触发约 40 秒超时），本地无法构造
     *    1xx 终态响应，因此该臂在纯本地测试中不可达。
     *
     * 3) L96 —— `audioUrl.isBlank()` 臂不可达。
     *    extractAudioUrl 内部对每个候选字段均已用 `!xxx.asText().isBlank()`
     *    过滤后才返回，故返回值恒为非空字符串或 null；null 已在上一行判掉，
     *    因此 isBlank 臂恒为假，词法不可达。
     */
}
