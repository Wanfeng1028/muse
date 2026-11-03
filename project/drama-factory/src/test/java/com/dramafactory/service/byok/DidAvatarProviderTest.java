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

class DidAvatarProviderTest {

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
    private DidAvatarProvider provider;

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.didAuth(any()))
                .thenReturn(Map.entry("Authorization", "Basic <redacted>"));
        gateway = new RecordingGateway();
        provider = new DidAvatarProvider(resolver, new ObjectMapper(), gateway);
    }

    @Test
    void submitTextOk() {
        gateway.enqueue(200, "{\"id\":\"tlk_abc\",\"status\":\"created\"}");
        AvatarProvider.SubmitResult result = provider.submit(
                "k", "https://img/x.png", null, "hello");
        assertEquals("tlk_abc", result.talkId());
        assertNotNull(gateway.lastRequest);
        assertEquals("POST", gateway.lastRequest.method());
        assertTrue(gateway.lastRequest.uri().toString().endsWith("/talks"),
                "URI should end with /talks but was: " + gateway.lastRequest.uri());
    }

    @Test
    void submitAudioOk() {
        gateway.enqueue(200, "{\"id\":\"tlk_def\",\"status\":\"created\"}");
        AvatarProvider.SubmitResult result = provider.submit(
                "k", "https://img/x.png", "https://a/y.mp3", null);
        assertEquals("tlk_def", result.talkId());
        assertNotNull(gateway.lastRequest);
        assertEquals("POST", gateway.lastRequest.method());
    }

    @Test
    void submitNoInput() {
        assertThrows(IllegalArgumentException.class, () -> provider.submit(
                "k", "https://img/x.png", null, null));
    }

    @Test
    void pollDone() {
        gateway.enqueue(200, "{\"id\":\"tlk_abc\",\"status\":\"done\",\"result_url\":\"https://r/v.mp4\"}");
        AvatarProvider.PollResult result = provider.poll("k", "tlk_abc");
        assertEquals(AvatarProvider.RemoteStatus.SUCCEEDED, result.status());
        assertEquals("https://r/v.mp4", result.videoUrl());
    }

    @Test
    void pollError() {
        gateway.enqueue(200, "{\"id\":\"tlk_abc\",\"status\":\"error\",\"message\":\"bad face\"}");
        AvatarProvider.PollResult result = provider.poll("k", "tlk_abc");
        assertEquals(AvatarProvider.RemoteStatus.FAILED, result.status());
    }

    @Test
    void probeOk() {
        gateway.enqueue(200, "{\"credits\":[]}");
        AvatarProvider.ConnectivityResult result = provider.probe(
                "k");
        assertEquals(VideoProvider.ConnectivityStatus.OK, result.status());
    }

    @Test
    void probeAuthFailed() {
        gateway.enqueue(401, "");
        AvatarProvider.ConnectivityResult result = provider.probe(
                "k");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
    }
}
