package com.dramafactory.service.byok;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.byok.MusicProvider.ConnectivityResult;
import com.dramafactory.service.byok.MusicProvider.GenerateResult;
import com.dramafactory.service.video.VideoProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class MiniMaxMusicProviderBranchTest {

    private static final String BASE = "https://api.minimaxi.com";

    private static final String GENERATE_OK =
            "{\"data\":{\"audio\":\"https://x/y.mp3\"},\"base_resp\":{\"status_code\":0,\"status_msg\":\"success\"},\"extra_info\":{\"music_duration\":30000}}";

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
    private MiniMaxMusicProvider provider;

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.minimaxAuth(any())).thenReturn(Map.entry("Authorization", "Bearer <redacted>"));
        gateway = new RecordingGateway();
        provider = new MiniMaxMusicProvider(resolver, new ObjectMapper(), gateway);
    }

    // 分支：generate/auth == null -> IllegalStateException 未配置密钥
    @Test
    void generateNoAuthNullEntry() {
        when(resolver.minimaxAuth(any())).thenReturn(null);
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", BASE, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("未配置密钥"));
    }

    // 分支：generate/auth.getKey().isBlank() -> IllegalStateException 未配置密钥
    @Test
    void generateNoAuthBlankKey() {
        when(resolver.minimaxAuth(any())).thenReturn(Map.entry("", "Bearer x"));
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> provider.generate("k", BASE, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("未配置密钥"));
    }

    // 分支：generate/网关抛异常 -> RuntimeException HTTP -1
    @Test
    void generateGatewayThrows() {
        ByokHttpGateway exploding = req -> {
            throw new RuntimeException("boom");
        };
        MiniMaxMusicProvider p = new MiniMaxMusicProvider(resolver, new ObjectMapper(), exploding);
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> p.generate("k", BASE, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("HTTP -1"));
    }

    // 分支：generate/响应码 500 -> RuntimeException HTTP 500
    @Test
    void generateHttp500Throws() {
        gateway.enqueue(500, "err");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.generate("k", BASE, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("HTTP 500"));
    }

    // 分支：generate/readTree(null) 抛异常 -> RuntimeException HTTP 200
    @Test
    void generateNullBodyParseFails() {
        gateway.enqueue(200, null);
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.generate("k", BASE, "m", "p", "l", false));
        assertEquals("MiniMax 音乐生成失败, HTTP 200", ex.getMessage());
    }

    // 分支：generate/status_code!=0 且 status_msg 缺失为空串 -> RuntimeException MiniMax 生成失败：
    @Test
    void generateBlankStatusMsg() {
        gateway.enqueue(200, "{\"base_resp\":{\"status_code\":1004}}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.generate("k", BASE, "m", "p", "l", false));
        assertTrue(ex.getMessage().startsWith("MiniMax 生成失败："));
    }

    // 分支：generate/data.audio 缺失 -> asText("") 空 -> RuntimeException 未返回音频地址
    @Test
    void generateNullAudioThrows() {
        gateway.enqueue(200, "{\"data\":{},\"base_resp\":{\"status_code\":0}}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.generate("k", BASE, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("未返回音频地址"));
    }

    // 分支：generate/data.audio 为空白 -> RuntimeException 未返回音频地址
    @Test
    void generateBlankAudioThrows() {
        gateway.enqueue(200, "{\"data\":{\"audio\":\" \"},\"base_resp\":{\"status_code\":0}}");
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.generate("k", BASE, "m", "p", "l", false));
        assertTrue(ex.getMessage().contains("未返回音频地址"));
    }

    // 分支：generate/extra_info.music_duration 缺失 -> durationMs 为 null
    @Test
    void generateNoDurationNull() {
        gateway.enqueue(200, "{\"data\":{\"audio\":\"https://x/y.mp3\"},\"base_resp\":{\"status_code\":0}}");
        GenerateResult result = provider.generate("k", BASE, "m", "p", "l", false);
        assertEquals("https://x/y.mp3", result.audioUrl());
        assertNull(result.durationMs());
    }

    // 分支：generate/music_duration 为字符串 -> isNumber() false -> durationMs 为 null
    @Test
    void generateStringDurationNull() {
        gateway.enqueue(200, "{\"data\":{\"audio\":\"https://x/y.mp3\"},\"base_resp\":{\"status_code\":0},\"extra_info\":{\"music_duration\":\"long\"}}");
        GenerateResult result = provider.generate("k", BASE, "m", "p", "l", false);
        assertEquals("https://x/y.mp3", result.audioUrl());
        assertNull(result.durationMs());
    }

    // 分支：normalizeBase/apiBase==null -> 默认 https://api.minimaxi.com
    @Test
    void generateNullBaseUsesDefault() {
        gateway.enqueue(200, GENERATE_OK);
        provider.generate("k", null, "m", "p", "l", false);
        assertTrue(gateway.lastRequest.uri().toString().startsWith("https://api.minimaxi.com/v1/music_generation"));
    }

    // 分支：normalizeBase/apiBase 为空白 -> 默认 https://api.minimaxi.com
    @Test
    void generateBlankBaseUsesDefault() {
        gateway.enqueue(200, GENERATE_OK);
        provider.generate("k", " ", "m", "p", "l", false);
        assertTrue(gateway.lastRequest.uri().toString().startsWith("https://api.minimaxi.com/v1/music_generation"));
    }

    // 分支：normalizeBase/末尾多个斜杠被剥离 -> uri 恰为 https://api.minimaxi.com/v1/music_generation
    @Test
    void generateTrailingSlashesStripped() {
        gateway.enqueue(200, GENERATE_OK);
        provider.generate("k", "https://api.minimaxi.com///", "m", "p", "l", false);
        assertEquals("https://api.minimaxi.com/v1/music_generation", gateway.lastRequest.uri().toString());
    }

    // 分支：probe/auth.getKey().isBlank() -> AUTH_FAILED
    @Test
    void probeBlankKeyAuthFailed() {
        when(resolver.minimaxAuth(any())).thenReturn(Map.entry("", "Bearer x"));
        ConnectivityResult result = provider.probe("k", BASE);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    // 分支：probe/网关抛异常 -> UNREACHABLE 无法连接
    @Test
    void probeGatewayThrows() {
        ByokHttpGateway exploding = req -> {
            throw new RuntimeException("boom");
        };
        MiniMaxMusicProvider p = new MiniMaxMusicProvider(resolver, new ObjectMapper(), exploding);
        ConnectivityResult result = p.probe("k", BASE);
        assertEquals(VideoProvider.ConnectivityStatus.UNREACHABLE, result.status());
        assertTrue(result.detail().contains("无法连接"));
    }

    // 分支：probe/code == 429 -> RATE_LIMITED
    @Test
    void probeRateLimited() {
        gateway.enqueue(429, "");
        ConnectivityResult result = provider.probe("k", BASE);
        assertEquals(VideoProvider.ConnectivityStatus.RATE_LIMITED, result.status());
    }

    // 分支：probe/code >= 500 -> PROVIDER_ERROR
    @Test
    void probeServerError() {
        gateway.enqueue(500, "");
        ConnectivityResult result = provider.probe("k", BASE);
        assertEquals(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, result.status());
    }

    // 分支：probe/code == 200 -> 最后的 return OK
    @Test
    void probeOk200() {
        gateway.enqueue(200, "{}");
        ConnectivityResult result = provider.probe("k", BASE);
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
    }

    // 分支：probe/code == 403 -> AUTH_FAILED
    @Test
    void probeForbidden403() {
        gateway.enqueue(403, "");
        ConnectivityResult result = provider.probe("k", BASE);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    // 分支：generate/prompt == null -> body.put("prompt", "") 分支
    @Test
    void generateNullPromptAndLyricsDefaults() {
        gateway.enqueue(200, GENERATE_OK);
        GenerateResult result = provider.generate("k", BASE, "m", null, null, true);
        assertEquals("https://x/y.mp3", result.audioUrl());
    }
}
