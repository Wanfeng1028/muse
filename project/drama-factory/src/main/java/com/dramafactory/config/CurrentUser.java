package com.dramafactory.config;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/**
 * 取当前请求的用户 id。JwtAuthFilter 鉴权成功时会把 {@code auth.userId} 塞进 request attribute；
 * 密钥为空（开放模式）或没有请求上下文时，统一回退成 {@code local}。
 *
 * 注意：项目没上 Spring Security，所以这里只认 request attribute，不碰 SecurityContext。
 */
@Component
public class CurrentUser {

    public static final String DEFAULT_OWNER_ID = "local";

    /**
     * 返回当前请求归属的用户 id，永不返回 null，也永不抛 NPE。
     */
    public String currentUserId() {
        RequestAttributes attrs = RequestContextHolder.getRequestAttributes();
        if (!(attrs instanceof ServletRequestAttributes servletAttrs)) {
            return DEFAULT_OWNER_ID;
        }
        HttpServletRequest request = servletAttrs.getRequest();
        if (request == null) {
            return DEFAULT_OWNER_ID;
        }
        Object userId = request.getAttribute("auth.userId");
        if (userId == null) {
            return DEFAULT_OWNER_ID;
        }
        String value = String.valueOf(userId);
        if (value.isBlank()) {
            return DEFAULT_OWNER_ID;
        }
        return value;
    }
}
