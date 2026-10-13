package com.dramafactory.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/**
 * 请求级 request_id 过滤器。
 *
 * <p>职责：
 * <ol>
 *     <li>从请求头 X-Request-Id 读取调用方传入的链路 ID，缺失时生成 UUID；</li>
 *     <li>写入 MDC（key = request_id），供日志 pattern / JSON encoder 使用；</li>
 *     <li>请求结束后将同一个 ID 写回响应头 X-Request-Id，便于前端 / 上游串联；</li>
 *     <li>finally 中清理 MDC，避免线程复用导致上下文串味。</li>
 * </ol>
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    /** 请求 / 响应头中的链路 ID 名称 */
    private static final String HEADER_NAME = "X-Request-Id";

    /** MDC 中的键名，需与 logback 配置中的 %X{request_id} 保持一致 */
    private static final String MDC_KEY = "request_id";

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        // 1. 读取请求头，为空则生成新的 UUID
        String requestId = request.getHeader(HEADER_NAME);
        if (!StringUtils.hasText(requestId)) {
            requestId = UUID.randomUUID().toString();
        }

        // 2. 写入 MDC，使本次请求内的所有日志自动带上 request_id
        MDC.put(MDC_KEY, requestId);
        // 3. 先写回响应头：必须在过滤链执行前设置，否则真实容器可能已提交响应导致写头无效
        //    （MockMvc 测试不 commit 响应，所以写在 finally 也能过，但生产 Tomcat 不行）
        response.setHeader(HEADER_NAME, requestId);
        try {
            // 4. 继续执行过滤链
            filterChain.doFilter(request, response);
        } finally {
            // 5. 清理 MDC，避免线程复用导致上下文串味
            MDC.clear();
        }
    }
}
