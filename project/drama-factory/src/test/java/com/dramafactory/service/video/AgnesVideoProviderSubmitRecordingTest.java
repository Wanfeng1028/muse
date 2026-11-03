
package com.dramafactory.service.video;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.service.CredentialResolver;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.http.HttpRequest;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * AgnesVideoProvider.submit 的录制回放测试。
 *
 * 录制方式声明：2026-10-15 编排脚本直调 Agnes/Qwen 官方接口录制；Agnes 提交时服务端返回
 * 503 队列满，故 submit 成功路径暂无真实录像（用契约形状手写夹具），失败路径为真实录像；
 * Qwen submit/poll 均为真实录像。
 *
 * 录像 1（Agnes submit 真实响应，队列满）：HTTP 503，响应体原文见 REC_503_BODY。
 */
class AgnesVideoProviderSubmitRecordingTest {

    /** 录像 1：Agnes submit 真实响应，HTTP 503，队列满。 */
    private static final String REC_503_BODY =
            "{\"code\":\"video_queue_full\",\"message\":\"video queue is full, please retry later (request id: 20261014174900366230677Ul7gsKNt)\",\"data\":null}";

    private RecordingGateway gateway;
    private CredentialResolver resolver;
    private AgnesVideoProvider provider;

    @BeforeEach
    void setUp() {
        gateway = new RecordingGateway();
        resolver = mock(CredentialResolver.class);
        when(resolver.agnesAuth(anyString())).thenReturn(Map.entry("Authorization", "Bearer test"));
        provider = new AgnesVideoProvider(resolver, gateway);
    }

    @Test
    void submit_queueFull_recording() {
        gateway.enqueue(503, REC_503_BODY);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(newShot(), 5));
        assertTrue(ex.getMessage().contains("503"), "message 应包含状态码 503，实际: " + ex.getMessage());
        assertTrue(ex.getMessage().contains("video queue is full"),
                "message 应包含真实录像中的队列满文案，实际: " + ex.getMessage());

        assertEquals("https://apihub.agnes-ai.com/v1/videos", gateway.lastRequest.uri().toString());
        assertEquals("POST", gateway.lastRequest.method());
    }

    @Test
    void submit_authMissing_throwsIllegalState() {
        when(resolver.agnesAuth(anyString())).thenReturn(null);

        IllegalStateException ex = assertThrows(IllegalStateException.class, () -> provider.submit(newShot(), 5));
        assertTrue(ex.getMessage().contains("未配置 Agnes 密钥"), "实际: " + ex.getMessage());
    }

    @Test
    void submit_gatewayThrows_wrapped() {
        gateway.failWith(new RuntimeException("boom"));

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(newShot(), 5));
        assertTrue(ex.getMessage().contains("请求 Agnes 提交接口失败"), "实际: " + ex.getMessage());
    }

    @Test
    void submit_429_throwsRateLimited() {
        gateway.enqueue(429, "");

        RateLimitedException ex = assertThrows(RateLimitedException.class, () -> provider.submit(newShot(), 5));
        assertEquals(60, ex.getRetryAfterSeconds());
    }

    @Test
    void submit_200_missingVideoId() {
        gateway.enqueue(200, "{\"data\":{}}");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(newShot(), 5));
        assertTrue(ex.getMessage().contains("缺少 video_id/id 字段"), "实际: " + ex.getMessage());
    }

    @Test
    void submit_200_idFallback() {
        gateway.enqueue(200, "{\"id\":\"abc-1\"}");

        assertEquals("abc-1", provider.submit(newShot(), 5));
    }

    @Test
    void submit_200_videoIdPreferred() {
        gateway.enqueue(200, "{\"video_id\":\"v-9\",\"id\":\"abc-1\"}");

        assertEquals("v-9", provider.submit(newShot(), 5));
    }

    @Test
    void submit_200_invalidJson() {
        gateway.enqueue(200, "{not json");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(newShot(), 5));
        assertTrue(ex.getMessage().contains("解析 Agnes 提交响应失败"), "实际: " + ex.getMessage());
    }

    @Test
    void submit_promptFallback拼接() {
        Shot shot = newShot();
        shot.setVideoPrompt(null);
        shot.setDescription("雨夜");
        shot.setShotSize(ShotSize.TE_XIE);
        shot.setCameraMove(CameraMove.GU_DING);
        gateway.enqueue(200, "{\"video_id\":\"v1\"}");

        assertEquals("v1", provider.submit(shot, 5));
    }

    private static Shot newShot() {
        return new Shot();
    }

    /**
     * 录制回放用 gateway：按录制顺序回放状态码与响应体，只记录 HttpRequest，
     * 不读取也不打印任何请求头值（避免泄漏密钥）。
     */
    static class RecordingGateway implements VideoHttpGateway {

        private final Deque<RecordedResponse> responses = new ArrayDeque<>();
        private RuntimeException failure;
        HttpRequest lastRequest;

        void enqueue(int status, String body) {
            responses.addLast(new RecordedResponse(status, body));
        }

        void failWith(RuntimeException e) {
            this.failure = e;
        }

        @Override
        public VideoHttpGateway.GatewayResponse exchange(HttpRequest request) throws Exception {
            this.lastRequest = request;
            if (failure != null) {
                throw failure;
            }
            if (responses.isEmpty()) {
                throw new IllegalStateException("no recorded response left");
            }
            RecordedResponse r = responses.removeFirst();
            return new VideoHttpGateway.GatewayResponse(r.status, r.body);
        }
    }

    static class RecordedResponse {
        final int status;
        final String body;

        RecordedResponse(int status, String body) {
            this.status = status;
            this.body = body;
        }
    }
}
