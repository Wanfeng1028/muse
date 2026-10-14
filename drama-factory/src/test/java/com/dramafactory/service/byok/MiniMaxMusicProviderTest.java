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

class MiniMaxMusicProviderTest {

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

    private static final String BASE = "https://api.minimaxi.com";

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.minimaxAuth(any()))
                .thenReturn(Map.entry("Authorization", "Bearer <redacted>"));
        gateway = new RecordingGateway();
        provider = new MiniMaxMusicProvider(resolver, new ObjectMapper(), gateway);
    }

    @Test
    void generateOk() {
        gateway.enqueue(200, "{\"data\":{\"audio\":\"https://x/y.mp3\"},\"base_resp\":{\"status_code\":0,\"status_msg\":\"success\"},\"extra_info\":{\"music_duration\":30000}}");
        MusicProvider.GenerateResult result = provider.generate(
                "k", BASE, "music-3.0", "pop", "la la", false);
        assertEquals("https://x/y.mp3", result.audioUrl());
        assertEquals(30000, result.durationMs());
    }

    @Test
    void generateLogicError() {
        gateway.enqueue(200, "{\"base_resp\":{\"status_code\":1004,\"status_msg\":\"auth failed\"}}");
        assertThrows(RuntimeException.class, () -> provider.generate(
                "k", BASE, "music-3.0", "pop", "la la", false));
    }

    @Test
    void instrumentalRequiresNoLyrics() {
        assertThrows(IllegalArgumentException.class, () -> provider.generate(
                "k", BASE, "music-3.0", "pop", "", false));

        gateway.enqueue(200, "{\"data\":{\"audio\":\"https://x/y.mp3\"},\"base_resp\":{\"status_code\":0,\"status_msg\":\"success\"},\"extra_info\":{\"music_duration\":10000}}");
        MusicProvider.GenerateResult result = provider.generate(
                "k", BASE, "music-3.0", "pop", null, true);
        assertEquals("https://x/y.mp3", result.audioUrl());
    }

    @Test
    void probeOk() {
        gateway.enqueue(400, "{\"base_resp\":{\"status_code\":2001}}");
        MusicProvider.ConnectivityResult result = provider.probe(
                "k", BASE);
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
    }

    @Test
    void probeAuthFailed() {
        gateway.enqueue(401, "");
        MusicProvider.ConnectivityResult result = provider.probe(
                "k", BASE);
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }

    @Test
    void probeNoKey() {
        when(resolver.minimaxAuth(any())).thenReturn(null);
        assertThrows(IllegalStateException.class, () -> provider.generate(
                "k", BASE, "music-3.0", "pop", "la la", false));
    }
}
