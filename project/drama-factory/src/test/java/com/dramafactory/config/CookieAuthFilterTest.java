package com.dramafactory.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Collections;
import java.util.Enumeration;
import java.util.LinkedHashSet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * CookieAuthFilter 分支覆盖测试（同包直接调 doFilterInternal）。
 *
 * 覆盖说明（JaCoCo 行号）：
 * - 29(3)：existing != null && !existing.isEmpty() —— 3 个测试：
 *          Authorization 非空透传原对象 / 空串透传原对象 / null 透传原对象。
 * - 35(3)：token == null || token.isEmpty() —— cookies 为 null / 无 df_at / df_at 为空串。
 * - 44(2)：包装器 getHeader 的 equalsIgnoreCase 真/假两臂。
 * - 52(2)：包装器 getHeaders 的 Authorization 命中臂 + 非命中臂。
 * - 62(2)+63(2)：包装器 getHeaderNames 的 original != null true/false 两臂。
 * - 77(1)+78(2)+79(2)：readCookie —— cookies 为 null 走 77；循环未命中走 78/79；
 *          由 cookieMissing_noDfAt_passesOriginalRequest 与 cookieEmptyToken_passesOriginalRequest 覆盖。
 *
 * 诚实跳过清单：无（所有列出的分支均已覆盖）。
 */
class CookieAuthFilterTest {

    private CookieAuthFilter filter;
    private HttpServletRequest request;
    private HttpServletResponse response;
    private FilterChain filterChain;

    @BeforeEach
    void setUp() {
        filter = new CookieAuthFilter();
        request = mock(HttpServletRequest.class);
        response = mock(HttpServletResponse.class);
        filterChain = mock(FilterChain.class);
    }

    // ---------- 第 29 行分支：existing != null && !existing.isEmpty() ----------

    @Test
    void existingAuthorization_passesOriginalRequest() throws Exception {
        // 覆盖第 29 行 true 臂（非空字符串）：直接透传原 request
        when(request.getHeader("Authorization")).thenReturn("Bearer abc");

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        assertSame(request, captor.getValue());
    }

    @Test
    void emptyAuthorizationNoCookie_passesOriginalRequest() throws Exception {
        // 覆盖第 29 行 existing.isEmpty() true 臂 → 进入 cookie 逻辑，无 cookie → 第 35 行 true 臂
        when(request.getHeader("Authorization")).thenReturn("");
        when(request.getCookies()).thenReturn(null);

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        assertSame(request, captor.getValue());
    }

    @Test
    void nullAuthorizationNoCookie_passesOriginalRequest() throws Exception {
        // 覆盖第 29 行 existing != null 的 false 臂（默认 mock 返回 null）→ 无 cookie → 透传原对象
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getCookies()).thenReturn(null);

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        assertSame(request, captor.getValue());
    }

    // ---------- 第 35 行分支：token == null || token.isEmpty() ----------

    @Test
    void cookiesNull_passesOriginalRequest() throws Exception {
        // 覆盖第 77 行 cookies == null 的 true 臂
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getCookies()).thenReturn(null);

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        assertSame(request, captor.getValue());
    }

    @Test
    void cookieMissing_noDfAt_passesOriginalRequest() throws Exception {
        // 覆盖第 78/79 行循环未命中 → readCookie 返回 null → 第 35 行 true 臂
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getCookies()).thenReturn(new Cookie[]{new Cookie("other", "x")});

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        assertSame(request, captor.getValue());
    }

    @Test
    void cookieEmptyToken_passesOriginalRequest() throws Exception {
        // 覆盖第 79 行命中后返回 "" → 第 35 行 token.isEmpty() true 臂
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getCookies()).thenReturn(new Cookie[]{new Cookie("df_at", "")});

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        assertSame(request, captor.getValue());
    }

    // ---------- 第 44 / 52 / 62 / 63 行：包装器方法行为 ----------

    @Test
    void wrapperGetHeader_authorizationAndOther() throws Exception {
        // 覆盖第 44 行 equalsIgnoreCase 真臂（大小写）与假臂（其他 header 透传）
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getHeader("X-Other")).thenReturn("v");
        when(request.getCookies()).thenReturn(new Cookie[]{new Cookie("df_at", "tok")});

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        HttpServletRequest wrapper = captor.getValue();

        assertNotNull(wrapper);
        assertFalse(wrapper == request);
        assertEquals("Bearer tok", wrapper.getHeader("Authorization"));
        assertEquals("Bearer tok", wrapper.getHeader("authorization"));
        assertEquals("v", wrapper.getHeader("X-Other"));
    }

    @Test
    void wrapperGetHeaders_authorizationAndOther() throws Exception {
        // 覆盖第 52 行 getHeaders 命中臂（返回仅含 Bearer tok）与假臂（透传 super）
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getHeaders("X-Other"))
                .thenReturn(Collections.enumeration(Collections.singletonList("orig")));
        when(request.getCookies()).thenReturn(new Cookie[]{new Cookie("df_at", "tok")});

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        HttpServletRequest wrapper = captor.getValue();

        Enumeration<String> authHeaders = wrapper.getHeaders("Authorization");
        LinkedHashSet<String> collected = new LinkedHashSet<>();
        while (authHeaders.hasMoreElements()) {
            collected.add(authHeaders.nextElement());
        }
        assertEquals(1, collected.size());
        assertTrue(collected.contains("Bearer tok"));

        Enumeration<String> otherHeaders = wrapper.getHeaders("X-Other");
        assertEquals("orig", otherHeaders.nextElement());
    }

    @Test
    void wrapperGetHeaderNames_withOriginalNames_containsBoth() throws Exception {
        // 覆盖第 62/63 行 original != null 的 true 臂（迭代合并）
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getHeaderNames())
                .thenReturn(Collections.enumeration(Collections.singletonList("X-A")));
        when(request.getCookies()).thenReturn(new Cookie[]{new Cookie("df_at", "tok")});

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        HttpServletRequest wrapper = captor.getValue();

        Enumeration<String> names = wrapper.getHeaderNames();
        LinkedHashSet<String> collected = new LinkedHashSet<>();
        while (names.hasMoreElements()) {
            collected.add(names.nextElement());
        }
        assertTrue(collected.contains("X-A"));
        assertTrue(collected.contains("Authorization"));
    }

    @Test
    void wrapperGetHeaderNames_originalNull_containsOnlyAuthorization() throws Exception {
        // 覆盖第 62 行 original != null 的 false 臂（null 时不迭代）
        when(request.getHeader("Authorization")).thenReturn(null);
        when(request.getHeaderNames()).thenReturn(null);
        when(request.getCookies()).thenReturn(new Cookie[]{new Cookie("df_at", "tok")});

        filter.doFilterInternal(request, response, filterChain);

        ArgumentCaptor<HttpServletRequest> captor = ArgumentCaptor.forClass(HttpServletRequest.class);
        verify(filterChain).doFilter(captor.capture(), org.mockito.ArgumentMatchers.eq(response));
        HttpServletRequest wrapper = captor.getValue();

        Enumeration<String> names = wrapper.getHeaderNames();
        LinkedHashSet<String> collected = new LinkedHashSet<>();
        while (names.hasMoreElements()) {
            collected.add(names.nextElement());
        }
        assertEquals(1, collected.size());
        assertTrue(collected.contains("Authorization"));
    }
}
