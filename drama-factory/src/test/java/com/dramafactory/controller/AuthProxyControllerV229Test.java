// 文件：src/test/java/com/dramafactory/controller/AuthProxyControllerV229Test.java

package com.dramafactory.controller;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;
import java.net.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * AuthProxyController 剩余分支覆盖补齐（2026-10-17 JaCoCo 口径）。
 * 纯 Mockito 单元测试，不启动 Spring 上下文。
 */
class AuthProxyControllerV229Test {

    private HttpClient httpClient;
    private AuthProxyController controller;

    @BeforeEach
    void setUp() {
        httpClient = mock(HttpClient.class);
        controller = new AuthProxyController("http://auth.local:8082", httpClient, false);
    }

    // ------------------------------------------------------------------
    // proxy: getInputStream() 抛 IOException -> 502
    // ------------------------------------------------------------------
    @Test
    @DisplayName("proxy 读取请求体抛 IOException 时返回 502 且携带 AUTH_UPSTREAM_UNAVAILABLE")
    void proxyReadBodyIOExceptionReturns502() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("/api");
        when(request.getHeader("Authorization")).thenReturn("Bearer x");
        ServletInputStream brokenStream = mock(ServletInputStream.class);
        when(brokenStream.readAllBytes()).thenThrow(new IOException("boom"));
        when(request.getInputStream()).thenReturn(brokenStream);

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(502);
        assertThat(new String(resp.getBody(), StandardCharsets.UTF_8))
                .contains("AUTH_UPSTREAM_UNAVAILABLE");
    }

    // ------------------------------------------------------------------
    // proxy: refresh 时上游返回非法 JSON -> isTokenResponse 内 catch -> 502
    // ------------------------------------------------------------------
    @Test
    @DisplayName("refresh 上游返回非法 JSON 时 502 而非泄露 token")
    void proxyRefreshInvalidJsonUpstreamReturns502() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/refresh");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeaderNames()).thenReturn(Collections.enumeration(List.of("Authorization")));
        when(request.getHeaders("Authorization"))
                .thenReturn(Collections.enumeration(List.of("Bearer token")));
        when(request.getInputStream()).thenReturn(streamOf(""));
        when(request.getCookies()).thenReturn(new Cookie[]{new Cookie("df_rt", "rt-value")});

        HttpResponse<byte[]> upstream = upstreamResponse(200, "not-a-json{{{".getBytes(StandardCharsets.UTF_8),
                Map.of("Content-Type", List.of("application/json")));
        when(httpClient.send(any(HttpRequest.class), ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenReturn(upstream);

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(502);
        assertThat(new String(resp.getBody(), StandardCharsets.UTF_8))
                .contains("AUTH_UPSTREAM_UNAVAILABLE");
    }

    // ------------------------------------------------------------------
    // proxy: httpClient.send 抛 InterruptedException -> 中断标记 + 502
    // ------------------------------------------------------------------
    @Test
    @DisplayName("httpClient.send 抛 InterruptedException 时置中断标记并返回 502")
    void proxySendInterruptedExceptionSetsInterruptAndReturns502() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("GET");
        when(request.getRequestURI()).thenReturn("/api/auth/me");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeaderNames()).thenReturn(Collections.enumeration(List.of()));
        when(request.getInputStream()).thenReturn(streamOf(""));
        when(request.getCookies()).thenReturn(null);

        when(httpClient.send(any(HttpRequest.class), ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenThrow(new InterruptedException("interrupted"));

        try {
            ResponseEntity<byte[]> resp = controller.proxy(request);

            assertThat(resp.getStatusCode().value()).isEqualTo(502);
            assertThat(Thread.currentThread().isInterrupted()).isTrue();
        } finally {
            // 清理中断标记，避免污染后续测试
            Thread.interrupted();
        }
    }

    // ------------------------------------------------------------------
    // proxy: respHeaders 复制时 hop-by-hop 过滤分支
    // ------------------------------------------------------------------
    @Test
    @DisplayName("上游响应头 hop-by-hop 被过滤，业务头原样透传")
    void proxyFiltersHopByHopResponseHeaders() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("GET");
        when(request.getRequestURI()).thenReturn("/api/auth/me");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeaderNames()).thenReturn(Collections.enumeration(List.of()));
        when(request.getInputStream()).thenReturn(streamOf(""));
        when(request.getCookies()).thenReturn(null);

        Map<String, List<String>> headers = Map.of(
                "Content-Type", List.of("application/json"),
                "connection", List.of("keep-alive"),
                "Transfer-Encoding", List.of("chunked")
        );
        HttpResponse<byte[]> upstream = upstreamResponse(200, "{\"name\":\"x\"}".getBytes(StandardCharsets.UTF_8), headers);
        when(httpClient.send(any(HttpRequest.class), ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenReturn(upstream);

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        assertThat(resp.getHeaders().getFirst("Content-Type")).isEqualTo("application/json");
        assertThat(resp.getHeaders().containsKey("connection")).isFalse();
        assertThat(resp.getHeaders().containsKey("Transfer-Encoding")).isFalse();
    }

    // ------------------------------------------------------------------
    // isCsrfAllowed: Origin 为空但 Referer 非空 -> 走 Referer 分支（host 一致放行）
    // ------------------------------------------------------------------
    @Test
    @DisplayName("Origin 缺失时回退 Referer，host 与 Host 一致则放行")
    void csrfFallsBackToRefererAndAllowsWhenHostMatches() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeader("Origin")).thenReturn("");
        when(request.getHeader("Referer")).thenReturn("https://app.example.com/page");
        when(request.getHeader("Host")).thenReturn("app.example.com");
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getHeaderNames()).thenReturn(Collections.enumeration(List.of()));
        when(request.getInputStream()).thenReturn(streamOf("{}"));
        when(request.getCookies()).thenReturn(null);

        HttpResponse<byte[]> upstream = upstreamResponse(200,
                "{\"accessToken\":\"at\",\"refreshToken\":\"rt\"}".getBytes(StandardCharsets.UTF_8),
                Map.of("Content-Type", List.of("application/json")));
        when(httpClient.send(any(HttpRequest.class), ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenReturn(upstream);

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
    }

    // ------------------------------------------------------------------
    // isCsrfAllowed: Referer host 与 Host 不一致 -> 403
    // ------------------------------------------------------------------
    @Test
    @DisplayName("Referer host 与 Host 不一致时返回 403")
    void csrfRefererHostMismatchReturns403() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeader("Origin")).thenReturn(null);
        when(request.getHeader("Referer")).thenReturn("https://evil.example.com/page");
        when(request.getHeader("Host")).thenReturn("app.example.com");
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getInputStream()).thenReturn(streamOf("{}"));

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(403);
        assertThat(new String(resp.getBody(), StandardCharsets.UTF_8)).contains("FORBIDDEN");
    }

    // ------------------------------------------------------------------
    // isCsrfAllowed: Origin 解析出空字符串 host -> 403
    // ------------------------------------------------------------------
    @Test
    @DisplayName("Origin 解析出空 host 时返回 403")
    void csrfOriginWithEmptyHostReturns403() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeader("Origin")).thenReturn("file:///tmp/page");
        when(request.getHeader("Host")).thenReturn("app.example.com");
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getInputStream()).thenReturn(streamOf("{}"));

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(403);
    }

    // ------------------------------------------------------------------
    // isCsrfAllowed: Host 为空字符串 -> 403
    // ------------------------------------------------------------------
    @Test
    @DisplayName("Host 头为空字符串时返回 403")
    void csrfEmptyHostHeaderReturns403() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeader("Origin")).thenReturn("https://app.example.com");
        when(request.getHeader("Host")).thenReturn("");
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getInputStream()).thenReturn(streamOf("{}"));

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(403);
    }

    // ------------------------------------------------------------------
    // textOrNull: hasNonNull(field) 为 false -> null（无 accessToken 字段）
    // 用 login 上游体触发：只有 refreshToken -> 只设 rt cookie
    // ------------------------------------------------------------------
    @Test
    @DisplayName("login 上游无 accessToken 字段时只设 df_rt cookie")
    void loginUpstreamMissingAccessTokenOnlySetsRtCookie() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeaderNames()).thenReturn(Collections.enumeration(List.of()));
        when(request.getInputStream()).thenReturn(streamOf("{\"username\":\"u\"}"));
        when(request.getCookies()).thenReturn(null);

        HttpResponse<byte[]> upstream = upstreamResponse(200,
                "{\"refreshToken\":\"rt-1\",\"expiresIn\":3600}".getBytes(StandardCharsets.UTF_8),
                Map.of("Content-Type", List.of("application/json")));
        when(httpClient.send(any(HttpRequest.class), ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenReturn(upstream);

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        List<String> cookies = resp.getHeaders().get("Set-Cookie");
        assertThat(cookies).isNotNull();
        assertThat(cookies).anyMatch(c -> c.startsWith("df_rt=rt-1"));
        assertThat(cookies).noneMatch(c -> c.startsWith("df_at="));
    }

    // ------------------------------------------------------------------
    // textOrNull: 字段值为空字符串 -> null
    // 用 login 上游返回 accessToken="" -> 只设 refresh cookie
    // ------------------------------------------------------------------
    @Test
    @DisplayName("login 上游 accessToken 为空字符串时只设 df_rt cookie")
    void loginUpstreamEmptyAccessTokenOnlySetsRtCookie() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeaderNames()).thenReturn(Collections.enumeration(List.of()));
        when(request.getInputStream()).thenReturn(streamOf("{\"username\":\"u\"}"));
        when(request.getCookies()).thenReturn(null);

        HttpResponse<byte[]> upstream = upstreamResponse(200,
                "{\"accessToken\":\"\",\"refreshToken\":\"x\",\"expiresIn\":3600}".getBytes(StandardCharsets.UTF_8),
                Map.of("Content-Type", List.of("application/json")));
        when(httpClient.send(any(HttpRequest.class), ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenReturn(upstream);

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        List<String> cookies = resp.getHeaders().get("Set-Cookie");
        assertThat(cookies).isNotNull();
        assertThat(cookies).anyMatch(c -> c.startsWith("df_rt=x"));
        assertThat(cookies).noneMatch(c -> c.startsWith("df_at="));
    }

    // ------------------------------------------------------------------
    // isTokenResponse: 非 2xx 的 login -> 直接透传，不解析 body
    // ------------------------------------------------------------------
    @Test
    @DisplayName("login 上游返回 500 时直接透传状态码与 body 不解析 token")
    void loginUpstream500IsPassedThroughWithoutParsing() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/login");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeaderNames()).thenReturn(Collections.enumeration(List.of()));
        when(request.getInputStream()).thenReturn(streamOf("{\"username\":\"u\"}"));
        when(request.getCookies()).thenReturn(null);

        byte[] upstreamBody = "{\"accessToken\":\"leaked\"}".getBytes(StandardCharsets.UTF_8);
        HttpResponse<byte[]> upstream = upstreamResponse(500, upstreamBody,
                Map.of("Content-Type", List.of("application/json")));
        when(httpClient.send(any(HttpRequest.class), ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenReturn(upstream);

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(500);
        assertThat(resp.getBody()).isEqualTo(upstreamBody);
        assertThat(resp.getHeaders().get("Set-Cookie")).isNull();
    }

    // ------------------------------------------------------------------
    // extractPath: getContextPath() 返回 null -> 直接返回 URI
    // ------------------------------------------------------------------
    @Test
    @DisplayName("contextPath 为 null 时 extractPath 直接返回原始 URI")
    void extractPathWithNullContextPathUsesRawUri() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("GET");
        when(request.getRequestURI()).thenReturn("/api/auth/me");
        when(request.getContextPath()).thenReturn(null);
        when(request.getHeaderNames()).thenReturn(Collections.enumeration(List.of()));
        when(request.getInputStream()).thenReturn(streamOf(""));
        when(request.getCookies()).thenReturn(null);

        HttpResponse<byte[]> upstream = upstreamResponse(200, "ok".getBytes(StandardCharsets.UTF_8),
                Map.of("Content-Type", List.of("text/plain")));
        when(httpClient.send(any(HttpRequest.class), ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenReturn(upstream);

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        assertThat(resp.getBody()).isEqualTo("ok".getBytes(StandardCharsets.UTF_8));
    }

    // ------------------------------------------------------------------
    // buildCookie: value 为 null -> name= 空值
    // 用 login 上游 {"refreshToken":"r"} 无 accessToken，accessToken 为 null 不设 at cookie；
    // 这里补 value 为 null 的 buildCookie 分支：通过 refresh 上游 accessToken 字段值为 null 触发
    // 使用 JSON null 使 hasNonNull 为 false -> textOrNull 返回 null，仅设 rt cookie
    // ------------------------------------------------------------------
    @Test
    @DisplayName("refresh 上游 accessToken 为 JSON null 时不设 df_at cookie")
    void refreshUpstreamNullAccessTokenSkipsAtCookie() throws Exception {
        HttpServletRequest request = mock(HttpServletRequest.class);
        when(request.getMethod()).thenReturn("POST");
        when(request.getRequestURI()).thenReturn("/api/auth/refresh");
        when(request.getContextPath()).thenReturn("");
        when(request.getHeaderNames()).thenReturn(Collections.enumeration(List.of()));
        when(request.getInputStream()).thenReturn(streamOf(""));
        when(request.getCookies()).thenReturn(new Cookie[]{new Cookie("df_rt", "rt-value")});

        HttpResponse<byte[]> upstream = upstreamResponse(200,
                "{\"accessToken\":null,\"refreshToken\":\"rt-new\",\"expiresIn\":3600}"
                        .getBytes(StandardCharsets.UTF_8),
                Map.of("Content-Type", List.of("application/json")));
        when(httpClient.send(any(HttpRequest.class), ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenReturn(upstream);

        ResponseEntity<byte[]> resp = controller.proxy(request);

        assertThat(resp.getStatusCode().value()).isEqualTo(200);
        List<String> cookies = resp.getHeaders().get("Set-Cookie");
        assertThat(cookies).isNotNull();
        assertThat(cookies).anyMatch(c -> c.startsWith("df_rt=rt-new"));
        assertThat(cookies).noneMatch(c -> c.startsWith("df_at="));
    }

    // ------------------------------------------------------------------
    // 辅助
    // ------------------------------------------------------------------

    private static ServletInputStream streamOf(String content) {
        ByteArrayInputStream bais = new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8));
        return new ServletInputStream() {
            @Override
            public boolean isFinished() {
                return bais.available() == 0;
            }

            @Override
            public boolean isReady() {
                return true;
            }

            @Override
            public void setReadListener(ReadListener readListener) {
                // no-op
            }

            @Override
            public int read() {
                return bais.read();
            }
        };
    }

    @SuppressWarnings("unchecked")
    private static HttpResponse<byte[]> upstreamResponse(int status, byte[] body, Map<String, List<String>> headers) {
        HttpResponse<byte[]> resp = mock(HttpResponse.class);
        when(resp.statusCode()).thenReturn(status);
        when(resp.body()).thenReturn(body);
        HttpHeaders httpHeaders = HttpHeaders.of(headers, (k, v) -> true);
        when(resp.headers()).thenReturn(httpHeaders);
        return resp;
    }
}