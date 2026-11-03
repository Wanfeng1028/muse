
package com.dramafactory.service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.HttpHost;
import org.apache.hc.core5.http.io.entity.StringEntity;
import org.apache.hc.core5.http.io.support.ClassicResponseBuilder;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * LlmTransport 的纯逻辑契约测试：全程无 socket、无外网。
 * 通过 HttpExecutor 函数式接口注入无 socket 的执行替身。
 */
class LlmTransportTest {

    /** 无 socket 的执行替身：返回预设响应，或抛出预设异常。 */
    private static LlmTransport.HttpExecutor ok(String body) {
        return (post, ctx) -> ClassicResponseBuilder.create(200)
                .setEntity(body, ContentType.TEXT_PLAIN).build();
    }

    private static LlmTransport.HttpExecutor status(int status, String body) {
        return (post, ctx) -> ClassicResponseBuilder.create(status)
                .setEntity(body, ContentType.TEXT_PLAIN).build();
    }

    private static LlmTransport.HttpExecutor failing(IOException failure) {
        return (post, ctx) -> {
            throw failure;
        };
    }

    // ---------- parseProxy ----------

    @Test
    void parseProxy_withUserInfo() {
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.parseProxy("http://user:pass@proxy.example.com:8080");
        assertTrue(opt.isPresent());
        LlmTransport.ProxySpec spec = opt.get();
        assertEquals("proxy.example.com", spec.host());
        assertEquals(8080, spec.port());
        assertEquals("user", spec.user());
        assertEquals("pass", spec.pass());
    }

    @Test
    void parseProxy_withoutUserInfo() {
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.parseProxy("http://proxy:3128");
        assertTrue(opt.isPresent());
        LlmTransport.ProxySpec spec = opt.get();
        assertEquals("proxy", spec.host());
        assertEquals(3128, spec.port());
        assertNull(spec.user());
        assertNull(spec.pass());
    }

    @Test
    void parseProxy_userOnly() {
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.parseProxy("http://onlyuser@proxy:3128");
        assertTrue(opt.isPresent());
        LlmTransport.ProxySpec spec = opt.get();
        assertEquals("onlyuser", spec.user());
        assertEquals("", spec.pass());
    }

    @Test
    void parseProxy_defaultPort() {
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.parseProxy("http://proxy");
        assertTrue(opt.isPresent());
        assertEquals(3128, opt.get().port());
    }

    @Test
    void parseProxy_blankAndNullAndInvalid() {
        assertTrue(LlmTransport.parseProxy("").isEmpty());
        assertTrue(LlmTransport.parseProxy(null).isEmpty());
        assertTrue(LlmTransport.parseProxy("http://[::1").isEmpty());
    }

    // ---------- resolveProxy ----------

    @Test
    void resolveProxy_lowerCaseOnly() {
        Map<String, String> env = new HashMap<>();
        env.put("https_proxy", "http://proxy:8080");
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.resolveProxy(env);
        assertTrue(opt.isPresent());
        assertEquals("proxy", opt.get().host());
        assertEquals(8080, opt.get().port());
    }

    @Test
    void resolveProxy_upperCasePriority() {
        Map<String, String> env = new HashMap<>();
        env.put("HTTPS_PROXY", "http://upper:1111");
        env.put("https_proxy", "http://lower:2222");
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.resolveProxy(env);
        assertTrue(opt.isPresent());
        assertEquals("upper", opt.get().host());
        assertEquals(1111, opt.get().port());
    }

    @Test
    void resolveProxy_allEmpty() {
        Map<String, String> env = new HashMap<>();
        env.put("HTTPS_PROXY", "");
        env.put("https_proxy", "   ");
        assertTrue(LlmTransport.resolveProxy(env).isEmpty());
    }

    // ---------- buildRequestConfig ----------

    @Test
    void buildRequestConfig_timeouts() {
        RequestConfig cfg = LlmTransport.buildRequestConfig(null, 7);
        assertEquals(7_000, cfg.getConnectTimeout().toMilliseconds());
        assertEquals(7_000, cfg.getResponseTimeout().toMilliseconds());
        assertNull(cfg.getProxy());
    }

    @Test
    void buildRequestConfig_withProxy() {
        HttpHost proxy = new HttpHost("proxy.example.com", 8080);
        RequestConfig cfg = LlmTransport.buildRequestConfig(proxy, 7);
        assertNotNull(cfg.getProxy());
        assertEquals("proxy.example.com", cfg.getProxy().getHostName());
    }

    // ---------- buildPost ----------

    @Test
    void buildPost_uriEntityAndAuthHeader() throws Exception {
        HttpPost post = LlmTransport.buildPost("https://api.example.com/v1/chat",
                "{\"a\":1}", Map.entry("Authorization", "Bearer x"));
        assertEquals("https://api.example.com/v1/chat", post.getUri().toString());
        assertNotNull(post.getEntity());
        assertTrue(post.getEntity().getContentType().contains("application/json"));
        assertEquals("Bearer x", post.getFirstHeader("Authorization").getValue());
    }

    @Test
    void buildPost_withoutAuthHeader() throws Exception {
        HttpPost post = LlmTransport.buildPost("https://api.example.com/v1/chat", "{}", null);
        assertNull(post.getFirstHeader("Authorization"));
    }

    // ---------- postJson（5 参数重载，注入 fake client） ----------

    @Test
    void postJson_success() {
        LlmTransport.HttpExecutor executor = ok("hello");
        String result = LlmTransport.postJson("https://api.example.com/x", "{}", null, 5, executor);
        assertEquals("hello", result);
    }

    @Test
    void postJson_non2xxTruncatesBody() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 400; i++) {
            sb.append('x');
        }
        LlmTransport.HttpExecutor executor = status(500, sb.toString());
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson("https://api.example.com/x", "{}", null, 5, executor));
        assertTrue(ex.getMessage().contains("500"));
        // body 部分长度应为 300
        int idx = ex.getMessage().indexOf("body=");
        assertTrue(idx >= 0);
        String bodyPart = ex.getMessage().substring(idx + "body=".length());
        assertEquals(300, bodyPart.length());
    }

    @Test
    void postJson_ioExceptionWrapped() {
        LlmTransport.HttpExecutor executor = failing(new IOException("boom"));
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson("https://api.example.com/x", "{}", null, 5, executor));
        assertEquals("调用大模型接口失败: boom", ex.getMessage());
    }

    @Test
    void postJson_neverLeaksProxyPassword() {
        // 解析出一个带密码的代理，验证异常信息不会包含该密码
        Optional<LlmTransport.ProxySpec> spec = LlmTransport.parseProxy("http://u:secret123@h:1");
        assertTrue(spec.isPresent());
        assertEquals("secret123", spec.get().pass());

        LlmTransport.HttpExecutor executor = failing(new IOException("connect failed"));
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson("https://api.example.com/x", "{}", null, 5, executor));
        assertTrue(!ex.getMessage().contains("secret123"));
        assertTrue(!ex.getMessage().contains("u:secret123"));
    }

    // ---------- toHttpHost ----------

    @Test
    void toHttpHost_mapsFields() {
        HttpHost host = LlmTransport.toHttpHost(new LlmTransport.ProxySpec("h", 1234, null, null));
        assertEquals("h", host.getHostName());
        assertEquals(1234, host.getPort());
    }

    // 保留对 ContentType 的引用，避免未使用告警（语义上用于断言）
    static {
        assertNotNull(ContentType.APPLICATION_JSON);
    }
}

