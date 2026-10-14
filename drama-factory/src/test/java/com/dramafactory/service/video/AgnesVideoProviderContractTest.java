package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.CredentialResolver;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

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
 * AgnesVideoProvider 的录制回放契约测试。
 * 通过 VideoHttpGateway 接缝注入录制好的响应，全程无 socket。
 */
class AgnesVideoProviderContractTest {

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
        try (InputStream in = AgnesVideoProviderContractTest.class
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
    private AgnesVideoProvider provider;

    @BeforeEach
    void setUp() {
        resolver = mock(CredentialResolver.class);
        when(resolver.agnesAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer <redacted>"));
        gateway = new RecordingGateway();
        provider = new AgnesVideoProvider(resolver, gateway);
    }

    private static Shot shot() {
        return new Shot();
    }

    @Test
    void nameIsAgnes() {
        // 契约点：provider 名称固定为 "agnes"
        assertEquals("agnes", provider.name());
    }

    @Test
    void submitOk() throws Exception {
        // 契约点：提交成功返回 video_id；请求命中 apihub.agnes-ai.com /v1/videos 且为 POST；
        // 携带鉴权头；body 含模型名与 prompt 文本
        gateway.enqueue(200, fixture("agnes-submit-ok.json"));

        Shot shot = shot();
        shot.setVideoPrompt("一段雨夜街道");

        String videoId = provider.submit(shot, 5);

        assertEquals("vid_9f3a2b1c", videoId);

        HttpRequest req = gateway.lastRequest;
        assertNotNull(req);
        assertEquals("apihub.agnes-ai.com", req.uri().getHost());
        assertEquals("/v1/videos", req.uri().getPath());
        assertEquals("POST", req.method());
        assertTrue(req.headers().firstValue("Authorization").isPresent());
        String body = bodyOf(req);
        assertTrue(body.contains("agnes-video-2.5-flash"));
        assertTrue(body.contains("一段雨夜街道"));
    }

    @Test
    void submitAssemblesPromptWhenBlank() throws Exception {
        // 契约点：videoPrompt 为空时，用 description 拼接出 prompt（只断言 description 文本出现）
        gateway.enqueue(200, fixture("agnes-submit-ok.json"));

        Shot shot = shot();
        shot.setVideoPrompt(null);
        shot.setDescription("雨夜");

        provider.submit(shot, 5);

        String body = bodyOf(gateway.lastRequest);
        assertTrue(body.contains("雨夜"));
    }

    @Test
    void submit429ThrowsRateLimited() throws Exception {
        // 契约点：HTTP 429 必须抛出 RateLimitedException
        gateway.enqueue(429, "{\"error\":\"too many requests\"}");

        Shot shot = shot();
        shot.setVideoPrompt("p");

        assertThrows(RateLimitedException.class, () -> provider.submit(shot, 5));
    }

    @Test
    void submit500ThrowsRuntimeWithStatus() throws Exception {
        // 契约点：非 2xx（非 429）抛 RuntimeException，消息含状态码
        gateway.enqueue(500, "{\"error\":\"boom\"}");

        Shot shot = shot();
        shot.setVideoPrompt("p");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("500"), "消息应含状态码 500，实际：" + ex.getMessage());
    }

    @Test
    void submitMissingIdThrows() throws Exception {
        // 契约点：响应缺 video_id/id 时抛 RuntimeException
        gateway.enqueue(200, fixture("agnes-submit-noid.json"));

        Shot shot = shot();
        shot.setVideoPrompt("p");

        assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
    }

    @Test
    void pollCompleted() throws Exception {
        // 契约点：status=completed → COMPLETED，videoUrl 取 metadata.url，progress=100
        gateway.enqueue(200, fixture("agnes-poll-completed.json"));

        VideoProvider.ProbeResult status = provider.poll("vid_9f3a2b1c");

        assertEquals(VideoProvider.RemoteStatus.COMPLETED, status.status());
        assertEquals("https://cdn.example.com/videos/vid_9f3a2b1c.mp4", status.videoUrl());
        assertEquals(100, status.progress());
    }

    @Test
    void pollFailed() throws Exception {
        // 契约点：status=failed → FAILED，errorMessage 取 message
        gateway.enqueue(200, fixture("agnes-poll-failed.json"));

        VideoProvider.ProbeResult status = provider.poll("vid_9f3a2b1c");

        assertEquals(VideoProvider.RemoteStatus.FAILED, status.status());
        assertEquals("render timeout after 300s", status.errorMessage());
    }

    @Test
    void pollProcessing() throws Exception {
        // 契约点：其他状态 → PROCESSING，尽力解析 progress
        gateway.enqueue(200, fixture("agnes-poll-processing.json"));

        VideoProvider.ProbeResult status = provider.poll("vid_9f3a2b1c");

        assertEquals(VideoProvider.RemoteStatus.PROCESSING, status.status());
        assertEquals(42, status.progress());
    }

    @Test
    void gatewayThrowsWrappedForSubmit() {
        // 契约点：网关抛异常时，提交路径包装为"请求 Agnes 提交接口失败"
        VideoHttpGateway throwing = request -> {
            throw new Exception("network down");
        };
        AgnesVideoProvider failing = new AgnesVideoProvider(resolver, throwing);

        Shot shot = shot();
        shot.setVideoPrompt("p");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> failing.submit(shot, 5));
        assertTrue(ex.getMessage().contains("请求 Agnes 提交接口失败"),
                "消息应含包装文案，实际：" + ex.getMessage());
    }
}
