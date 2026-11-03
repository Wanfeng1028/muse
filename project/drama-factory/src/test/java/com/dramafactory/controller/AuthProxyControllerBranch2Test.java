package com.dramafactory.controller;

/*
 * 诚实跳过清单（经分析确认不可达，不硬编测试）：
 *
 * - AuthProxyController.java:240 buildCookie 的 `value == null` 臂：三个调用点（174 行
 *   `accessToken != null` 守卫、178 行 `refreshToken != null` 守卫、192/193 行传 "" 常量）
 *   都不可能传 null。防御性不可达。
 * - AuthProxyController.java:249 `node == null` 臂：唯一调用方是 objectMapper.readTree(byte[])，
 *   空输入返回 MissingNode 而非 null（本仓库 Jackson 已实测）。防御性不可达。
 * - AuthProxyController.java:251 `v == null` 臂：JsonNode.asText() 按 Jackson 契约永不返回
 *   null（无值字段返回 ""）。防御性不可达。
 * 但 249 的 `!node.hasNonNull(field)` 臂、251 的 `v.isEmpty()` 臂已分别写出测试覆盖。
 */

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.DelegatingServletInputStream;

import java.io.ByteArrayInputStream;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Vector;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AuthProxyControllerBranch2Test {

    private HttpClient httpClient;

    @BeforeEach
    void setUp() {
        httpClient = mock(HttpClient.class);
    }

    private HttpServletRequestStub request(String method, String uri) {
        return new HttpServletRequestStub(method, uri);
    }

    @SuppressWarnings("unchecked")
    private HttpResponse<byte[]> upstream(int status, byte[] body) {
        return upstream(status, body, java.net.http.HttpHeaders.of(Map.of(), (k, v) -> true));
    }

    private HttpResponse<byte[]> upstream(int status, byte[] body, java.net.http.HttpHeaders headers) {
        HttpResponse<byte[]> resp = mock(HttpResponse.class);
        when(resp.statusCode()).thenReturn(status);
        when(resp.body()).thenReturn(body);
        when(resp.headers()).thenReturn(headers);
        return resp;
    }

    private void stubSend(HttpResponse<byte[]> resp) throws Exception {
        doReturn(resp).when(httpClient).send(any(), any());
    }

    private HttpRequest captureRequest() throws Exception {
        ArgumentCaptor<HttpRequest> captor = ArgumentCaptor.forClass(HttpRequest.class);
        org.mockito.Mockito.verify(httpClient).send(captor.capture(), any());
        return captor.getValue();
    }

    // ---- 112：headerNames 含 null 被跳过 ----
    @Test
    void proxy_headerNamesContainsNull_expectsSkipAnd200() throws Exception {
        HttpServletRequestStub req = request("GET", "/api/auth/me");
        req.headerNames = enumeration("X-Custom", null);
        req.headers.put("X-Custom", List.of("v1"));
        stubSend(upstream(200, "ok".getBytes(StandardCharsets.UTF_8)));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        ResponseEntity<byte[]> resp = controller.proxy(req.proxy());

        // 覆盖第 112 行 `if (name == null) continue;` 的 true 臂
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).isEqualTo("ok".getBytes(StandardCharsets.UTF_8));
    }

    // ---- 127：Authorization 为空串，回退到 df_at cookie ----
    @Test
    void proxy_emptyAuthorizationHeader_expectsBearerFromCookie() throws Exception {
        HttpServletRequestStub req = request("GET", "/api/auth/me");
        req.headerNames = enumeration("Authorization");
        req.headers.put("Authorization", List.of(""));
        req.cookies = new Cookie[]{new Cookie("df_at", "tok123")};
        stubSend(upstream(200, new byte[0]));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        controller.proxy(req.proxy());

        // 覆盖第 127 行 `authHeader.isEmpty()` 的 true 臂 → 走 cookie 回退
        HttpRequest captured = captureRequest();
        assertThat(captured.headers().firstValue("Authorization")).contains("Bearer tok123");
    }

    // ---- 129：df_at cookie 为空串，不加 Authorization ----
    @Test
    void proxy_emptyAtCookie_expectsNoAuthorizationHeader() throws Exception {
        HttpServletRequestStub req = request("GET", "/api/auth/me");
        req.headerNames = enumeration();
        req.cookies = new Cookie[]{new Cookie("df_at", "")};
        stubSend(upstream(200, new byte[0]));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        controller.proxy(req.proxy());

        // 覆盖第 129 行 `at != null && !at.isEmpty()` 的 false 臂
        HttpRequest captured = captureRequest();
        assertThat(captured.headers().firstValue("Authorization")).isEmpty();
    }

    // ---- 152：upstream body 为 null ----
    @Test
    void proxy_upstreamBodyNull_expectsEmptyBody() throws Exception {
        HttpServletRequestStub req = request("GET", "/api/auth/me");
        req.headerNames = enumeration();
        stubSend(upstream(200, null));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        ResponseEntity<byte[]> resp = controller.proxy(req.proxy());

        // 覆盖第 152 行 `upstream.body() == null` 的 true 臂
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).isNotNull();
        assertThat(resp.getBody().length).isEqualTo(0);
    }

    // ---- 155：上游响应头 map 含 null key ----
    @Test
    void proxy_upstreamHeadersNullKey_expectsSkipAnd200() throws Exception {
        HttpServletRequestStub req = request("GET", "/api/auth/me");
        req.headerNames = enumeration();

        Map<String, List<String>> raw = new HashMap<>();
        raw.put(null, List.of("x"));
        raw.put("X-Good", List.of("v"));
        // 注意：java.net.http.HttpHeaders.of() 自身会对 null key 抛 NPE，
        // 这里用 mock 才能把"上游响应头含 null key"的场景送进被测代码。
        java.net.http.HttpHeaders headers = mock(java.net.http.HttpHeaders.class);
        when(headers.map()).thenReturn(raw);
        stubSend(upstream(200, "hi".getBytes(StandardCharsets.UTF_8), headers));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        ResponseEntity<byte[]> resp = controller.proxy(req.proxy());

        // 覆盖第 155 行 `if (k == null) return;` 的 true 臂
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    // ---- 189：logout 上游非 2xx，原样透传 ----
    @Test
    void proxy_logoutUpstream500_expectsPassThrough() throws Exception {
        HttpServletRequestStub req = request("POST", "/api/auth/logout");
        req.headerNames = enumeration();
        req.body = "".getBytes(StandardCharsets.UTF_8);
        stubSend(upstream(500, "oops".getBytes(StandardCharsets.UTF_8)));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        ResponseEntity<byte[]> resp = controller.proxy(req.proxy());

        // 覆盖第 189 行 `status >= 200 && status < 300` 的 false 臂
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(resp.getBody()).isEqualTo("oops".getBytes(StandardCharsets.UTF_8));
    }

    // ---- 204：login 上游 302，不进 token 剥离 ----
    @Test
    void proxy_loginUpstream302_expectsPassThrough() throws Exception {
        HttpServletRequestStub req = request("POST", "/api/auth/login");
        req.headerNames = enumeration();
        req.body = "{}".getBytes(StandardCharsets.UTF_8);
        stubSend(upstream(302, "redirect".getBytes(StandardCharsets.UTF_8)));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        ResponseEntity<byte[]> resp = controller.proxy(req.proxy());

        // 覆盖第 204 行 `status >= 300` 的 true 臂（isTokenResponse 返回 false）
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.FOUND);
        assertThat(resp.getBody()).isEqualTo("redirect".getBytes(StandardCharsets.UTF_8));
    }

    // ---- 207：oauth 路径 startsWith 真但 endsWith /callback 假 ----
    @Test
    void proxy_oauthNonCallbackPath_expectsPassThrough() throws Exception {
        HttpServletRequestStub req = request("POST", "/api/auth/oauth/github/authorize");
        req.headerNames = enumeration();
        req.body = "{}".getBytes(StandardCharsets.UTF_8);
        stubSend(upstream(200, "{\"a\":1}".getBytes(StandardCharsets.UTF_8)));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        ResponseEntity<byte[]> resp = controller.proxy(req.proxy());

        // 覆盖第 207 行 `path.endsWith("/callback")` 的 false 臂
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).isEqualTo("{\"a\":1}".getBytes(StandardCharsets.UTF_8));
    }

    // ---- 221 true 臂：contextPath 被剥离 ----
    @Test
    void proxy_contextPathMatches_expectsStrippedUpstreamUri() throws Exception {
        HttpServletRequestStub req = request("GET", "/app/api/auth/me");
        req.contextPath = "/app";
        req.headerNames = enumeration();
        stubSend(upstream(200, new byte[0]));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        controller.proxy(req.proxy());

        // 覆盖第 221 行 `uri.startsWith(ctx)` 的 true 臂
        HttpRequest captured = captureRequest();
        assertThat(captured.uri().toString()).isEqualTo("http://x/api/auth/me");
    }

    // ---- 221 false 臂：contextPath 不匹配，原样拼接 ----
    @Test
    void proxy_contextPathMismatch_expectsUriUnchanged() throws Exception {
        HttpServletRequestStub req = request("GET", "/api/auth/me");
        req.contextPath = "/other";
        req.headerNames = enumeration();
        stubSend(upstream(200, new byte[0]));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        controller.proxy(req.proxy());

        // 覆盖第 221 行 `uri.startsWith(ctx)` 的 false 臂
        HttpRequest captured = captureRequest();
        assertThat(captured.uri().toString()).isEqualTo("http://x/api/auth/me");
    }

    // ---- 249 `!node.hasNonNull(field)` 臂：login 空对象，无 Set-Cookie ----
    @Test
    void proxy_loginEmptyObject_expectsOkTrueNoSetCookie() throws Exception {
        HttpServletRequestStub req = request("POST", "/api/auth/login");
        req.headerNames = enumeration();
        req.body = "{}".getBytes(StandardCharsets.UTF_8);
        stubSend(upstream(200, "{}".getBytes(StandardCharsets.UTF_8)));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        ResponseEntity<byte[]> resp = controller.proxy(req.proxy());

        // 覆盖第 249 行 `!node.hasNonNull(field)` 的 true 臂（accessToken/refreshToken 均缺失）
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).isEqualTo("{\"ok\":true}".getBytes(StandardCharsets.UTF_8));
        assertThat(resp.getHeaders().get(HttpHeaders.SET_COOKIE)).isNull();
    }

    // ---- 251 `v.isEmpty()` 臂：accessToken 空串，只有 df_rt 写 cookie ----
    @Test
    void proxy_loginEmptyAccessToken_expectsOnlyRefreshCookie() throws Exception {
        HttpServletRequestStub req = request("POST", "/api/auth/login");
        req.headerNames = enumeration();
        req.body = "{}".getBytes(StandardCharsets.UTF_8);
        byte[] body = "{\"accessToken\":\"\",\"refreshToken\":\"rt\",\"expiresIn\":3600}"
                .getBytes(StandardCharsets.UTF_8);
        stubSend(upstream(200, body));

        AuthProxyController controller = new AuthProxyController("http://x", httpClient);
        ResponseEntity<byte[]> resp = controller.proxy(req.proxy());

        // 覆盖第 251 行 `v.isEmpty()` 的 true 臂：accessToken → null（不写 df_at），refreshToken 正常
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        List<String> setCookies = resp.getHeaders().get(HttpHeaders.SET_COOKIE);
        assertThat(setCookies).isNotNull();
        assertThat(setCookies).anyMatch(c -> c.startsWith("df_rt="));
        assertThat(setCookies).noneMatch(c -> c.startsWith("df_at="));
    }

    // ---- 262：authServiceUrl 为 null，构造不抛错且代理可用 ----
    @Test
    void constructor_nullAuthServiceUrl_expectsIaeOnProxy() throws Exception {
        HttpServletRequestStub req = request("GET", "/api/auth/me");
        req.headerNames = enumeration();
        stubSend(upstream(200, "ok".getBytes(StandardCharsets.UTF_8)));

        // 覆盖第 262 行 `if (s == null) return "";` 的 true 臂：构造本身不抛错；
        // 但 authServiceUrl 为空时代理拼出的相对 URI 会被 JDK HttpRequest 拒绝，
        // 此处如实断言该退化行为（生产环境 @Value 恒有默认值，走不到这里）。
        AuthProxyController controller = new AuthProxyController(null, httpClient);
        assertThat(org.junit.jupiter.api.Assertions.assertThrows(IllegalArgumentException.class,
                () -> controller.proxy(req.proxy())).getMessage()).contains("scheme");
    }

    private static <T> Enumeration<T> enumeration(T... items) {
        Vector<T> v = new Vector<>();
        if (items != null) {
            Collections.addAll(v, items);
        }
        return v.elements();
    }

    /**
     * 简易 HttpServletRequest 桩，避免逐处 mock 造成样板膨胀；仅覆盖被测代码用到的访问器。
     */
    private static final class HttpServletRequestStub {
        private final String method;
        private final String uri;
        String contextPath = "";
        String queryString = null;
        Enumeration<String> headerNames = new Vector<String>().elements();
        final Map<String, List<String>> headers = new HashMap<>();
        Cookie[] cookies = null;
        byte[] body = new byte[0];

        HttpServletRequestStub(String method, String uri) {
            this.method = method;
            this.uri = uri;
        }

        jakarta.servlet.http.HttpServletRequest proxy() {
            jakarta.servlet.http.HttpServletRequest req = mock(jakarta.servlet.http.HttpServletRequest.class);
            when(req.getMethod()).thenReturn(method);
            when(req.getRequestURI()).thenReturn(uri);
            when(req.getContextPath()).thenReturn(contextPath);
            when(req.getQueryString()).thenReturn(queryString);
            when(req.getHeaderNames()).thenReturn(headerNames);
            for (Map.Entry<String, List<String>> e : headers.entrySet()) {
                when(req.getHeaders(e.getKey())).thenReturn(enumeration(e.getValue().toArray(new String[0])));
            }
            when(req.getHeaders(any())).thenReturn(new Vector<String>().elements());
            when(req.getCookies()).thenReturn(cookies);
            try {
                when(req.getInputStream()).thenReturn(
                        new DelegatingServletInputStream(new ByteArrayInputStream(body)));
            } catch (Exception ex) {
                throw new IllegalStateException(ex);
            }
            return req;
        }
    }

    @SuppressWarnings("unused")
    private static ObjectMapper unusedMapperRef() {
        return new ObjectMapper();
    }
}
