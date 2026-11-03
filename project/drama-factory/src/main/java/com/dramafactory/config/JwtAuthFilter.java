package com.dramafactory.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * JWT 资源方过滤器。
 *
 * <p>密钥（auth.jwt.secret / 环境变量 AUTH_JWT_SECRET）为空时为<b>开放模式</b>
 * （单机本地使用，启动时打 warn）；配置密钥后，/api/**（除白名单）必须携带
 * 有效的 Bearer access token，否则 401。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class JwtAuthFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(JwtAuthFilter.class);

    /** 不鉴权的 API 白名单 */
    private static final Set<String> ALLOWLIST = Set.of(
            "/api/health");

    private final JwtVerifier verifier;
    private final AtomicBoolean warned = new AtomicBoolean(false);

    public JwtAuthFilter(JwtVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String path = request.getRequestURI();
        if (!path.startsWith("/api/") || ALLOWLIST.contains(path)) {
            filterChain.doFilter(request, response);
            return;
        }
        // /api/auth/** 由 AuthProxyController 代理到 auth-service，其自身负责鉴权；放行避免"登录前先要求登录"
        if (path.startsWith("/api/auth/")) {
            filterChain.doFilter(request, response);
            return;
        }
        if (!verifier.isEnabled()) {
            if (warned.compareAndSet(false, true)) {
                log.warn("AUTH_JWT_SECRET 未配置，API 鉴权处于开放模式（仅适合单机本地使用）");
            }
            filterChain.doFilter(request, response);
            return;
        }
        String header = request.getHeader("Authorization");
        Map<String, Object> claims = null;
        if (header != null && header.startsWith("Bearer ")) {
            claims = verifier.verify(header.substring(7));
        }
        if (claims == null) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"code\":\"UNAUTHORIZED\",\"message\":\"缺少或无效的登录凭证\"}");
            return;
        }
        request.setAttribute("auth.userId", String.valueOf(claims.get("sub")));
        request.setAttribute("auth.role", String.valueOf(claims.get("role")));
        filterChain.doFilter(request, response);
    }
}
