
package com.dramafactory.service.video;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.service.CredentialResolver;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpRequest;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

class QwenVideoProviderSubmitPollRecordingTest {

    private static final String SUBMIT_RESPONSE = "{\"output\":{\"task_id\":\"task-abc-123\",\"task_status\":\"PENDING\"},\"request_id\":\"req-submit-1\"}";
    private static final String POLL_PROCESSING_RESPONSE = "{\"output\":{\"task_id\":\"task-abc-123\",\"task_status\":\"RUNNING\"},\"request_id\":\"req-poll-1\"}";
    private static final String POLL_COMPLETED_RESPONSE = "{\"output\":{\"task_id\":\"task-abc-123\",\"task_status\":\"SUCCEEDED\",\"video_url\":\"https://cdn.example.com/out/final.mp4\"},\"request_id\":\"req-poll-2\"}";

    private static final String SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis";
    private static final String POLL_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/task-abc-123";

    private ObjectMapper objectMapper;
    private CredentialResolver credentialResolver;
    private RecordingGateway gateway;
    private QwenVideoProvider provider;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        credentialResolver = mock(CredentialResolver.class);
        when(credentialResolver.dashscopeAuth(anyString())).thenReturn(Map.entry("Authorization", "Bearer test-api-key"));
        gateway = new RecordingGateway();
        provider = new QwenVideoProvider(credentialResolver, objectMapper, gateway);
    }

    @Test
    void submitReturnsTaskIdAndPostsToSubmitEndpoint() throws Exception {
        gateway.enqueue(200, SUBMIT_RESPONSE);

        String taskId = provider.submit(shot(), 5);

        assertEquals("task-abc-123", taskId);
        assertNotNull(gateway.lastRequest);
        assertEquals("POST", gateway.lastRequest.method());
        assertEquals(URI.create(SUBMIT_URL), gateway.lastRequest.uri());
    }

    @Test
    void submitSendsBearerAuthorizationHeader() throws Exception {
        gateway.enqueue(200, SUBMIT_RESPONSE);

        provider.submit(shot(), 5);

        String auth = gateway.lastRequest.headers().firstValue("Authorization").orElse(null);
        assertEquals("Bearer test-api-key", auth);
    }

    @Test
    void pollReturnsProcessingWhileTaskRunning() throws Exception {
        gateway.enqueue(200, POLL_PROCESSING_RESPONSE);

        VideoProvider.ProbeResult result = provider.poll("task-abc-123");

        assertEquals(VideoProvider.RemoteStatus.PROCESSING, result.status());
        assertNull(result.videoUrl());
        assertEquals(0, result.progress());
    }

    @Test
    void pollReturnsCompletedWithVideoUrl() throws Exception {
        gateway.enqueue(200, POLL_COMPLETED_RESPONSE);

        VideoProvider.ProbeResult result = provider.poll("task-abc-123");

        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
        assertEquals("https://cdn.example.com/out/final.mp4", result.videoUrl());
        assertEquals(100, result.progress());
    }

    @Test
    void pollUsesTaskScopedEndpoint() throws Exception {
        gateway.enqueue(200, POLL_PROCESSING_RESPONSE);

        provider.poll("task-abc-123");

        assertNotNull(gateway.lastRequest);
        assertEquals("GET", gateway.lastRequest.method());
        assertEquals(URI.create(POLL_URL), gateway.lastRequest.uri());
    }

    @Test
    void pollReturnsFailedOnErrorStatus() throws Exception {
        gateway.enqueue(200, "{\"output\":{\"task_id\":\"task-abc-123\",\"task_status\":\"FAILED\",\"message\":\"model rejected input\"},\"request_id\":\"req-poll-3\"}");

        VideoProvider.ProbeResult result = provider.poll("task-abc-123");

        assertEquals(VideoProvider.RemoteStatus.FAILED, result.status());
        assertNotNull(result.errorMessage());
        assertTrue(result.errorMessage().contains("model rejected input"));
    }

    private Shot shot() {
        Shot shot = new Shot();
        shot.setDescription("a lone astronaut walking across a crimson desert");
        shot.setShotSize(ShotSize.YUAN_JING);
        shot.setCameraMove(CameraMove.GU_DING);
        return shot;
    }

    static class RecordingGateway implements VideoHttpGateway {
        HttpRequest lastRequest;
        private final Deque<VideoHttpGateway.GatewayResponse> queue = new ArrayDeque<>();
        void enqueue(int statusCode, String body) { queue.add(new VideoHttpGateway.GatewayResponse(statusCode, body)); }
        @Override
        public VideoHttpGateway.GatewayResponse exchange(HttpRequest request) {
            this.lastRequest = request;
            VideoHttpGateway.GatewayResponse next = queue.poll();
            if (next == null) { throw new IllegalStateException("no recorded response left"); }
            return next;
        }
    }
}
