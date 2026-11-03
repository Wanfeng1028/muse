package com.dramaauth.security;

import com.dramaauth.exception.ApiException;
import com.dramaauth.service.JwtService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.util.Map;

/**
 * JWT 鉴权拦截器：校验 Authorization: Bearer，要求 access token（非 REFRESH）。
 * 通过后往 request 设 userId / userRole。
 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

    public static final String ATTR_USER_ID = "userId";
    public static final String ATTR_USER_ROLE = "userRole";

    private final JwtService jwtService;

    public AuthInterceptor(JwtService jwtService) {
        this.jwtService = jwtService;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        // CORS 预检放行
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }
        String header = request.getHeader("Authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHORIZED", "缺少登录凭证");
        }
        Map<String, Object> claims = jwtService.parseAndValidate(header.substring(7));
        if ("REFRESH".equals(claims.get("role"))) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_TOKEN", "请使用 access token");
        }
        request.setAttribute(ATTR_USER_ID, Long.valueOf(String.valueOf(claims.get("sub"))));
        request.setAttribute(ATTR_USER_ROLE, String.valueOf(claims.get("role")));
        return true;
    }
}
