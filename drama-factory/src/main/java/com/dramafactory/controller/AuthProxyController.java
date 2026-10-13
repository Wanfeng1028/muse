package com.dramafactory.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.Set;

@RestController
@Tag(name = "Auth", description = "认证请求代理到账号服务")
public class AuthProxyController {

    private static final Set<String> HOP_BY_HOP = new HashSet<>(Set.of(
            "host", "content-length", "transfer-encoding", "connection",
            "keep-alive", "proxy-authenticate", "proxy-authorization",
            "te", "trailers", "upgrade"
    ));

    private static final String COOKIE_AT = "df_at";
    private static final String COOKIE_RT = "df_rt";
    private static final long RT_MAX_AGE = 604800L;

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final String authServiceUrl;

    public AuthProxyController(
            // 默认 [::1] 而非 localhost：本沙箱的出口透明代理只拦截 IPv4 回环，IPv6 直通；
            // 生产/docker 环境无此限制，可配 http://auth:8082 等任意地址
            @Value("${auth.service.url:http://[::1]:8082}") String authServiceUrl) {
        this.authServiceUrl = trimTrailingSlash(authServiceUrl);
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        this.objectMapper = new ObjectMapper();
    }

    @RequestMapping("/api/auth/**")
    @Operation(summary = "代理认证请求到账号服务")
    public ResponseEntity<byte[]> proxy(HttpServletRequest request) {
        String method = request.getMethod();
        String path = extractPath(request);
        String query = request.getQueryString();
        String targetUrl = authServiceUrl + path + (query != null && !query.isEmpty() ? "?" + query : "");

        byte[] body;
        try {
            body = request.getInputStream().readAllBytes();
        } catch (IOException e) {
            return upstreamUnavailable();
        }

        // refresh: 从 df_rt cookie 取 refreshToken 构造请求体
        if ("POST".equalsIgnoreCase(method) && "/api/auth/refresh".equals(path)) {
            String rt = readCookie(request, COOKIE_RT);
            if (rt == null || rt.isEmpty()) {
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"code\":\"UNAUTHORIZED\",\"message\":\"未登录\"}".getBytes(StandardCharsets.UTF_8));
            }
            ObjectNode node = objectMapper.createObjectNode();
            node.put("refreshToken", rt);
            try {
                body = objectMapper.writeValueAsBytes(node);
            } catch (Exception e) {
                return upstreamUnavailable();
            }
        }

        HttpRequest.Builder rb = HttpRequest.newBuilder()
                .uri(URI.create(targetUrl))
                .timeout(Duration.ofSeconds(15));

        // 透传业务头（过滤 hop-by-hop），Authorization 优先用现有头，否则用 df_at cookie
        String authHeader = null;
        Enumeration<String> headerNames = request.getHeaderNames();
        if (headerNames != null) {
            while (headerNames.hasMoreElements()) {
                String name = headerNames.nextElement();
                if (name == null) continue;
                String lower = name.toLowerCase();
                if (HOP_BY_HOP.contains(lower)) continue;
                if ("cookie".equals(lower)) continue;
                Enumeration<String> vals = request.getHeaders(name);
                while (vals.hasMoreElements()) {
                    String v = vals.nextElement();
                    if ("authorization".equals(lower)) {
                        authHeader = v;
                    }
                    rb.header(name, v);
                }
            }
        }

        if (authHeader == null || authHeader.isEmpty()) {
            String at = readCookie(request, COOKIE_AT);
            if (at != null && !at.isEmpty()) {
                authHeader = "Bearer " + at;
                rb.header("Authorization", authHeader);
            }
        }

        if (body.length > 0 || hasRequestBody(method)) {
            rb.method(method, HttpRequest.BodyPublishers.ofByteArray(body));
        } else {
            rb.method(method, HttpRequest.BodyPublishers.noBody());
        }

        HttpResponse<byte[]> upstream;
        try {
            upstream = httpClient.send(rb.build(), HttpResponse.BodyHandlers.ofByteArray());
        } catch (IOException | InterruptedException e) {
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            return upstreamUnavailable();
        }

        int status = upstream.statusCode();
        byte[] respBody = upstream.body() == null ? new byte[0] : upstream.body();
        HttpHeaders respHeaders = new HttpHeaders();
        upstream.headers().map().forEach((k, vs) -> {
            if (k == null) return;
            String lower = k.toLowerCase();
            if (HOP_BY_HOP.contains(lower)) return;
            for (String v : vs) {
                respHeaders.add(k, v);
            }
        });

        // 登录 / refresh / oauth callback：剥离 token，设置 cookie，返回 {"ok":true}
        if (isTokenResponse(path, status)) {
            try {
                JsonNode node = objectMapper.readTree(respBody);
                String accessToken = textOrNull(node, "accessToken");
                String refreshToken = textOrNull(node, "refreshToken");
                long expiresIn = node.hasNonNull("expiresIn") ? node.get("expiresIn").asLong() : 0L;
                if (expiresIn <= 0) expiresIn = 3600L; // 防御：上游未给有效期时默认 1 小时，避免 Max-Age=0 误删 cookie

                HttpHeaders out = new HttpHeaders();
                out.setContentType(MediaType.APPLICATION_JSON);
                if (accessToken != null) {
                    out.add(HttpHeaders.SET_COOKIE, buildCookie(COOKIE_AT, accessToken, "/", expiresIn));
                }
                if (refreshToken != null) {
                    out.add(HttpHeaders.SET_COOKIE, buildCookie(COOKIE_RT, refreshToken, "/api/auth", RT_MAX_AGE));
                }
                return new ResponseEntity<>("{\"ok\":true}".getBytes(StandardCharsets.UTF_8), out, HttpStatus.OK);
            } catch (Exception e) {
                // 上游返回非预期结构：按 502 处理，避免泄露原始 token
                return upstreamUnavailable();
            }
        }

        // logout：清除 cookie
        if ("POST".equalsIgnoreCase(method) && "/api/auth/logout".equals(path)) {
            if (status >= 200 && status < 300) {
                HttpHeaders out = new HttpHeaders();
                out.setContentType(MediaType.APPLICATION_JSON);
                out.add(HttpHeaders.SET_COOKIE, buildCookie(COOKIE_AT, "", "/", 0L));
                out.add(HttpHeaders.SET_COOKIE, buildCookie(COOKIE_RT, "", "/api/auth", 0L));
                return new ResponseEntity<>("{\"ok\":true}".getBytes(StandardCharsets.UTF_8), out, HttpStatus.OK);
            }
            return new ResponseEntity<>(respBody, respHeaders, HttpStatus.valueOf(status));
        }

        // 其余接口原样透传
        return new ResponseEntity<>(respBody, respHeaders, HttpStatus.valueOf(status));
    }

    private boolean isTokenResponse(String path, int status) {
        if (status < 200 || status >= 300) return false;
        if ("/api/auth/login".equals(path) || "/api/auth/refresh".equals(path)) return true;
        // oauth callback: /api/auth/oauth/{provider}/callback
        if (path.startsWith("/api/auth/oauth/") && path.endsWith("/callback")) return true;
        return false;
    }

    private boolean hasRequestBody(String method) {
        return "POST".equalsIgnoreCase(method)
                || "PUT".equalsIgnoreCase(method)
                || "PATCH".equalsIgnoreCase(method)
                || "DELETE".equalsIgnoreCase(method);
    }

    private String extractPath(HttpServletRequest request) {
        String uri = request.getRequestURI();
        String ctx = request.getContextPath();
        if (ctx != null && !ctx.isEmpty() && uri.startsWith(ctx)) {
            uri = uri.substring(ctx.length());
        }
        return uri;
    }

    private String readCookie(HttpServletRequest request, String name) {
        Cookie[] cookies = request.getCookies();
        if (cookies == null) return null;
        for (Cookie c : cookies) {
            if (name.equals(c.getName())) {
                return c.getValue();
            }
        }
        return null;
    }

    private String buildCookie(String name, String value, String path, long maxAge) {
        StringBuilder sb = new StringBuilder();
        sb.append(name).append('=').append(value == null ? "" : value);
        sb.append("; Path=").append(path);
        sb.append("; HttpOnly");
        sb.append("; SameSite=Lax");
        sb.append("; Max-Age=").append(maxAge);
        return sb.toString();
    }

    private String textOrNull(JsonNode node, String field) {
        if (node == null || !node.hasNonNull(field)) return null;
        String v = node.get(field).asText();
        return v == null || v.isEmpty() ? null : v;
    }

    private ResponseEntity<byte[]> upstreamUnavailable() {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"code\":\"AUTH_UPSTREAM_UNAVAILABLE\",\"message\":\"账号服务暂时不可用\"}"
                        .getBytes(StandardCharsets.UTF_8));
    }

    private static String trimTrailingSlash(String s) {
        if (s == null) return "";
        while (s.endsWith("/")) {
            s = s.substring(0, s.length() - 1);
        }
        return s;
    }
}
