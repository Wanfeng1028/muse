package com.dramafactory.service.byok;

import com.dramafactory.service.video.VideoProvider;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AceStepMusicProviderTest {

    private HttpServer server;
    private String base;

    private final AtomicReference<Integer> nextStatus = new AtomicReference<>(200);
    private final AtomicReference<String> nextBody = new AtomicReference<>("{}");
    private final AtomicReference<String> lastPath = new AtomicReference<>();
    private final AtomicReference<String> lastAuth = new AtomicReference<>();
    private final AtomicReference<String> lastBody = new AtomicReference<>();
    private final AtomicReference<Function<HttpExchange, String>> customBody = new AtomicReference<>(null);

    private final AceStepMusicProvider provider = new AceStepMusicProvider();

    @BeforeEach
    void setUp() throws IOException {
        server = HttpServer.create(new InetSocketAddress("::1", 0), 0);
        server.createContext("/", exchange -> {
            lastPath.set(exchange.getRequestURI().getPath());
            lastAuth.set(exchange.getRequestHeaders().getFirst("Authorization"));
            byte[] raw = exchange.getRequestBody().readAllBytes();
            lastBody.set(new String(raw, StandardCharsets.UTF_8));

            int status = nextStatus.get();
            String body;
            Function<HttpExchange, String> fn = customBody.get();
            if (fn != null) {
                body = fn.apply(exchange);
            } else {
                body = nextBody.get();
            }
            byte[] out = body == null ? new byte[0] : body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(status, out.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(out);
            }
        });
        server.start();
        base = "http://[::1]:" + server.getAddress().getPort();
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    private void preset(int status, String body) {
        nextStatus.set(status);
        nextBody.set(body);
        customBody.set(null);
    }

    // ---------- name ----------

    @Test
    void name_returnsAceStepMusic() {
        assertEquals("ace-step-music", provider.name());
    }

    // ---------- generate: validation ----------

    @Test
    void generate_blankApiKey_throws() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("  ", base, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("未配置密钥"), ex.getMessage());
    }

    @Test
    void generate_blankApiBase_throws() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", "   ", "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("未配置 API 地址"), ex.getMessage());
    }

    // ---------- generate: happy paths ----------

    @Test
    void generate_success_extractsAudioUrlFromDataAudioUrl() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/a.mp3\",\"duration_ms\":1234}}");
        MusicProvider.GenerateResult r = provider.generate("k", base, "m", "p", "l", false);
        assertEquals("http://x/a.mp3", r.audioUrl());
    }

    @Test
    void generate_success_fallsBackToDataUrl() {
        preset(200, "{\"data\":{\"url\":\"http://x/b.mp3\"}}");
        MusicProvider.GenerateResult r = provider.generate("k", base, "m", "p", "l", false);
        assertEquals("http://x/b.mp3", r.audioUrl());
    }

    @Test
    void generate_success_fallsBackToTopLevelAudioUrl() {
        preset(200, "{\"audio_url\":\"http://x/c.mp3\"}");
        MusicProvider.GenerateResult r = provider.generate("k", base, "m", "p", "l", false);
        assertEquals("http://x/c.mp3", r.audioUrl());
    }

    @Test
    void generate_success_durationFromDataDurationMs() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/a.mp3\",\"duration_ms\":5000}}");
        MusicProvider.GenerateResult r = provider.generate("k", base, "m", "p", "l", false);
        assertEquals(Integer.valueOf(5000), r.durationMs());
    }

    @Test
    void generate_success_durationFromDataDurationSeconds() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/a.mp3\",\"duration\":2.5}}");
        MusicProvider.GenerateResult r = provider.generate("k", base, "m", "p", "l", false);
        assertEquals(Integer.valueOf(2500), r.durationMs());
    }

    @Test
    void generate_success_durationFromTopLevelDurationMs() {
        preset(200, "{\"audio_url\":\"http://x/a.mp3\",\"duration_ms\":7000}");
        MusicProvider.GenerateResult r = provider.generate("k", base, "m", "p", "l", false);
        assertEquals(Integer.valueOf(7000), r.durationMs());
    }

    @Test
    void generate_success_durationFromTopLevelDurationSeconds() {
        preset(200, "{\"audio_url\":\"http://x/a.mp3\",\"duration\":3.0}");
        MusicProvider.GenerateResult r = provider.generate("k", base, "m", "p", "l", false);
        assertEquals(Integer.valueOf(3000), r.durationMs());
    }

    @Test
    void generate_success_durationNullWhenAbsent() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/a.mp3\"}}");
        MusicProvider.GenerateResult r = provider.generate("k", base, "m", "p", "l", false);
        assertNull(r.durationMs());
    }

    // ---------- generate: request shaping ----------

    @Test
    void generate_sendsAuthorizationBearerHeader() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/a.mp3\"}}");
        provider.generate("secret-key", base, "m", "p", "l", false);
        assertEquals("Bearer secret-key", lastAuth.get());
    }

    @Test
    void generate_instrumentalTrue_forcesEmptyLyricsInBody() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/a.mp3\"}}");
        provider.generate("k", base, "m", "some prompt", "some lyrics", true);
        String body = lastBody.get();
        assertTrue(body.contains("\"lyrics\":\"\""), body);
    }

    @Test
    void generate_blankModelId_defaultsToAceStep() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/a.mp3\"}}");
        provider.generate("k", base, null, "p", "l", false);
        String body = lastBody.get();
        assertTrue(body.contains("\"model\":\"ace-step\""), body);
    }

    @Test
    void generate_stripsTrailingSlashesFromApiBase() {
        preset(200, "{\"data\":{\"audio_url\":\"http://x/a.mp3\"}}");
        provider.generate("k", base + "///", "m", "p", "l", false);
        assertEquals("/api/v1/generate", lastPath.get());
    }

    // ---------- generate: error mapping ----------

    @Test
    void generate_connectionFailure_throws() {
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", "http://[::1]:1", "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("请求作曲接口失败"), ex.getMessage());
    }

    @Test
    void generate_httpNon2xx_throwsWithCode() {
        preset(500, "boom");
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", base, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("HTTP 500"), ex.getMessage());
    }

    @Test
    void generate_invalidJson_throwsParseFailure() {
        preset(200, "not-json-at-all");
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", base, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("作曲接口响应解析失败"), ex.getMessage());
    }

    @Test
    void generate_missingAudioUrl_throws() {
        preset(200, "{\"data\":{\"duration_ms\":1000}}");
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", base, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("作曲接口未返回音频地址"), ex.getMessage());
    }

    @Test
    void generate_longErrorBody_isTruncated() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 500; i++) {
            sb.append('x');
        }
        preset(500, sb.toString());
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", base, "m", "p", "l", false));
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().endsWith("…"), ex.getMessage());
    }

    // ---------- probe ----------

    @Test
    void probe_blankApiKey_returnsAuthFailed() {
        MusicProvider.ConnectivityResult r = provider.probe("  ", base);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, r.status());
    }

    @Test
    void probe_blankApiKey_detailMentionsKey() {
        MusicProvider.ConnectivityResult r = provider.probe("  ", base);
        assertTrue(r.detail().contains("未配置密钥"), r.detail());
    }

    @Test
    void probe_sendsProbeModelInBody() {
        preset(200, "{}");
        provider.probe("k", base);
        String body = lastBody.get();
        assertTrue(body.contains("\"model\":\"__connectivity_probe__\""), body);
    }

    @Test
    void probe_401_returnsAuthFailed() {
        preset(401, "{}");
        MusicProvider.ConnectivityResult r = provider.probe("k", base);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, r.status());
    }

    @Test
    void probe_403_returnsAuthFailed() {
        preset(403, "{}");
        MusicProvider.ConnectivityResult r = provider.probe("k", base);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, r.status());
    }

    @Test
    void probe_429_returnsRateLimited() {
        preset(429, "{}");
        MusicProvider.ConnectivityResult r = provider.probe("k", base);
        assertEquals(VideoProvider.ConnectivityStatus.RATE_LIMITED, r.status());
    }

    @Test
    void probe_500_returnsProviderError() {
        preset(500, "{}");
        MusicProvider.ConnectivityResult r = provider.probe("k", base);
        assertEquals(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, r.status());
    }

    @Test
    void probe_other4xx_returnsOk() {
        preset(400, "{}");
        MusicProvider.ConnectivityResult r = provider.probe("k", base);
        assertEquals(VideoProvider.ConnectivityStatus.OK, r.status());
    }

    @Test
    void probe_2xx_returnsOk() {
        preset(200, "{}");
        MusicProvider.ConnectivityResult r = provider.probe("k", base);
        assertEquals(VideoProvider.ConnectivityStatus.OK, r.status());
    }

    @Test
    void probe_connectionFailure_returnsUnreachable() {
        MusicProvider.ConnectivityResult r = provider.probe("k", "http://[::1]:1");
        assertEquals(VideoProvider.ConnectivityStatus.UNREACHABLE, r.status());
    }
}
