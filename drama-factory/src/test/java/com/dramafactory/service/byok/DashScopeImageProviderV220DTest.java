package com.dramafactory.service.byok;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.byok.ImageProvider.PollResult;
import com.dramafactory.service.byok.ImageProvider.RemoteStatus;
import com.dramafactory.service.byok.ImageProvider.SubmitResult;
import com.dramafactory.service.video.VideoProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * v2.20 第 D 批：DashScopeImageProvider 剩余未覆盖分支补充测试。
 */
class DashScopeImageProviderV220DTest {

    private static final String AUTH_HEADER = "Bearer test-key-123";

    private DashScopeImageProvider provider;
    private RecordingGateway gateway;

    @BeforeEach
    void setUp() {
        @SuppressWarnings("unchecked")
        CredentialResolver resolver = mock(CredentialResolver.class);
        when(resolver.dashscopeByokAuth(any(), any()))
                .thenReturn(Map.entry("Authorization", AUTH_HEADER));
        gateway = new RecordingGateway();
        provider = new DashScopeImageProvider(resolver, new ObjectMapper(), gateway);
    }

    // ---------------- submit：body() == null 走空字符串臂（源码 111 行） ----------------
    // 网关返回 2xx + null body -> responseBody 空串。注意 readTree("") 返回
    // MissingNode 不抛异常，因此走的是 task_id 缺失臂。

    @Test
    void submit_nullGatewayBody_parseFailure() {
        gateway.status = 200;
        gateway.body = null;
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("k", "https://x.test", "wanx", "p", "1024*1024"));
        assertEquals("DashScope 图片提交失败, 未返回 task_id, 响应: ", ex.getMessage());
    }

    // ---------------- submit：code < 200 下界臂（源码 113 行） ----------------

    @Test
    void submit_httpBelow200_throwsWithCode() {
        gateway.status = 199;
        gateway.body = "early";
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("k", "https://x.test", "wanx", "p", "1024*1024"));
        assertTrue(ex.getMessage().startsWith("DashScope 图片提交失败, HTTP 199, 响应: "));
    }

    // ---------------- poll：body() == null 走空字符串臂（源码 160 行） ----------------

    @Test
    void poll_nullGatewayBody_returnsQueued() {
        gateway.status = 200;
        gateway.body = null;
        // readTree("") 返回 MissingNode 不抛异常；task_status 取不到 -> switch default -> QUEUED
        PollResult result = provider.poll("k", "https://x.test", "task-1");
        assertEquals(RemoteStatus.QUEUED, result.status());
    }

    // ---------------- poll：code < 200 下界臂（源码 162 行） ----------------

    @Test
    void poll_httpBelow200_throwsWithCode() {
        gateway.status = 199;
        gateway.body = "early";
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("k", "https://x.test", "task-1"));
        assertTrue(ex.getMessage().startsWith("DashScope 图片轮询失败, HTTP 199, 响应: "));
    }

    // ---------------- poll：SUCCEEDED 且 results 非数组（isArray false）臂（源码 177 行） ----------------

    @Test
    void poll_succeededResultsNotArray_throws() {
        gateway.status = 200;
        gateway.body = "{\"output\":{\"task_status\":\"SUCCEEDED\",\"results\":{}}}";
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("k", "https://x.test", "task-1"));
        assertTrue(ex.getMessage().startsWith("DashScope 图片轮询失败, 成功响应缺少 results, 响应: "));
    }

    // ---------------- poll：SUCCEEDED 且 results[0].url 为空白文本臂（源码 181 行） ----------------

    @Test
    void poll_succeededResultUrlBlank_throws() {
        gateway.status = 200;
        gateway.body = "{\"output\":{\"task_status\":\"SUCCEEDED\",\"results\":[{\"url\":\"  \"}]}}";
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.poll("k", "https://x.test", "task-1"));
        assertTrue(ex.getMessage().startsWith("DashScope 图片轮询失败, 成功响应缺少图片 URL, 响应: "));
    }

    // ---------------- poll：FAILED 且 message 非 missing/null 走 asText 臂（源码 188 行） ----------------

    @Test
    void poll_failedWithMessage_returnsMessage() {
        gateway.status = 200;
        gateway.body = "{\"output\":{\"task_status\":\"FAILED\",\"message\":\"boom\"}}";
        PollResult result = provider.poll("k", "https://x.test", "task-1");
        assertEquals(RemoteStatus.FAILED, result.status());
        assertNull(result.imageUrl());
        assertEquals("boom", result.errorMessage());
        assertEquals(100, result.progress());
    }

    // ---------------- poll：SUCCEEDED 有效 url 走成功臂（源码 184 行） ----------------

    @Test
    void poll_succeededValidUrl_returnsUrl() {
        gateway.status = 200;
        gateway.body = "{\"output\":{\"task_status\":\"SUCCEEDED\",\"results\":[{\"url\":\"http://x/i.png\"}]}}";
        PollResult result = provider.poll("k", "https://x.test", "task-1");
        assertEquals(RemoteStatus.SUCCEEDED, result.status());
        assertEquals("http://x/i.png", result.imageUrl());
        assertNull(result.errorMessage());
        assertEquals(100, result.progress());
    }

    // ---------------- probe：code == 401 走 AUTH_FAILED 臂（源码 229 行） ----------------

    @Test
    void probe_401_returnsAuthFailed() {
        gateway.status = 401;
        gateway.body = "unauthorized";
        ImageProvider.ConnectivityResult result = provider.probe("k", "https://x.test");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
        assertEquals("密钥无效或鉴权失败", result.detail());
    }

    // ---------------- probe：code == 403 走 AUTH_FAILED 臂（源码 229 行） ----------------

    @Test
    void probe_403_returnsAuthFailed() {
        gateway.status = 403;
        gateway.body = "forbidden";
        ImageProvider.ConnectivityResult result = provider.probe("k", "https://x.test");
        assertEquals(VideoProvider.ConnectivityStatus.AUTH_FAILED, result.status());
        assertEquals("密钥无效或鉴权失败", result.detail());
    }

    // ---------------- probe：code >= 300 且非 404/401/403/429 走 PROVIDER_ERROR 臂（源码 238 行） ----------------

    @Test
    void probe_unexpected3xx_returnsProviderError() {
        gateway.status = 302;
        gateway.body = "redirect";
        ImageProvider.ConnectivityResult result = provider.probe("k", "https://x.test");
        assertEquals(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, result.status());
        assertEquals("服务方返回异常状态码：302", result.detail());
    }

    // ---------------- truncate：value 为 null 走空字符串臂（源码 242 行） ----------------
    // 通过 HTTP 非 2xx + null body 间接进入 truncate(responseBody, 300)，responseBody 已被
    // submit/poll 提前转换为 ""，故此处构造超长响应体覆盖 length>max 截断臂（源码 248 行）。

    @Test
    void submit_longErrorBody_truncatedTo300() {
        gateway.status = 500;
        gateway.body = "x".repeat(400);
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("k", "https://x.test", "wanx", "p", "1024*1024"));
        String msg = ex.getMessage();
        assertTrue(msg.startsWith("DashScope 图片提交失败, HTTP 500, 响应: "));
        String suffix = msg.substring("DashScope 图片提交失败, HTTP 500, 响应: ".length());
        assertEquals(300, suffix.length());
    }

    // ---------------- submit：size 合法但 modelId 为 null 走 Map.of 抛 NPE 臂（源码 90-92 行） ----------------

    @Test
    void submit_nullModelId_bodyBuildException() {
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> provider.submit("k", "https://x.test", null, "p", "1024*1024"));
        assertEquals("DashScope 图片提交失败, 请求体构建异常", ex.getMessage());
    }

    // ==================== RecordingGateway ====================

    static final class RecordingGateway implements ByokHttpGateway {

        int status = 200;
        String body = "{}";

        @Override
        public GatewayResponse exchange(HttpRequest request) {
            return new GatewayResponse(status, body);
        }
    }
}
