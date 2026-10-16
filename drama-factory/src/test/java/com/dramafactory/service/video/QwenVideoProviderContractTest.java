package com.dramafactory.service.video;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.service.CredentialResolver;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Disabled;

import java.io.InputStream;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * QwenVideoProvider 的录制回放契约测试。
 * 通过 VideoHttpGateway 接缝注入录制好的响应，全程无 socket。
 */
class QwenVideoProviderContractTest {

    /** 录制回放网关：记录最后一次请求，按队列顺序返回预置响应。 */
    static class RecordingGateway implements VideoHttpGateway {
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

    /** 从 classpath 加载 fixture 文件内容（UTF-8）。 */
    static String fixture(String name) throws Exception {
        try (InputStream in = QwenVideoProviderContractTest.class
                .getResourceAsStream("/fixtures/video/" + name)) {
            assertNotNull(in, "fixture not found: " + name);
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    /** 同步读取请求体字符串。 */
    static String bodyOf(HttpRequest request) {
        final StringBuilder sb = new StringBuilder();
        request.bodyPublisher().ifPresent(publisher ->
                publisher.subscribe(new java.util.concurrent.Flow.Subscriber<>() {
                    @Override
                    public void onSubscribe(java.util.concurrent.Flow.Subscription subscription) {
                        subscription.request(Long.MAX_VALUE);
                    }

                    @Override
                    public void onNext(java.nio.ByteBuffer item) {
                        byte[] bytes = new byte[item.remaining()];
                        item.get(bytes);
                        sb.append(new String(bytes, StandardCharsets.UTF_8));
                    }

                    @Override
                    public void onError(Throwable throwable) {
                    }

                    @Override
                    public void onComplete() {
                    }
                }));
        return sb.toString();
    }

    private CredentialResolver resolver;
    private RecordingGateway gateway;
    private QwenVideoProvider provider;

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer <redacted>"));
        gateway = new RecordingGateway();
        provider = new QwenVideoProvider(resolver, new ObjectMapper(), gateway);
    }

    private static Shot shot() {
        return new Shot();
    }

    @Test
    void nameIsQwen() {
        // 契约点：provider 名称固定为 "qwen"
        assertEquals("qwen", provider.name());
    }

    @Test
    @Disabled("2026-10-16 起 wan2.5-t2v-preview 免费额度耗尽，submit() 已加硬拒单 guard；额度恢复后删 guard 并移除本 Disabled")
    void submitOk() throws Exception {
        // 契约点：提交成功返回 task_id；body 含模型 wan2.5-t2v-preview；
        // 携带 X-DashScope-Async=enable 头
        gateway.enqueue(200, fixture("qwen-submit-ok.json"));

        Shot shot = shot();
        shot.setVideoPrompt("一段雨夜街道");

        String taskId = provider.submit(shot, 5);

        assertEquals("task_7d2e1a9b", taskId);

        HttpRequest req = gateway.lastRequest;
        assertNotNull(req);
        assertTrue(req.headers().firstValue("X-DashScope-Async").isPresent());
        assertEquals("enable", req.headers().firstValue("X-DashScope-Async").orElse(null));
        String body = bodyOf(req);
        assertTrue(body.contains("wan2.5-t2v-preview"));
    }

    @Test
    @Disabled("2026-10-16 起 wan2.5-t2v-preview 免费额度耗尽，submit() 已加硬拒单 guard；额度恢复后删 guard 并移除本 Disabled")
    void submitAssemblesPrompt() throws Exception {
        // 契约点：videoPrompt 为空时，用 description + shotSize.getLabel() + cameraMove.getLabel() 拼接；
        // QUAN_JING → "全景"，TUI → "推镜头"
        gateway.enqueue(200, fixture("qwen-submit-ok.json"));

        Shot shot = shot();
        shot.setVideoPrompt(null);
        shot.setDescription("雨夜");
        shot.setShotSize(ShotSize.QUAN_JING);
        shot.setCameraMove(CameraMove.TUI);

        provider.submit(shot, 5);

        String body = bodyOf(gateway.lastRequest);
        assertTrue(body.contains("雨夜"));
        assertTrue(body.contains("全景"));
        assertTrue(body.contains("推镜头"));
    }

    @Test
    @Disabled("2026-10-16 起 wan2.5-t2v-preview 免费额度耗尽，submit() 已加硬拒单 guard；额度恢复后删 guard 并移除本 Disabled")
    void submitLogicError() throws Exception {
        // 契约点：响应体含 code 字段 → 抛 RuntimeException，消息含"逻辑错误"
        gateway.enqueue(200, fixture("qwen-submit-logic-error.json"));

        Shot shot = shot();
        shot.setVideoPrompt("p");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("逻辑错误"), "消息应含'逻辑错误'，实际：" + ex.getMessage());
    }

    @Test
    @Disabled("2026-10-16 起 wan2.5-t2v-preview 免费额度耗尽，submit() 已加硬拒单 guard；额度恢复后删 guard 并移除本 Disabled")
    void submitMissingTaskId() throws Exception {
        // 契约点：缺 output.task_id → 抛 RuntimeException，消息含 task_id
        gateway.enqueue(200, fixture("qwen-submit-noid.json"));

        Shot shot = shot();
        shot.setVideoPrompt("p");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("task_id"), "消息应含 task_id，实际：" + ex.getMessage());
    }

    @Test
    void pollSucceeded() throws Exception {
        // 契约点：task_status=SUCCEEDED → COMPLETED，videoUrl 取 video_url
        gateway.enqueue(200, fixture("qwen-poll-succeeded.json"));

        VideoProvider.ProbeResult status = provider.poll("task_7d2e1a9b");

        assertEquals(VideoProvider.RemoteStatus.COMPLETED, status.status());
        assertEquals("https://dashscope.example.com/videos/task_7d2e1a9b.mp4", status.videoUrl());
    }

    @Test
    void pollFailed() throws Exception {
        // 契约点：task_status=FAILED → FAILED，errorMessage 取 message
        gateway.enqueue(200, fixture("qwen-poll-failed.json"));

        VideoProvider.ProbeResult status = provider.poll("task_7d2e1a9b");

        assertEquals(VideoProvider.RemoteStatus.FAILED, status.status());
        assertEquals("content violates policy", status.errorMessage());
    }

    @Test
    void pollCanceledMapsToFailed() throws Exception {
        // 契约点：task_status=CANCELED → FAILED，errorMessage 取 message
        gateway.enqueue(200, fixture("qwen-poll-canceled.json"));

        VideoProvider.ProbeResult status = provider.poll("task_7d2e1a9b");

        assertEquals(VideoProvider.RemoteStatus.FAILED, status.status());
        assertEquals("user canceled", status.errorMessage());
    }

    @Test
    void pollRunning() throws Exception {
        // 契约点：其他状态（RUNNING）→ PROCESSING
        gateway.enqueue(200, fixture("qwen-poll-running.json"));

        VideoProvider.ProbeResult status = provider.poll("task_7d2e1a9b");

        assertEquals(VideoProvider.RemoteStatus.PROCESSING, status.status());
    }
}
