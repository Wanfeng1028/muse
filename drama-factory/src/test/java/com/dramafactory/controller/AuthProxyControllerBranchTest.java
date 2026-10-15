package com.dramafactory.controller;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.DelegatingServletInputStream;
import org.springframework.mock.web.MockHttpServletRequest;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * AuthProxyController 分支覆盖测试。
 */
class AuthProxyControllerBranchTest {

    private HttpServer server;
    private int port;
    private AuthProxyController controller;
    private final List<Recorded> recorded = new ArrayList<>();
    private final AtomicReference<ResponseSpec> nextResponse = new AtomicReference<>();

    static class Recorded {
        String method;
        String path;
        String query;
        String authorization;
        String body;
    }

    static class ResponseSpec {
        int status = 200;
        String body = "";
        String contentType = "application/json";
    }

    @BeforeEach
    void setUp() throws IOException {
        recorded.clear();
        nextResponse.set(new ResponseSpec());
        server = HttpServer.create(new InetSocketAddress("::1", 0), 0);
        server.createContext("/", this::handle);
        server.start();
        port = server.getAddress().getPort();
        controller = new AuthProxyController("http://[::1]:" + port, HttpClient.newHttpClient());
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    private void handle(HttpExchange exchange) throws IOException {
        Recorded r = new Recorded();
        r.method = exchange.getRequestMethod();
        r.path = exchange.getRequestURI().getPath();
        r.query = exchange.getRequestURI().getRawQuery();
        r.authorization = exchange.getRequestHeaders().getFirst("Authorization");
        byte[] reqBody = exchange.getRequestBody().readAllBytes();
        r.body = new String(reqBody, StandardCharsets.UTF_8);
        recorded.add(r);

        ResponseSpec spec = nextResponse.get();
        byte[] respBytes = spec.body == null ? new byte[0] : spec.body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", spec.contentType);
        exchange.sendResponseHeaders(spec.status, respBytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(respBytes);
        }
    }

    private Recorded last() {
        assertTrue(!recorded.isEmpty(), "上游未收到请求");
        return recorded.get(recorded.size() - 1);
    }

    // L76：queryString 为空串 → 走 !query.isEmpty() 的 false 分支，targetUrl 不带 "?"
    @Test
    void emptyQueryStringProducesNullUpstreamQuery() {
        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/api/auth/me");
        req.setQueryString("");
        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertNull(last().query, "空 queryString 不应拼接到上游 URL");
    }

    // L88：POST /api/auth/refresh 无 df_rt cookie → rt == null → 401
    @Test
    void refreshWithoutCookieReturns401() {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api/auth/refresh");
        req.setContent(new byte[0]);
        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.UNAUTHORIZED, resp.getStatusCode());
        assertTrue(recorded.isEmpty(), "无 refresh cookie 不应打到上游");
    }

    // L88：POST /api/auth/refresh 带空值 df_rt cookie → rt.isEmpty() → 401
    @Test
    void refreshWithEmptyCookieReturns401() {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api/auth/refresh");
        req.setContent(new byte[0]);
        req.setCookies(new Cookie("df_rt", ""));
        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.UNAUTHORIZED, resp.getStatusCode());
        assertTrue(recorded.isEmpty(), "空 refresh cookie 不应打到上游");
    }

    // L97/L98：refresh 正常路径，构造请求体发送给上游
    @Test
    void refreshWithCookieSendsRefreshTokenBody() {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api/auth/refresh");
        req.setContent(new byte[0]);
        req.setCookies(new Cookie("df_rt", "rt-token-xyz"));
        ResponseSpec spec = new ResponseSpec();
        spec.status = 200;
        spec.body = "{\"accessToken\":\"at-new\",\"refreshToken\":\"rt-new\"}";
        nextResponse.set(spec);

        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        Recorded r = last();
        assertEquals("POST", r.method);
        assertTrue(r.body.contains("rt-token-xyz"), "上游应收到包含 refreshToken 的请求体");
    }

    // L109/L112：mock getHeaderNames() 返回 null，不抛 NPE
    @Test
    void nullHeaderNamesDoesNotThrow() throws IOException {
        HttpServletRequest req = mock(HttpServletRequest.class);
        when(req.getMethod()).thenReturn("GET");
        when(req.getRequestURI()).thenReturn("/api/auth/me");
        when(req.getContextPath()).thenReturn("");
        when(req.getQueryString()).thenReturn(null);
        when(req.getHeaderNames()).thenReturn(null);
        ServletInputStream sis = new DelegatingServletInputStream(new ByteArrayInputStream(new byte[0]));
        when(req.getInputStream()).thenReturn(sis);

        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertNotNull(resp);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
    }

    // L127/L129：无 Authorization 头，df_at cookie 回退 → Bearer
    @Test
    void accessTokenCookieFallbackSetsAuthorizationHeader() {
        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/api/auth/me");
        req.setCookies(new Cookie("df_at", "abc123"));
        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("Bearer abc123", last().authorization);
    }

    // L189：POST /api/auth/logout 上游 200 → 清除 cookie
    @Test
    void logoutWith2xxClearsCookies() {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api/auth/logout");
        req.setContent(new byte[0]);
        ResponseSpec spec = new ResponseSpec();
        spec.status = 200;
        spec.body = "";
        nextResponse.set(spec);

        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        List<String> setCookies = resp.getHeaders().get("Set-Cookie");
        assertNotNull(setCookies);
        boolean hasAt = setCookies.stream().anyMatch(c -> c.contains("df_at"));
        boolean hasRt = setCookies.stream().anyMatch(c -> c.contains("df_rt"));
        assertTrue(hasAt, "应清除 df_at cookie");
        assertTrue(hasRt, "应清除 df_rt cookie");
    }

    // L204/L207：oauth callback + 2xx → isTokenResponse true，返回 200
    @Test
    void oauthCallbackTokenResponse() {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api/auth/oauth/github/callback");
        req.setContent("{\"code\":\"x\"}".getBytes(StandardCharsets.UTF_8));
        ResponseSpec spec = new ResponseSpec();
        spec.status = 200;
        spec.body = "{\"accessToken\":\"at1\",\"refreshToken\":\"rt1\",\"expiresIn\":120}";
        nextResponse.set(spec);

        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
    }

    // L213/L214/L215：PUT/PATCH/DELETE 无 body 也发送 body（hasRequestBody 分支）
    @Test
    void putMethodUsesBodyPublisher() {
        MockHttpServletRequest req = new MockHttpServletRequest("PUT", "/api/auth/me");
        req.setContent(new byte[0]);
        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("PUT", last().method);
    }

    @Test
    void patchMethodUsesBodyPublisher() {
        MockHttpServletRequest req = new MockHttpServletRequest("PATCH", "/api/auth/me");
        req.setContent(new byte[0]);
        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("PATCH", last().method);
    }

    @Test
    void deleteMethodUsesBodyPublisher() {
        MockHttpServletRequest req = new MockHttpServletRequest("DELETE", "/api/auth/me");
        req.setContent(new byte[0]);
        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("DELETE", last().method);
    }

    // L221/L222：contextPath 剥离
    @Test
    void contextPathIsStripped() {
        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/ctx/api/auth/me");
        req.setContextPath("/ctx");
        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("/api/auth/me", last().path);
    }

    // L240：readCookie 中 cookies == null 分支（空数组等价覆盖 cookie 不存在路径）
    @Test
    void readCookieWhenNoCookiesReturnsNull() {
        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/api/auth/me");
        req.setCookies(new Cookie[0]);
        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertNull(last().authorization, "无 cookie 时不应有 Authorization 头");
    }

    // L249/L251：login 响应中 refreshToken 为空字符串 → textOrNull 返回 null，不设 df_rt cookie
    @Test
    void loginWithEmptyRefreshTokenOmitsRefreshCookie() {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api/auth/login");
        req.setContent("{}".getBytes(StandardCharsets.UTF_8));
        ResponseSpec spec = new ResponseSpec();
        spec.status = 200;
        spec.body = "{\"accessToken\":\"at1\",\"refreshToken\":\"\"}";
        nextResponse.set(spec);

        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        List<String> setCookies = resp.getHeaders().get("Set-Cookie");
        assertNotNull(setCookies);
        boolean hasRt = setCookies.stream().anyMatch(c -> c.contains("df_rt"));
        assertTrue(!hasRt, "空 refreshToken 不应设置 df_rt cookie");
    }

    // L249：login 响应缺 refreshToken 字段 → textOrNull 返回 null
    @Test
    void loginWithoutRefreshTokenFieldOmitsRefreshCookie() {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api/auth/login");
        req.setContent("{}".getBytes(StandardCharsets.UTF_8));
        ResponseSpec spec = new ResponseSpec();
        spec.status = 200;
        spec.body = "{\"accessToken\":\"at1\"}";
        nextResponse.set(spec);

        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        List<String> setCookies = resp.getHeaders().get("Set-Cookie");
        assertNotNull(setCookies);
        boolean hasRt = setCookies.stream().anyMatch(c -> c.contains("df_rt"));
        assertTrue(!hasRt, "缺 refreshToken 字段不应设置 df_rt cookie");
    }

    // L262：构造器 trimTrailingSlash，上游 URL 带尾部斜杠仍能正确路由
    @Test
    void trailingSlashTrimmedFromUpstreamUrl() {
        AuthProxyController c2 = new AuthProxyController("http://[::1]:" + port + "/", HttpClient.newHttpClient());
        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/api/auth/me");
        ResponseEntity<byte[]> resp = c2.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertEquals("/api/auth/me", last().path);
    }

    // L152：上游响应 body 为 null（空 body）时使用空数组
    @Test
    void upstreamEmptyBodyHandled() {
        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/api/auth/me");
        ResponseSpec spec = new ResponseSpec();
        spec.status = 200;
        spec.body = "";
        nextResponse.set(spec);

        ResponseEntity<byte[]> resp = controller.proxy(req);
        assertEquals(HttpStatus.OK, resp.getStatusCode());
        assertNotNull(resp.getBody());
    }
}
