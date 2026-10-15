package com.dramafactory.service.video;

import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.service.CredentialResolver;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.net.http.HttpRequest;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * QwenVideoProvider 分支覆盖补测（第二轮）。
 *
 * 说明（不可达分支结论）：
 * 源码 293 行 `if (text == null) return "";` —— 经分析不可达：
 * submit/poll 中调用 truncate(body, ...) 之前都执行了
 * `String body = response.body() == null ? "" : response.body();`，
 * 因此传入 truncate 的 text 永不为 null。此分支无法在测试中触达，
 * 故不编写测试，也不用反射硬调私有方法。
 */
class QwenVideoProviderBranch2Test {

    /** 录制回放假网关：enqueue 入队响应，lastRequest 记录最后一次请求。 */
    static class RecordingGateway implements VideoHttpGateway {
        private final Deque<GatewayResponse> responses = new ArrayDeque<>();
        HttpRequest lastRequest;

        void enqueue(int statusCode, String body) {
            responses.add(new GatewayResponse(statusCode, body));
        }

        @Override
        public GatewayResponse exchange(HttpRequest request) {
            this.lastRequest = request;
            return responses.poll();
        }
    }

    /** 抛异常网关：exchange 直接抛 RuntimeException。 */
    static class ThrowingGateway implements VideoHttpGateway {
        @Override
        public GatewayResponse exchange(HttpRequest request) {
            throw new RuntimeException("boom");
        }
    }

    private CredentialResolver okResolver() {
        CredentialResolver r = mock(CredentialResolver.class);
        when(r.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer test-token"));
        return r;
    }

    private CredentialResolver nullResolver() {
        CredentialResolver r = mock(CredentialResolver.class);
        when(r.dashscopeAuth(anyString())).thenReturn(null);
        return r;
    }

    private Shot shotWith(String videoPrompt, String description, ShotSize size, CameraMove move) {
        Shot s = new Shot();
        s.setVideoPrompt(videoPrompt);
        s.setDescription(description);
        s.setShotSize(size);
        s.setCameraMove(move);
        return s;
    }

    private String captureRequestJson(ObjectMapper spyMapper) throws Exception {
        // 注意：provider 调的是 writeValueAsString(Object)（传入 ObjectNode），不是 String 重载
        ArgumentCaptor<ObjectNode> bodyCaptor = ArgumentCaptor.forClass(ObjectNode.class);
        verify(spyMapper, atLeastOnce()).writeValueAsString(bodyCaptor.capture());
        return bodyCaptor.getValue().toString();
    }

    // ---------------------------------------------------------------------
    // probeConnectivity
    // ---------------------------------------------------------------------

    /**
     * 覆盖 110 行 `if (code >= 200 && code < 300)` 复合条件的"非 2xx 且非 404/401/403/429"路径：
     * 网关返回 500 → PROVIDER_ERROR。
     */
    @Test
    void probeConnectivity_500_expectsProviderError() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(500, "{}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        VideoProvider.ConnectivityResult result = provider.probeConnectivity();

        assertNotNull(result);
        assertTrue(result.toString().contains("PROVIDER_ERROR"));
    }

    // ---------------------------------------------------------------------
    // submit: prompt 拼接分支
    // ---------------------------------------------------------------------

    /**
     * 覆盖 130 行 `if (prompt == null || prompt.isBlank())` 的 videoPrompt 非空分支：
     * videoPrompt 有值时应直接使用，请求体 JSON 包含该文案。
     */
    @Test
    void submit_withNonBlankVideoPrompt_expectsPromptUsed() throws Exception {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_id\":\"task-1\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith("一只猫在屋顶", "描述", ShotSize.JIN_JING, CameraMove.TUI);
        provider.submit(shot, 5);

        String requestJson = captureRequestJson(mapper);
        JsonNode json = new ObjectMapper().readTree(requestJson);
        assertEquals("一只猫在屋顶", json.path("input").path("prompt").asText());
    }

    /**
     * 覆盖 132 行 `if (shot.getDescription() != null && !shot.getDescription().isBlank())` 的
     * description==null 分支臂：prompt 中不含 "null" 字样。
     */
    @Test
    void submit_withNullDescription_expectsNoNullInPrompt() throws Exception {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_id\":\"task-2\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith(null, null, ShotSize.JIN_JING, CameraMove.TUI);
        provider.submit(shot, 5);

        String requestJson = captureRequestJson(mapper);
        JsonNode json = new ObjectMapper().readTree(requestJson);
        String prompt = json.path("input").path("prompt").asText();
        assertTrue(!prompt.contains("null"));
    }

    /**
     * 覆盖 132 行 description 为空串分支臂：prompt 中不含 "null"，也不含多余内容。
     */
    @Test
    void submit_withBlankDescription_expectsNoNullInPrompt() throws Exception {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_id\":\"task-3\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith(null, "   ", ShotSize.JIN_JING, CameraMove.TUI);
        provider.submit(shot, 5);

        String requestJson = captureRequestJson(mapper);
        JsonNode json = new ObjectMapper().readTree(requestJson);
        String prompt = json.path("input").path("prompt").asText();
        assertTrue(!prompt.contains("null"));
    }

    /**
     * 覆盖 135 行 `if (shot.getShotSize() != null)` 的 shotSize==null 分支：
     * description 有值、shotSize 不设、cameraMove=GU_DING，submit 成功。
     */
    @Test
    void submit_withNullShotSize_expectsSubmitSucceeds() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_id\":\"task-4\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith(null, "描述", null, CameraMove.GU_DING);
        String taskId = provider.submit(shot, 5);

        assertEquals("task-4", taskId);
    }

    /**
     * 覆盖 136 行 `if (sb.length() > 0)`（shotSize 分支内）sb 为空时不加 "，" 的分支：
     * description 为 null、shotSize=YUAN_JING、cameraMove 不设 → prompt 精确等于 "远景"。
     */
    @Test
    void submit_withOnlyShotSize_expectsPromptEqualsLabel() throws Exception {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_id\":\"task-5\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith(null, null, ShotSize.YUAN_JING, null);
        provider.submit(shot, 5);

        String requestJson = captureRequestJson(mapper);
        JsonNode json = new ObjectMapper().readTree(requestJson);
        assertEquals("远景", json.path("input").path("prompt").asText());
    }

    /**
     * 覆盖 141 行 `if (shot.getCameraMove() != null)` 的 cameraMove==null 分支：
     * description 有值、shotSize 有值、cameraMove 不设，submit 成功。
     */
    @Test
    void submit_withNullCameraMove_expectsSubmitSucceeds() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_id\":\"task-6\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith(null, "描述", ShotSize.ZHONG_JING, null);
        String taskId = provider.submit(shot, 5);

        assertEquals("task-6", taskId);
    }

    /**
     * 覆盖 142 行 `if (sb.length() > 0)`（cameraMove 分支内）sb 为空时不加 "，" 的分支：
     * description/shotSize 均不设、cameraMove=TUI → prompt 精确等于 "推镜头"。
     */
    @Test
    void submit_withOnlyCameraMove_expectsPromptEqualsLabel() throws Exception {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_id\":\"task-7\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith(null, null, null, CameraMove.TUI);
        provider.submit(shot, 5);

        String requestJson = captureRequestJson(mapper);
        JsonNode json = new ObjectMapper().readTree(requestJson);
        assertEquals("推镜头", json.path("input").path("prompt").asText());
    }

    // ---------------------------------------------------------------------
    // submit: 异常分支
    // ---------------------------------------------------------------------

    /**
     * 覆盖 166-167 行：objectMapper.writeValueAsString 抛异常 →
     * RuntimeException("构造通义万相请求体失败...")。
     */
    @Test
    void submit_whenSerializeThrows_expectsBuildRequestBodyException() throws Exception {
        ObjectMapper mapper = spy(new ObjectMapper());
        doThrow(new RuntimeException("boom")).when(mapper).writeValueAsString(any());
        RecordingGateway gw = new RecordingGateway();
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith("prompt", null, null, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("构造通义万相请求体失败"));
    }

    /**
     * 覆盖 188-189 行：submit 时 dashscopeAuth 返回 null →
     * IllegalStateException("未配置 DashScope 密钥...")。
     */
    @Test
    void submit_whenAuthNull_expectsIllegalStateException() {
        RecordingGateway gw = new RecordingGateway();
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(nullResolver(), mapper, gw);

        Shot shot = shotWith("prompt", null, null, null);
        IllegalStateException ex =
                assertThrows(IllegalStateException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("未配置 DashScope 密钥"));
    }

    /**
     * 覆盖 192 行：submit 时 gateway.exchange 抛异常 →
     * RuntimeException("通义万相提交任务请求失败...")。
     */
    @Test
    void submit_whenGatewayThrows_expectsSubmitRequestFailed() {
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, new ThrowingGateway());

        Shot shot = shotWith("prompt", null, null, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("提交任务请求失败"));
    }

    /**
     * 覆盖 197-199 行：submit 网关返回非 2xx（500）→
     * RuntimeException("通义万相提交任务失败, HTTP 500...")。
     */
    @Test
    void submit_whenHttp500_expectsSubmitHttpError() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(500, "server error");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith("prompt", null, null, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("HTTP 500"));
    }

    /**
     * 覆盖 205-207 行：submit 网关返回 200 但 body 非 JSON →
     * RuntimeException("解析通义万相响应失败...")。
     */
    @Test
    void submit_whenBodyNotJson_expectsParseException() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "not-json{{{");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith("prompt", null, null, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("解析通义万相响应失败"));
    }

    /**
     * 覆盖 217 行 `if (json.has("code"))` 命中分支：body 含 code →
     * RuntimeException("通义万相提交任务逻辑错误...")。
     */
    @Test
    void submit_whenResponseHasCode_expectsLogicError() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"code\":\"InvalidParameter\",\"message\":\"bad\"}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith("prompt", null, null, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("逻辑错误"));
    }

    /**
     * 覆盖 taskIdNode.isNull() 分支臂：`{"output":{"task_id":null}}` →
     * RuntimeException("通义万相提交任务未返回 task_id...")。
     */
    @Test
    void submit_whenTaskIdIsNull_expectsMissingTaskIdException() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_id\":null}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith("prompt", null, null, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("未返回 task_id"));
    }

    /**
     * 覆盖 taskIdNode.asText().isBlank() 分支臂：`{"output":{"task_id":"   "}}` →
     * RuntimeException("通义万相提交任务未返回 task_id...")。
     */
    @Test
    void submit_whenTaskIdIsBlank_expectsMissingTaskIdException() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_id\":\"   \"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith("prompt", null, null, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("未返回 task_id"));
    }

    /**
     * 覆盖 taskIdNode.isMissingNode() 分支臂：`{"output":{}}` →
     * RuntimeException("通义万相提交任务未返回 task_id...")。
     */
    @Test
    void submit_whenTaskIdMissing_expectsMissingTaskIdException() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith("prompt", null, null, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("未返回 task_id"));
    }

    /**
     * 覆盖 296/299 行 truncate 超长截断臂：submit 网关 500 且 body 为 400 个 'x'，
     * 异常 message 长度显著小于 400（被截断到 300 以内），且含 "HTTP 500"。
     */
    @Test
    void submit_whenHttp500WithLongBody_expectsTruncatedMessage() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(500, "x".repeat(400));
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        Shot shot = shotWith("prompt", null, null, null);
        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("HTTP 500"));
        assertTrue(ex.getMessage().length() < 400);
    }

    // ---------------------------------------------------------------------
    // poll: 异常与状态分支
    // ---------------------------------------------------------------------

    /**
     * 覆盖 246-247 行：poll 时 dashscopeAuth 返回 null →
     * IllegalStateException("未配置 DashScope 密钥...")。
     */
    @Test
    void poll_whenAuthNull_expectsIllegalStateException() {
        RecordingGateway gw = new RecordingGateway();
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(nullResolver(), mapper, gw);

        IllegalStateException ex =
                assertThrows(IllegalStateException.class, () -> provider.poll("task-x"));
        assertTrue(ex.getMessage().contains("未配置 DashScope 密钥"));
    }

    /**
     * 覆盖 250 行：poll 时 gateway.exchange 抛异常 →
     * RuntimeException("通义万相查询任务请求失败...")。
     */
    @Test
    void poll_whenGatewayThrows_expectsPollRequestFailed() {
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, new ThrowingGateway());

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.poll("task-x"));
        assertTrue(ex.getMessage().contains("查询任务请求失败"));
    }

    /**
     * 覆盖 253-255 行：poll 网关返回 500 →
     * RuntimeException("通义万相查询任务失败, HTTP 500...")。
     */
    @Test
    void poll_whenHttp500_expectsPollHttpError() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(500, "server error");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.poll("task-x"));
        assertTrue(ex.getMessage().contains("HTTP 500"));
    }

    /**
     * 覆盖 261-263 行：poll 网关返回 200 但 body 非 JSON →
     * RuntimeException("解析通义万相查询响应失败...")。
     */
    @Test
    void poll_whenBodyNotJson_expectsParseException() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "not-json{{{");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.poll("task-x"));
        assertTrue(ex.getMessage().contains("解析通义万相查询响应失败"));
    }

    /**
     * 覆盖 266 行 `if (json.has("code"))` 命中分支：poll 响应含 code →
     * RuntimeException("通义万相查询任务逻辑错误...")。
     */
    @Test
    void poll_whenResponseHasCode_expectsLogicError() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"code\":\"Throttling\",\"message\":\"busy\"}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.poll("task-x"));
        assertTrue(ex.getMessage().contains("逻辑错误"));
    }

    /**
     * 覆盖 279-282 行：poll `task_status=FAILED`（带 message）→ ProbeResult status 为 FAILED。
     */
    @Test
    void poll_whenTaskFailed_expectsFailedStatus() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_status\":\"FAILED\",\"message\":\"quota exceeded\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        VideoProvider.ProbeResult result = provider.poll("task-x");

        assertNotNull(result);
        assertEquals(VideoProvider.RemoteStatus.FAILED, result.status());
    }

    /**
     * 覆盖 279-282 行：poll `task_status=CANCELED` → ProbeResult status 为 FAILED。
     */
    @Test
    void poll_whenTaskCanceled_expectsFailedStatus() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_status\":\"CANCELED\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        VideoProvider.ProbeResult result = provider.poll("task-x");

        assertNotNull(result);
        assertEquals(VideoProvider.RemoteStatus.FAILED, result.status());
    }

    /**
     * 覆盖 275-278 行：poll `task_status=SUCCEEDED` → ProbeResult status 为 COMPLETED。
     */
    @Test
    void poll_whenTaskSucceeded_expectsCompletedStatus() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_status\":\"SUCCEEDED\",\"video_url\":\"http://example/v.mp4\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        VideoProvider.ProbeResult result = provider.poll("task-x");

        assertNotNull(result);
        assertEquals(VideoProvider.RemoteStatus.COMPLETED, result.status());
    }

    /**
     * 覆盖 284-285 行 default 分支：poll `task_status=RUNNING` → PROCESSING。
     */
    @Test
    void poll_whenTaskRunning_expectsProcessingStatus() {
        RecordingGateway gw = new RecordingGateway();
        gw.enqueue(200, "{\"output\":{\"task_status\":\"RUNNING\"}}");
        ObjectMapper mapper = spy(new ObjectMapper());
        QwenVideoProvider provider = new QwenVideoProvider(okResolver(), mapper, gw);

        VideoProvider.ProbeResult result = provider.poll("task-x");

        assertNotNull(result);
        assertEquals(VideoProvider.RemoteStatus.PROCESSING, result.status());
    }
}
