package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.video.VideoProvider.ConnectivityResult;
import com.dramafactory.service.video.VideoProvider.ConnectivityStatus;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.net.http.HttpRequest;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * QwenVideoProvider 分支收尾测试（第三批）。
 *
 * 诚实跳过清单：
 * 1. 293 行 truncate 的 {@code text == null} 臂：防御性不可达。全部 7 处调用方传入的 body
 *    都经过 {@code response.body() == null ? "" : response.body()} 归一化，永远不为 null，
 *    无法在真实执行路径上触达该分支，故跳过。
 */
class QwenVideoProviderBranch3Test {

    /** 内存桩网关：按队列顺序回放预设响应，参考 QwenVideoProviderBranch2Test.StubGateway。 */
    static final class StubGateway implements VideoHttpGateway {
        final Deque<GatewayResponse> queue = new ArrayDeque<>();

        void enqueue(GatewayResponse response) {
            queue.add(response);
        }

        @Override
        public GatewayResponse exchange(HttpRequest request) {
            GatewayResponse resp = queue.poll();
            if (resp == null) {
                throw new IllegalStateException("StubGateway 队列已空");
            }
            return resp;
        }
    }

    @TempDir
    Path tempDir;

    private CredentialResolver credentialResolver;
    private ObjectMapper objectMapper;
    private StubGateway gateway;
    private QwenVideoProvider provider;

    @BeforeEach
    void setUp() {
        credentialResolver = mock(CredentialResolver.class);
        objectMapper = new ObjectMapper();
        gateway = new StubGateway();
        provider = new QwenVideoProvider(credentialResolver, objectMapper, gateway);
    }

    /**
     * 覆盖 probeConnectivity 第 110 行 if (code >= 200 && code < 300) 的真分支臂：
     * 网关返回 200 → ConnectivityStatus.OK。
     */
    @Test
    void probeConnectivity_2xx_expectsOk() {
        when(credentialResolver.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer k"));
        gateway.enqueue(new VideoHttpGateway.GatewayResponse(200, "{\"ok\":true}"));

        ConnectivityResult result = provider.probeConnectivity();

        assertEquals(ConnectivityStatus.OK, result.status());
    }

    /**
     * 覆盖 probeConnectivity 第 110 行 if (code >= 200 && code < 300) 的假分支臂：
     * 网关返回 500 → 落到第 113 行 PROVIDER_ERROR。
     */
    @Test
    void probeConnectivity_500_expectsProviderError() {
        when(credentialResolver.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer k"));
        gateway.enqueue(new VideoHttpGateway.GatewayResponse(500, "boom"));

        ConnectivityResult result = provider.probeConnectivity();

        assertEquals(ConnectivityStatus.PROVIDER_ERROR, result.status());
    }

    /**
     * 覆盖 probeConnectivity 第 89 行 if (auth == null) 的真分支臂：
     * 凭据解析返回 null → AUTH_FAILED。
     */
    @Test
    void probeConnectivity_nullAuth_expectsAuthFailed() {
        when(credentialResolver.dashscopeAuth(anyString())).thenReturn(null);

        ConnectivityResult result = provider.probeConnectivity();

        assertEquals(ConnectivityStatus.AUTH_FAILED, result.status());
    }

    /**
     * 覆盖 submit 第 130 行 if (prompt == null || prompt.isBlank()) 的 null 臂：
     * videoPrompt 为 null 时走 description/景别/运镜拼接路径，最终提交成功。
     */
    @Test
    void submit_nullVideoPrompt_expectsBuiltFromFields() {
        when(credentialResolver.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer k"));
        gateway.enqueue(new VideoHttpGateway.GatewayResponse(200,
                "{\"output\":{\"task_id\":\"task-null\"}}"));

        Shot shot = new Shot();
        shot.setVideoPrompt(null);
        shot.setDescription("雨夜街头");
        shot.setShotSize(com.dramafactory.model.ShotSize.ZHONG_JING);
        shot.setCameraMove(com.dramafactory.model.CameraMove.TUI);

        String taskId = provider.submit(shot, 5);

        assertEquals("task-null", taskId);
    }

    /**
     * 覆盖 submit 第 130 行 if (prompt == null || prompt.isBlank()) 的 blank 臂：
     * videoPrompt 为 "" 时同样走拼接路径，提交成功。
     */
    @Test
    void submit_blankVideoPrompt_expectsBuiltFromFields() {
        when(credentialResolver.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer k"));
        gateway.enqueue(new VideoHttpGateway.GatewayResponse(200,
                "{\"output\":{\"task_id\":\"task-blank\"}}"));

        Shot shot = new Shot();
        shot.setVideoPrompt("   ");
        shot.setDescription("黄昏天台");

        String taskId = provider.submit(shot, 5);

        assertEquals("task-blank", taskId);
    }

    /**
     * 覆盖 submit 第 192 行 response.body() == null ? "" : ... 的 null 臂：
     * 网关返回 (200, null)，body 归一化为 ""，readTree("") 失败 → RuntimeException。
     */
    @Test
    void submit_nullBody_expectsRuntimeException() {
        when(credentialResolver.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer k"));
        gateway.enqueue(new VideoHttpGateway.GatewayResponse(200, null));

        Shot shot = new Shot();
        shot.setVideoPrompt("一个镜头");

        assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
    }

    /**
     * 覆盖 submit 第 197 行 if (response.statusCode() < 200 || response.statusCode() >= 300)
     * 的真分支臂：网关返回 500，消息含 "通义万相提交任务失败, HTTP 500"。
     */
    @Test
    void submit_http500_expectsRuntimeExceptionWithHttpCode() {
        when(credentialResolver.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer k"));
        gateway.enqueue(new VideoHttpGateway.GatewayResponse(500, "{\"message\":\"server error\"}"));

        Shot shot = new Shot();
        shot.setVideoPrompt("一个镜头");

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.submit(shot, 5));
        assertTrue(ex.getMessage().contains("通义万相提交任务失败, HTTP 500"),
                "实际消息: " + ex.getMessage());
    }

    /**
     * 覆盖 submit 第 172 行 if (auth == null) 的真分支臂：
     * 凭据解析返回 null → IllegalStateException。
     */
    @Test
    void submit_nullAuth_expectsIllegalStateException() {
        when(credentialResolver.dashscopeAuth(anyString())).thenReturn(null);

        Shot shot = new Shot();
        shot.setVideoPrompt("一个镜头");

        assertThrows(IllegalStateException.class, () -> provider.submit(shot, 5));
    }

    /**
     * 覆盖 poll 第 250 行 response.body() == null ? "" : ... 的 null 臂：
     * 网关返回 (200, null) → body 按 "" 处理；readTree("") 得 MissingNode（本仓库 v2.13 已实测，
     * 不抛异常）→ task_status 取空 → default 臂返回 PROCESSING（不抛错）。
     */
    @Test
    void poll_nullBody_expectsProcessing() {
        when(credentialResolver.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer k"));
        gateway.enqueue(new VideoHttpGateway.GatewayResponse(200, null));

        VideoProvider.ProbeResult result = provider.poll("task-1");
        assertEquals(VideoProvider.RemoteStatus.PROCESSING, result.status());
    }

    /**
     * 覆盖 poll 第 253 行 if (response.statusCode() < 200 || response.statusCode() >= 300)
     * 的真分支臂：网关返回 500，消息含 "通义万相查询任务失败, HTTP 500"。
     */
    @Test
    void poll_http500_expectsRuntimeExceptionWithHttpCode() {
        when(credentialResolver.dashscopeAuth(anyString()))
                .thenReturn(Map.entry("Authorization", "Bearer k"));
        gateway.enqueue(new VideoHttpGateway.GatewayResponse(500, "{\"message\":\"server error\"}"));

        RuntimeException ex = assertThrows(RuntimeException.class, () -> provider.poll("task-1"));
        assertTrue(ex.getMessage().contains("通义万相查询任务失败, HTTP 500"),
                "实际消息: " + ex.getMessage());
    }

    /**
     * 覆盖 poll 第 232 行 if (auth == null) 的真分支臂：
     * 凭据解析返回 null → IllegalStateException。
     */
    @Test
    void poll_nullAuth_expectsIllegalStateException() {
        when(credentialResolver.dashscopeAuth(anyString())).thenReturn(null);

        assertThrows(IllegalStateException.class, () -> provider.poll("task-1"));
    }
}
