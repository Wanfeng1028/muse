package com.dramafactory.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Collections;
import java.util.Enumeration;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CookieAuthFilter extends OncePerRequestFilter {

    private static final String COOKIE_AT = "df_at";

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String existing = request.getHeader("Authorization");
        if (existing != null && !existing.isEmpty()) {
            filterChain.doFilter(request, response);
            return;
        }

        String token = readCookie(request, COOKIE_AT);
        if (token == null || token.isEmpty()) {
            filterChain.doFilter(request, response);
            return;
        }

        String bearer = "Bearer " + token;
        HttpServletRequestWrapper wrapper = new HttpServletRequestWrapper(request) {
            @Override
            public String getHeader(String name) {
                if ("Authorization".equalsIgnoreCase(name)) {
                    return bearer;
                }
                return super.getHeader(name);
            }

            @Override
            public Enumeration<String> getHeaders(String name) {
                if ("Authorization".equalsIgnoreCase(name)) {
                    return Collections.enumeration(Collections.singletonList(bearer));
                }
                return super.getHeaders(name);
            }

            @Override
            public Enumeration<String> getHeaderNames() {
                java.util.LinkedHashSet<String> names = new java.util.LinkedHashSet<>();
                Enumeration<String> original = super.getHeaderNames();
                if (original != null) {
                    while (original.hasMoreElements()) {
                        names.add(original.nextElement());
                    }
                }
                names.add("Authorization");
                return Collections.enumeration(names);
            }
        };

        filterChain.doFilter(wrapper, response);
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
}
