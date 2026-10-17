// 文件：src/test/java/com/dramafactory/config/JwtAuthFilterV229Test.java

package com.dramafactory.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

class JwtAuthFilterV229Test {

    private static final String SECRET = "test-secret";

    private static String base64Url(byte[] data) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(data);
    }

    private static String hs256Token(String secret, String sub, String role) {
        String header = base64Url("{\"alg\":\"HS256\",\"typ\":\"JWT\"}".getBytes(StandardCharsets.UTF_8));
        String payloadJson = "{\"sub\":\"" + sub + "\",\"role\":\"" + role + "\",\"exp\":" + (System.currentTimeMillis() / 1000 + 3600) + "}";
        String payload = base64Url(payloadJson.getBytes(StandardCharsets.UTF_8));
        String signingInput = header + "." + payload;
        try {
            javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
            mac.init(new javax.crypto.spec.SecretKeySpec(
                    secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] sig = mac.doFinal(signingInput.getBytes(StandardCharsets.UTF_8));
            return signingInput + "." + base64Url(sig);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static HttpServletResponse responseWithWriter(StringWriter sink) throws java.io.IOException {
        HttpServletResponse response = mock(HttpServletResponse.class);
        doReturn(new PrintWriter(sink)).when(response).getWriter();
        return response;
    }

    @Test
    @DisplayName("非 /api/ 路径直接放行，不鉴权")
    void doFilterInternal_nonApiPathPassesThrough() throws Exception {
        JwtVerifier verifier = new JwtVerifier(SECRET);
        JwtAuthFilter filter = new JwtAuthFilter(verifier);

        HttpServletRequest request = mock(HttpServletRequest.class);
        HttpServletResponse response = mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        doReturn("/index.html").when(request).getRequestURI();

        filter.doFilterInternal(request, response, chain);

        verify(chain).doFilter(request, response);
        verify(response, never()).setStatus(any(Integer.class));
    }

    @Test
    @DisplayName("/api/health 白名单路径直接放行，不鉴权")
    void doFilterInternal_allowlistedHealthPassesThrough() throws Exception {
        JwtAuthFilter filter = new JwtAuthFilter(new JwtVerifier(SECRET));

        HttpServletRequest request = mock(HttpServletRequest.class);
        HttpServletResponse response = mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        doReturn("/api/health").when(request).getRequestURI();

        filter.doFilterInternal(request, response, chain);

        verify(chain).doFilter(request, response);
        verify(response, never()).setStatus(any(Integer.class));
    }

    @Test
    @DisplayName("/api/auth/** 代理路径直接放行，不鉴权")
    void doFilterInternal_authProxyPathPassesThrough() throws Exception {
        JwtAuthFilter filter = new JwtAuthFilter(new JwtVerifier(SECRET));

        HttpServletRequest request = mock(HttpServletRequest.class);
        HttpServletResponse response = mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        doReturn("/api/auth/login").when(request).getRequestURI();

        filter.doFilterInternal(request, response, chain);

        verify(chain).doFilter(request, response);
        verify(response, never()).setStatus(any(Integer.class));
    }

    @Test
    @DisplayName("开放模式（secret 为空）连续两次请求均放行，第二次不重复 warn")
    void doFilterInternal_openModePassesThroughBothCalls() throws Exception {
        JwtAuthFilter filter = new JwtAuthFilter(new JwtVerifier(""));

        HttpServletRequest request = mock(HttpServletRequest.class);
        HttpServletResponse response = mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        doReturn("/api/orders").when(request).getRequestURI();

        filter.doFilterInternal(request, response, chain);
        filter.doFilterInternal(request, response, chain);

        verify(chain, times(2)).doFilter(request, response);
        verify(response, never()).setStatus(any(Integer.class));
    }

    @Test
    @DisplayName("启用模式且无 Authorization 头：返回 401 且不调用 filterChain")
    void doFilterInternal_enabledModeMissingHeaderReturns401() throws Exception {
        JwtAuthFilter filter = new JwtAuthFilter(new JwtVerifier(SECRET));

        HttpServletRequest request = mock(HttpServletRequest.class);
        StringWriter sink = new StringWriter();
        HttpServletResponse response = responseWithWriter(sink);
        FilterChain chain = mock(FilterChain.class);
        doReturn("/api/orders").when(request).getRequestURI();
        doReturn(null).when(request).getHeader("Authorization");

        filter.doFilterInternal(request, response, chain);

        verify(response).setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        verify(response).setContentType("application/json;charset=UTF-8");
        verify(chain, never()).doFilter(request, response);
        assertThat(sink.toString()).contains("UNAUTHORIZED");
    }

    @Test
    @DisplayName("启用模式但 Authorization 头非 Bearer 前缀：返回 401")
    void doFilterInternal_enabledModeNonBearerHeaderReturns401() throws Exception {
        JwtAuthFilter filter = new JwtAuthFilter(new JwtVerifier(SECRET));

        HttpServletRequest request = mock(HttpServletRequest.class);
        StringWriter sink = new StringWriter();
        HttpServletResponse response = responseWithWriter(sink);
        FilterChain chain = mock(FilterChain.class);
        doReturn("/api/orders").when(request).getRequestURI();
        doReturn("Basic abc123").when(request).getHeader("Authorization");

        filter.doFilterInternal(request, response, chain);

        verify(response).setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        verify(chain, never()).doFilter(request, response);
        assertThat(sink.toString()).contains("UNAUTHORIZED");
    }

    @Test
    @DisplayName("启用模式且 Bearer token 非法：返回 401 且不调用 filterChain")
    void doFilterInternal_enabledModeInvalidBearerTokenReturns401() throws Exception {
        JwtAuthFilter filter = new JwtAuthFilter(new JwtVerifier(SECRET));

        HttpServletRequest request = mock(HttpServletRequest.class);
        StringWriter sink = new StringWriter();
        HttpServletResponse response = responseWithWriter(sink);
        FilterChain chain = mock(FilterChain.class);
        doReturn("/api/orders").when(request).getRequestURI();
        doReturn("Bearer not.a.valid.jwt").when(request).getHeader("Authorization");

        filter.doFilterInternal(request, response, chain);

        verify(response).setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        verify(chain, never()).doFilter(request, response);
        assertThat(sink.toString()).contains("UNAUTHORIZED");
    }

    @Test
    @DisplayName("启用模式且 Bearer token 合法：注入 auth.userId/auth.role 并放行")
    void doFilterInternal_enabledModeValidBearerTokenPassesThrough() throws Exception {
        JwtAuthFilter filter = new JwtAuthFilter(new JwtVerifier(SECRET));

        HttpServletRequest request = mock(HttpServletRequest.class);
        HttpServletResponse response = mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);
        doReturn("/api/orders").when(request).getRequestURI();
        doReturn("Bearer " + hs256Token(SECRET, "123", "USER"))
                .when(request).getHeader("Authorization");

        filter.doFilterInternal(request, response, chain);

        verify(request).setAttribute("auth.userId", "123");
        verify(request).setAttribute("auth.role", "USER");
        verify(chain).doFilter(request, response);
        verify(response, never()).setStatus(any(Integer.class));
    }

    @Test
    @DisplayName("启用模式且 token 签名不匹配：返回 401")
    void doFilterInternal_enabledModeWrongSignatureReturns401() throws Exception {
        JwtAuthFilter filter = new JwtAuthFilter(new JwtVerifier(SECRET));

        HttpServletRequest request = mock(HttpServletRequest.class);
        StringWriter sink = new StringWriter();
        HttpServletResponse response = responseWithWriter(sink);
        FilterChain chain = mock(FilterChain.class);
        doReturn("/api/orders").when(request).getRequestURI();
        doReturn("Bearer " + hs256Token("other-secret", "123", "USER"))
                .when(request).getHeader("Authorization");

        filter.doFilterInternal(request, response, chain);

        verify(response).setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        verify(chain, never()).doFilter(request, response);
        assertThat(sink.toString()).contains("UNAUTHORIZED");
    }
}