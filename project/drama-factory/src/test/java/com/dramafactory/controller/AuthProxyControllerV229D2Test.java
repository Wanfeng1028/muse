// 文件：src/test/java/com/dramafactory/controller/AuthProxyControllerV229D2Test.java

package com.dramafactory.controller;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.ResponseEntity;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

// 本测试针对 AuthProxyController 剩余可达分支（2026-10-17 JaCoCo）：
//   line 99  DELETE 方法触发 CSRF 检查
//   line 100 非 /api/auth/ 写请求跳过 CSRF（startsWith false 分支）
//   line 151 空 Authorization 头 → 回退 df_at cookie
//   line 213 logout 上游非 2xx → 透传
//   line 228 isTokenResponse 非 2xx → false
//   line 262 空 Origin → 回退 Referer
//   line 271 Origin 解析出空 host → 拒绝
//
// 不可达分支（不覆盖）：
//   line 297 buildCookie value == null
//   line 309 textOrNull node == null
//   line 311 textOrNull v == null
//   line 100 path != null 为 false
/**
 * D2-3 补齐 AuthProxyController 剩余可达分支。
 *
 * <p>诚实声明（不可达分支，不硬凑）：</p>
 * <ul>
 *   <li>line 297 {@code buildCookie} 的 {@code value == null}：所有调用点都传非 null（logout 传 ""），不可达。</li>
 *   <li>line 309 {@code textOrNull} 的 {@code node == null}：{@code objectMapper.readTree} 成功时永不返回 null。</li>
 *   <li>line 311 {@code textOrNull} 的 {@code v == null}：{@code hasNonNull(field)} 为 true 时 {@code get(field)} 永不为 null。</li>
 *   <li>line 271 {@code isCsrfAllowed} 的 {@code sourceHost.isEmpty()}：实测 {@code new URI("http:///path").getHost()}
 *       与 {@code new URI("http://:80/path").getHost()} 均返回 null 而非 ""——JDK 的 {@code URI.getHost()}
 *       在 host 为空时返回 null，不可能返回空字符串。故该分支不可达。</li>
 *   <li>line 100 的 {@code path != null} 为 false：{@code extractPath} 返回 {@code getRequestURI()} 永不为 null。</li>
 * </ul>
 */
class AuthProxyControllerV229D2Test {

    private static final String UPSTREAM = "http://auth-test:8082";

    private AuthProxyController newController(HttpClient client) {
        return new AuthProxyController(UPSTREAM, client);
    }

    private HttpResponse<byte[]> mockUpstream(int status, String body) {
        @SuppressWarnings("unchecked")
        HttpResponse<byte[]> resp = mock(HttpResponse.class);
        when(resp.statusCode()).thenReturn(status);
        when(resp.body()).thenReturn(body.getBytes(StandardCharsets.UTF_8));
        when(resp.headers()).thenReturn(HttpHeaders.of(Map.of(), (k, v) -> true));
        return resp;
    }

    private ServletInputStream emptyStream() {
        ByteArrayInputStream delegate = new ByteArrayInputStream(new byte[0]);
        return new ServletInputStream() {
            @Override public boolean isFinished() { return false; }
            @Override public boolean isReady() { return true; }
            @Override public void setReadListener(ReadListener readListener) { }
            @Override public int read() { return delegate.read(); }
        };
    }

    @SuppressWarnings("unchecked")
    private void stubUpstream(HttpClient client, HttpResponse<byte[]> resp) throws Exception {
        when(client.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class))).thenReturn(resp);
    }

    @Test
    @DisplayName("用例1：DELETE 方法触发 CSRF 检查，跨站 Origin 返回 403 FORBIDDEN")
    void deleteMethodTriggersCsrfCheck() throws Exception {
        HttpClient client = mock(HttpClient.class);
        AuthProxyController controller = newController(client);

        jakarta.servlet.http.HttpServletRequest request = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(request.getMethod()).thenReturn("DELETE");
        when(request.getRequestURI()).thenReturn("/api/auth/me");
        when(request.getContextPath()).thenReturn("");
        when(request.getQueryString()).thenReturn(null);
        when(request.getHeader("Origin")).thenReturn("http://evil.com");
        when(request.getHeader("Host")).thenReturn("localhost");
        when(request.getInputStream()).thenReturn(emptyStream());

        ResponseEntity<byte[]> response = controller.proxy(request);

        assertEquals(403, response.getStatusCode().value());
        String body = new String(response.getBody(), StandardCharsets.UTF_8);
        assertTrue(body.contains("FORBIDDEN"), "响应体应包含 FORBIDDEN，实际：" + body);
        verify(client, never()).send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class));
    }

    @Test
    @DisplayName("用例2：非 /api/auth/ 的写请求跳过 CSRF，正常透传上游 200")
    void nonAuthWritePathSkipsCsrf() throws Exception {
        HttpClient client = mock(HttpClient.class);
        AuthProxyController controller = newController(client);
        stubUpstream(client, mockUpstream(200, "proxied"));

        jakarta.servlet.http.HttpServletRequest request = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/projects");
        when(request.getContextPath()).thenReturn("");
        when(request.getQueryString()).thenReturn(null);
        when(request.getHeader("Origin")).thenReturn("http://evil.com");
        when(request.getHeader("Host")).thenReturn("localhost");
        when(request.getInputStream()).thenReturn(emptyStream());

        ResponseEntity<byte[]> response = controller.proxy(request);

        assertEquals(200, response.getStatusCode().value());
        assertEquals("proxied", new String(response.getBody(), StandardCharsets.UTF_8));
    }

    @Test
    @DisplayName("用例3：空字符串 Authorization 头 → 回退 df_at cookie，上游收到 Bearer tok123")
    void emptyAuthorizationFallsBackToCookie() throws Exception {
        HttpClient client = mock(HttpClient.class);
        AuthProxyController controller = newController(client);
        stubUpstream(client, mockUpstream(200, "ok"));

        jakarta.servlet.http.HttpServletRequest request = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(request.getMethod()).thenReturn("GET");
        when(request.getRequestURI()).thenReturn("/api/auth/me");
        when(request.getContextPath()).thenReturn("");
        when(request.getQueryString()).thenReturn(null);
        when(request.getHeader("Authorization")).thenReturn("");
        when(request.getCookies()).thenReturn(new Cookie[]{new Cookie("df_at", "tok123")});
        when(request.getInputStream()).thenReturn(emptyStream());

        ResponseEntity<byte[]> response = controller.proxy(request);

        assertEquals(200, response.getStatusCode().value());

        ArgumentCaptor<HttpRequest> captor = ArgumentCaptor.forClass(HttpRequest.class);
        verify(client).send(captor.capture(), any(HttpResponse.BodyHandler.class));
        HttpRequest sent = captor.getValue();
        String auth = sent.headers().firstValue("Authorization").orElse("");
        assertEquals("Bearer tok123", auth);
    }

    @Test
    @DisplayName("用例4：logout 上游返回 302 → 直接透传，不清 cookie")
    void logoutUpstream302PassThrough() throws Exception {
        HttpClient client = mock(HttpClient.class);
        AuthProxyController controller = newController(client);
        stubUpstream(client, mockUpstream(302, "upstream-body"));

        jakarta.servlet.http.HttpServletRequest request = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/logout");
        when(request.getContextPath()).thenReturn("");
        when(request.getQueryString()).thenReturn(null);
        when(request.getHeader("Origin")).thenReturn("http://localhost");
        when(request.getHeader("Host")).thenReturn("localhost");
        when(request.getInputStream()).thenReturn(emptyStream());

        ResponseEntity<byte[]> response = controller.proxy(request);

        assertEquals(302, response.getStatusCode().value());
        assertEquals("upstream-body", new String(response.getBody(), StandardCharsets.UTF_8));
        assertTrue(response.getHeaders().get("Set-Cookie") == null
                || response.getHeaders().get("Set-Cookie").isEmpty());
    }

    @Test
    @DisplayName("用例5：login 上游返回 500 → isTokenResponse false，透传且不设 Set-Cookie")
    void loginUpstream500PassThrough() throws Exception {
        HttpClient client = mock(HttpClient.class);
        AuthProxyController controller = newController(client);
        stubUpstream(client, mockUpstream(500, "{\"code\":\"X\"}"));

        jakarta.servlet.http.HttpServletRequest request = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("");
        when(request.getQueryString()).thenReturn(null);
        when(request.getHeader("Origin")).thenReturn("http://localhost");
        when(request.getHeader("Host")).thenReturn("localhost");
        when(request.getInputStream()).thenReturn(emptyStream());

        ResponseEntity<byte[]> response = controller.proxy(request);

        assertEquals(500, response.getStatusCode().value());
        assertEquals("{\"code\":\"X\"}", new String(response.getBody(), StandardCharsets.UTF_8));
        assertTrue(response.getHeaders().get("Set-Cookie") == null
                || response.getHeaders().get("Set-Cookie").isEmpty());
    }

    @Test
    @DisplayName("用例6：空 Origin → 回退 Referer 跨站 → 403")
    void emptyOriginFallsBackToReferer() throws Exception {
        HttpClient client = mock(HttpClient.class);
        AuthProxyController controller = newController(client);

        jakarta.servlet.http.HttpServletRequest request = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("");
        when(request.getQueryString()).thenReturn(null);
        when(request.getHeader("Origin")).thenReturn("");
        when(request.getHeader("Referer")).thenReturn("http://evil.com/page");
        when(request.getHeader("Host")).thenReturn("localhost");
        when(request.getInputStream()).thenReturn(emptyStream());

        ResponseEntity<byte[]> response = controller.proxy(request);

        assertEquals(403, response.getStatusCode().value());
        verify(client, never()).send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class));
    }

}