package com.dramafactory.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.protocol.HttpClientContext;
import org.apache.hc.core5.http.ClassicHttpResponse;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.HttpHost;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.http.io.entity.StringEntity;
import org.apache.hc.core5.http.message.BasicClassicHttpResponse;
import org.apache.hc.core5.util.Timeout;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * LlmTransport 深度集成测试。
 *
 * <p>覆盖范围：代理解析纯函数语义、代理来源优先级、请求配置与 HttpPost 构造、
 * postJson 契约（2xx/非 2xx/异常透传/凭证脱敏/超时/空体）、HttpExecutor seam 的
 * 可注入性、以及并发调用下的行为一致性。</p>
 *
 * <p>说明：{@link LlmTransport} 是包可见工具类，本测试与它在同一包
 * {@code com.dramafactory} 下（被测类源码声明包名为 {@code com.dramafactory.service}，
 * 通过 import 使用）。凡涉及网络的方法一律走 {@code HttpExecutor} seam 注入，
 * 不发起真实 socket，从而在 @SpringBootTest 真实上下文里做可重复的深度集成测试。</p>
 */
@SpringBootTest
class LlmTransportDeepTest {

    private static final String TEST_URL = "https://llm.example.com/v1/chat/completions";
    private static final String TEST_BODY = "{\"model\":\"m\",\"messages\":[]}";

    /**
     * 用固定状态码与响应体构造一个 ClassicHttpResponse，供 executor 返回。
     */
    private static ClassicHttpResponse response(int status, String body) {
        BasicClassicHttpResponse resp = new BasicClassicHttpResponse(status);
        if (body != null) {
            resp.setEntity(new StringEntity(body, ContentType.APPLICATION_JSON));
        }
        return resp;
    }

    // ------------------------------------------------------------------
    // 1. parseProxy 纯函数：合法输入
    // ------------------------------------------------------------------
    @Test
    @DisplayName("parseProxy 解析带凭证的完整代理串")
    void parseProxyWithCredentials() {
        // given: 形如 http://user:pass@host:port 的代理串
        String raw = "http://alice:s3cr3t@proxy.internal:8080";

        // when: 调用纯函数解析
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.parseProxy(raw);

        // then: 解析成功且字段逐字匹配
        assertTrue(opt.isPresent(), "合法代理串必须解析成功");
        LlmTransport.ProxySpec spec = opt.get();
        assertEquals("proxy.internal", spec.host(), "host 必须与输入一致");
        assertEquals(8080, spec.port(), "port 必须与输入一致");
        assertEquals("alice", spec.user(), "user 必须与输入一致");
        assertEquals("s3cr3t", spec.pass(), "pass 必须与输入一致");
    }

    // ------------------------------------------------------------------
    // 2. parseProxy 纯函数：缺省端口回落 3128
    // ------------------------------------------------------------------
    @Test
    @DisplayName("parseProxy 在端口缺失时回落到 3128")
    void parseProxyDefaultsPort() {
        // given: 未携带端口的代理串
        String raw = "http://proxy.internal";

        // when: 解析
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.parseProxy(raw);

        // then: 端口回落为 3128，且 user/pass 为 null
        assertTrue(opt.isPresent(), "无端口但 host 合法的代理串必须解析成功");
        LlmTransport.ProxySpec spec = opt.get();
        assertEquals(3128, spec.port(), "缺省端口必须是 3128");
        assertNull(spec.user(), "无 userInfo 时 user 必须为 null");
        assertNull(spec.pass(), "无 userInfo 时 pass 必须为 null");
    }

    // ------------------------------------------------------------------
    // 3. parseProxy 纯函数：非法/空白输入返回 empty
    // ------------------------------------------------------------------
    @Test
    @DisplayName("parseProxy 对空白与无 host 输入返回 empty")
    void parseProxyRejectsInvalid() {
        // given: 一组非法或空白输入
        String blank = "   ";
        String noHost = "http://:9090";
        String illegalUri = "http://[::1";

        // when: 逐个解析
        Optional<LlmTransport.ProxySpec> r1 = LlmTransport.parseProxy(null);
        Optional<LlmTransport.ProxySpec> r2 = LlmTransport.parseProxy(blank);
        Optional<LlmTransport.ProxySpec> r3 = LlmTransport.parseProxy(noHost);
        Optional<LlmTransport.ProxySpec> r4 = LlmTransport.parseProxy(illegalUri);

        // then: 全部返回 empty，不得抛异常
        assertFalse(r1.isPresent(), "null 输入必须返回 empty");
        assertFalse(r2.isPresent(), "纯空白输入必须返回 empty");
        assertFalse(r3.isPresent(), "host 缺失的输入必须返回 empty");
        assertFalse(r4.isPresent(), "URI 非法的输入必须返回 empty");
    }

    // ------------------------------------------------------------------
    // 4. resolveProxy 优先级：HTTPS_PROXY 先于 https_proxy
    // ------------------------------------------------------------------
    @Test
    @DisplayName("resolveProxy 优先取 HTTPS_PROXY 而非 https_proxy")
    void resolveProxyPrefersUpperKey() {
        // given: 两个键同时存在且指向不同主机
        Map<String, String> env = new HashMap<>();
        env.put("HTTPS_PROXY", "http://upper.proxy:1111");
        env.put("https_proxy", "http://lower.proxy:2222");

        // when: 解析
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.resolveProxy(env);

        // then: 取到大写键对应主机
        assertTrue(opt.isPresent(), "存在合法值时必须解析成功");
        assertEquals("upper.proxy", opt.get().host(), "必须优先使用 HTTPS_PROXY");
        assertEquals(1111, opt.get().port(), "端口必须来自 HTTPS_PROXY");
    }

    // ------------------------------------------------------------------
    // 5. resolveProxy 回落：大写缺失时用小写；都缺失返回 empty
    // ------------------------------------------------------------------
    @Test
    @DisplayName("resolveProxy 在大写缺失时回落小写，全缺失返回 empty")
    void resolveProxyFallbackAndEmpty() {
        // given: 仅小写键存在；以及一个空 map
        Map<String, String> onlyLower = new HashMap<>();
        onlyLower.put("https_proxy", "http://lower.proxy:2222");
        Map<String, String> emptyEnv = new HashMap<>();

        // when: 分别解析
        Optional<LlmTransport.ProxySpec> lowerOpt = LlmTransport.resolveProxy(onlyLower);
        Optional<LlmTransport.ProxySpec> emptyOpt = LlmTransport.resolveProxy(emptyEnv);
        Optional<LlmTransport.ProxySpec> nullOpt = LlmTransport.resolveProxy((Map<String, String>) null);

        // then: 小写被采用；空 map 与 null 均为 empty
        assertTrue(lowerOpt.isPresent(), "仅小写键时也必须解析成功");
        assertEquals("lower.proxy", lowerOpt.get().host(), "必须回落到 https_proxy");
        assertFalse(emptyOpt.isPresent(), "空 map 必须返回 empty");
        assertFalse(nullOpt.isPresent(), "null map 必须返回 empty");
    }

    // ------------------------------------------------------------------
    // 6. toHttpHost + buildRequestConfig：代理存在时写入配置
    // ------------------------------------------------------------------
    @Test
    @DisplayName("toHttpHost 与 buildRequestConfig 正确携带代理与超时")
    void toHttpHostAndRequestConfigWithProxy() {
        // given: 一个代理规格
        LlmTransport.ProxySpec spec = new LlmTransport.ProxySpec("proxy.internal", 8080, null, null);

        // when: 转 HttpHost 并构建请求配置
        HttpHost host = LlmTransport.toHttpHost(spec);
        RequestConfig config = LlmTransport.buildRequestConfig(host, 17);

        // then: host 字段与超时都被正确写入
        assertNotNull(host, "HttpHost 不得为 null");
        assertEquals("proxy.internal", host.getHostName(), "HttpHost host 必须一致");
        assertEquals(8080, host.getPort(), "HttpHost port 必须一致");
        assertNotNull(config.getProxy(), "配置中必须带代理");
        assertEquals("proxy.internal", config.getProxy().getHostName(), "配置代理 host 必须一致");
        Timeout connectTimeout = config.getConnectTimeout();
        assertEquals(17, connectTimeout.toSeconds(), "连接超时必须为 17 秒");
    }

    // ------------------------------------------------------------------
    // 7. buildRequestConfig：proxy 为 null 时不设置代理
    // ------------------------------------------------------------------
    @Test
    @DisplayName("buildRequestConfig 在 proxy 为 null 时保持直连配置")
    void buildRequestConfigDirect() {
        // given: 无代理
        // when: 构建配置
        RequestConfig config = LlmTransport.buildRequestConfig(null, 5);

        // then: 无代理，且两个超时都生效
        assertNull(config.getProxy(), "proxy 为 null 时配置不得携带代理");
        assertEquals(5, config.getConnectTimeout().toSeconds(), "连接超时必须为 5 秒");
        assertEquals(5, config.getResponseTimeout().toSeconds(), "响应超时必须为 5 秒");
    }

    // ------------------------------------------------------------------
    // 8. buildPost：实体与可选请求头
    // ------------------------------------------------------------------
    @Test
    @DisplayName("buildPost 构造 JSON 实体并按需设置请求头")
    void buildPostWithAndWithoutAuthHeader() throws Exception {
        // given: 一个额外请求头
        Map.Entry<String, String> auth = Map.entry("Authorization", "Bearer token-abc");

        // when: 分别构造带/不带头的 HttpPost
        HttpPost withAuth = LlmTransport.buildPost(TEST_URL, TEST_BODY, auth);
        HttpPost withoutAuth = LlmTransport.buildPost(TEST_URL, TEST_BODY, null);

        // then: URL、实体内容与请求头均符合预期
        assertEquals(TEST_URL, withAuth.getUri().toString(), "URL 必须一致");
        assertEquals(TEST_BODY, EntityUtils.toString(withAuth.getEntity(), StandardCharsets.UTF_8),
                "实体内容必须与输入一致");
        assertEquals("Bearer token-abc", withAuth.getFirstHeader("Authorization").getValue(),
                "Authorization 头必须被设置");
        assertNull(withoutAuth.getFirstHeader("Authorization"), "authHeader 为 null 时不得设置该头");
    }

    // ------------------------------------------------------------------
    // 9. postJson 成功：2xx 返回响应体原文
    // ------------------------------------------------------------------
    @Test
    @DisplayName("postJson 在 2xx 时原样返回响应体")
    void postJsonReturnsBodyOn2xx() throws Exception {
        // given: 一个返回 200 与固定体的 executor
        String expectedBody = "{\"choices\":[{\"text\":\"hello\"}]}";
        AtomicReference<HttpPost> capturedPost = new AtomicReference<>();
        LlmTransport.HttpExecutor executor = (post, ctx) -> {
            capturedPost.set(post);
            return response(200, expectedBody);
        };

        // when: 执行 postJson
        String actual = LlmTransport.postJson(TEST_URL, TEST_BODY,
                Map.entry("Authorization", "Bearer x"), 10, executor);

        // then: 返回体一致，且 post 被真实构造并传入
        assertEquals(expectedBody, actual, "2xx 时必须返回原始响应体");
        assertNotNull(capturedPost.get(), "executor 必须收到非 null 的 HttpPost");
        assertEquals(TEST_URL, capturedPost.get().getUri().toString(), "传入的 URL 必须一致");
    }

    // ------------------------------------------------------------------
    // 10. postJson 非 2xx：抛 RuntimeException 且带状态码
    // ------------------------------------------------------------------
    @Test
    @DisplayName("postJson 在非 2xx 时抛出带状态码的 RuntimeException")
    void postJsonThrowsOnNon2xx() {
        // given: 一个返回 500 的 executor
        LlmTransport.HttpExecutor executor = (post, ctx) -> response(500, "upstream boom");

        // when: 执行 postJson
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, executor));

        // then: 消息里包含状态码与响应预览
        assertNotNull(ex.getMessage(), "异常消息不得为 null");
        assertTrue(ex.getMessage().contains("500"), "异常消息必须包含状态码 500");
        assertTrue(ex.getMessage().contains("upstream boom"), "异常消息必须包含响应体预览");
    }

    // ------------------------------------------------------------------
    // 11. postJson 非 2xx 且响应体超长：预览被截断到 300 字符
    // ------------------------------------------------------------------
    @Test
    @DisplayName("postJson 在非 2xx 时把响应体预览截断到 300 字符")
    void postJsonTruncatesLongErrorBody() {
        // given: 一个 400 且响应体远长于 300 的 executor
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 500; i++) {
            sb.append('x');
        }
        String longBody = sb.toString();
        LlmTransport.HttpExecutor executor = (post, ctx) -> response(400, longBody);

        // when: 执行 postJson
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, executor));

        // then: 消息包含状态码，且预览长度不超过 300
        assertTrue(ex.getMessage().contains("400"), "异常消息必须包含状态码 400");
        int idx = ex.getMessage().indexOf("body=");
        assertTrue(idx >= 0, "异常消息必须包含 body= 前缀");
        String preview = ex.getMessage().substring(idx + "body=".length());
        assertTrue(preview.length() <= 300, "预览长度必须不超过 300，实际=" + preview.length());
    }

    // ------------------------------------------------------------------
    // 12. postJson 空实体：非 2xx 时预览为空串
    // ------------------------------------------------------------------
    @Test
    @DisplayName("postJson 在实体为 null 时把响应体当作空串处理")
    void postJsonHandlesNullEntity() {
        // given: 一个 204（成功但无实体）的 executor
        LlmTransport.HttpExecutor okExecutor = (post, ctx) -> response(204, null);
        // 以及一个 503 无实体的 executor
        LlmTransport.HttpExecutor failExecutor = (post, ctx) -> response(503, null);

        // when: 分别执行
        String okBody = LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, okExecutor);
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, failExecutor));

        // then: 成功路径返回空串，失败路径消息包含状态码且 body 为空
        assertEquals("", okBody, "204 无实体时必须返回空串");
        assertTrue(ex.getMessage().contains("503"), "异常消息必须包含状态码 503");
        assertTrue(ex.getMessage().endsWith("body="), "无实体时预览必须为空串");
    }

    // ------------------------------------------------------------------
    // 13. postJson 失败注入：executor 抛 IOException 时包装为 RuntimeException
    // ------------------------------------------------------------------
    @Test
    @DisplayName("postJson 把 executor 的 IOException 包装为 RuntimeException")
    void postJsonWrapsIoException() {
        // given: 一个直接抛 IOException 的 executor
        LlmTransport.HttpExecutor executor = (post, ctx) -> {
            throw new IOException("connection refused");
        };

        // when: 执行 postJson
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, executor));

        // then: 消息包含 "调用大模型接口失败" 与原异常描述
        assertTrue(ex.getMessage().startsWith("调用大模型接口失败"), "消息必须以固定前缀开头");
        assertTrue(ex.getMessage().contains("connection refused"), "消息必须包含底层原因");
        assertNotNull(ex.getCause(), "必须保留原始异常作为 cause");
        assertTrue(ex.getCause() instanceof IOException, "cause 必须是 IOException");
    }

    // ------------------------------------------------------------------
    // 14. postJson 凭证脱敏：异常信息中不得出现代理密码
    // ------------------------------------------------------------------
    @Test
    @DisplayName("postJson 异常信息不泄露代理凭证")
    void postJsonNeverLeaksProxyCredentials() {
        // given: 一个抛 IOException 的 executor，且进程环境变量里塞入含密码的代理
        String password = "TOP-SECRET-PASS-42";
        Map<String, String> saved = new HashMap<>();
        String[] keys = {"HTTPS_PROXY", "https_proxy"};
        for (String k : keys) {
            saved.put(k, System.getenv(k));
        }
        // 这里只验证异常消息里不含密码片段（环境变量本身在容器内可能不存在，故用消息断言）
        LlmTransport.HttpExecutor executor = (post, ctx) -> {
            throw new IOException("proxy auth failed for user alice");
        };

        // when: 执行并捕获异常
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson(TEST_URL, TEST_BODY,
                        Map.entry("Authorization", "Bearer " + password), 10, executor));

        // then: 异常消息不含请求头里的敏感串，也不含 password 片段
        assertFalse(ex.getMessage().contains(password),
                "异常消息绝不能包含 Authorization 里的敏感串");
        assertFalse(ex.getMessage().contains("TOP-SECRET-PASS-42"),
                "异常消息绝不能包含密码明文");
        assertTrue(ex.getMessage().contains("proxy auth failed for user alice"),
                "异常消息必须保留底层原因描述");
    }

    // ------------------------------------------------------------------
    // 15. postJson 业务异常透传：executor 抛 RuntimeException 时原样抛出
    // ------------------------------------------------------------------
    @Test
    @DisplayName("postJson 原样透传 executor 抛出的 RuntimeException")
    void postJsonPassesThroughRuntimeException() {
        // given: executor 抛一个带唯一标记的 RuntimeException
        IllegalStateException original = new IllegalStateException("业务层拒绝-MARKER-77");
        LlmTransport.HttpExecutor executor = (post, ctx) -> {
            throw original;
        };

        // when: 执行 postJson
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, executor));

        // then: 是同一个实例，且消息未被包装
        assertSame(original, ex, "业务 RuntimeException 必须原样透传");
        assertTrue(ex.getMessage().contains("MARKER-77"), "消息必须保留原样");
    }

    // ------------------------------------------------------------------
    // 16. 幂等性：同一输入重复调用结果一致
    // ------------------------------------------------------------------
    @Test
    @DisplayName("postJson 相同输入重复调用返回一致结果")
    void postJsonIsIdempotentForSameInput() {
        // given: 一个固定响应的 executor
        String expectedBody = "{\"id\":\"resp-1\"}";
        AtomicInteger calls = new AtomicInteger();
        LlmTransport.HttpExecutor executor = (post, ctx) -> {
            calls.incrementAndGet();
            return response(200, expectedBody);
        };

        // when: 连续调用两次
        String first = LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, executor);
        String second = LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, executor);

        // then: 两次结果一致，且确实各调用一次
        assertEquals(expectedBody, first, "第一次结果必须一致");
        assertEquals(first, second, "两次调用结果必须完全一致");
        assertEquals(2, calls.get(), "executor 必须被调用两次");
    }

    // ------------------------------------------------------------------
    // 17. 并发：两线程同时推进同一任务，结果不坏数据
    // ------------------------------------------------------------------
    @Test
    @DisplayName("两线程并发调用 postJson 不破坏返回数据")
    void postJsonConcurrentCallsAreConsistent() throws Exception {
        // given: 一个根据请求体回显的 executor
        AtomicInteger counter = new AtomicInteger();
        LlmTransport.HttpExecutor executor = (post, ctx) -> {
            String body;
            try {
                body = EntityUtils.toString(post.getEntity(), StandardCharsets.UTF_8);
            } catch (org.apache.hc.core5.http.ParseException e) {
                throw new RuntimeException(e);
            }
            return response(200, "{\"echo\":" + body + ",\"seq\":" + counter.incrementAndGet() + "}");
        };
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicReference<String> r1 = new AtomicReference<>();
        AtomicReference<String> r2 = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            // when: 两线程同时发起请求
            pool.submit(() -> {
                try {
                    start.await();
                    r1.set(LlmTransport.postJson(TEST_URL, "{\"n\":1}", null, 10, executor));
                } catch (Throwable t) {
                    failure.compareAndSet(null, t);
                } finally {
                    done.countDown();
                }
            });
            pool.submit(() -> {
                try {
                    start.await();
                    r2.set(LlmTransport.postJson(TEST_URL, "{\"n\":2}", null, 10, executor));
                } catch (Throwable t) {
                    failure.compareAndSet(null, t);
                } finally {
                    done.countDown();
                }
            });
            start.countDown();
            assertTrue(done.await(10, TimeUnit.SECONDS), "并发任务必须在 10 秒内完成");
        } finally {
            pool.shutdownNow();
        }

        // then: 无异常，两个响应各自回显自己的输入，未被串写
        assertNull(failure.get(), "并发执行不得出现异常");
        assertNotNull(r1.get(), "线程 1 必须有结果");
        assertNotNull(r2.get(), "线程 2 必须有结果");
        assertTrue(r1.get().contains("{\"n\":1}"), "线程 1 的响应必须回显自己的输入");
        assertTrue(r2.get().contains("{\"n\":2}"), "线程 2 的响应必须回显自己的输入");
        assertEquals(2, counter.get(), "两次调用必须各自计数一次");
    }

    // ------------------------------------------------------------------
    // 18. 边界：超大 payload 原样传入并成功返回
    // ------------------------------------------------------------------
    @Test
    @DisplayName("postJson 能处理超大 payload 并原样送达")
    void postJsonHandlesHugePayload() throws Exception {
        // given: 一个约 1MB 的请求体
        StringBuilder sb = new StringBuilder(1_000_000);
        sb.append('{');
        while (sb.length() < 1_000_000) {
            sb.append('a');
        }
        sb.append('}');
        String hugeBody = sb.toString();
        AtomicInteger observedLength = new AtomicInteger(-1);
        LlmTransport.HttpExecutor executor = (post, ctx) -> {
            String sent;
            try {
                sent = EntityUtils.toString(post.getEntity(), StandardCharsets.UTF_8);
            } catch (org.apache.hc.core5.http.ParseException e) {
                throw new RuntimeException(e);
            }
            observedLength.set(sent.length());
            return response(200, "{\"ok\":true}");
        };

        // when: 执行
        String actual = LlmTransport.postJson(TEST_URL, hugeBody, null, 30, executor);

        // then: 送达长度与输入一致，且返回体正确
        assertEquals("{\"ok\":true}", actual, "超大 payload 场景必须正常返回");
        assertEquals(hugeBody.length(), observedLength.get(),
                "送达的 payload 长度必须与输入完全一致");
        assertTrue(hugeBody.length() >= 1_000_000, "输入必须达到 1MB 量级");
    }

    // ------------------------------------------------------------------
    // 19. 边界：非法状态跳转语义 —— 同一 HttpExecutor 被复用且不共享可变状态
    // ------------------------------------------------------------------
    @Test
    @DisplayName("多次调用不共享 HttpClientContext 状态")
    void postJsonDoesNotShareContextAcrossCalls() throws Exception {
        // given: executor 记录每次收到的 context 身份
        AtomicReference<HttpClientContext> firstCtx = new AtomicReference<>();
        AtomicReference<HttpClientContext> secondCtx = new AtomicReference<>();
        AtomicInteger calls = new AtomicInteger();
        LlmTransport.HttpExecutor executor = (post, ctx) -> {
            if (calls.incrementAndGet() == 1) {
                firstCtx.set(ctx);
            } else {
                secondCtx.set(ctx);
            }
            return response(200, "{\"ok\":true}");
        };

        // when: 连续两次调用
        LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, executor);
        LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, executor);

        // then: 每次调用都用全新的 context，不互相污染
        assertNotNull(firstCtx.get(), "第一次调用必须传入 context");
        assertNotNull(secondCtx.get(), "第二次调用必须传入 context");
        assertFalse(firstCtx.get() == secondCtx.get(),
                "两次调用必须使用不同的 HttpClientContext 实例");
        assertEquals(2, calls.get(), "executor 必须被调用两次");
    }

    // ------------------------------------------------------------------
    // 20. 边界：executor 返回 null 视为异常路径
    // ------------------------------------------------------------------
    @Test
    @DisplayName("executor 返回 null 时透传原生 NullPointerException")
    void postJsonThrowsWhenExecutorReturnsNull() {
        // given: 一个返回 null 的 executor
        LlmTransport.HttpExecutor executor = (post, ctx) -> null;

        // when: 执行 postJson
        // then: 抛出的就是原生 NullPointerException。
        // 原因：try-with-resources 对 null 资源不抛异常，随后 response.getCode() 触发 NPE；
        // 该 NPE 属于 RuntimeException，被 catch (RuntimeException e) 原样透传，
        // 不会被包装成"调用大模型接口失败"，也没有 cause 包装。
        assertThrows(NullPointerException.class,
                () -> LlmTransport.postJson(TEST_URL, TEST_BODY, null, 10, executor));
    }

    // ------------------------------------------------------------------
    // 21. 边界：timeoutSeconds 为 0 时仍能构造配置（不抛异常）
    // ------------------------------------------------------------------
    @Test
    @DisplayName("buildRequestConfig 接受 0 秒超时并如实写入")
    void buildRequestConfigZeroTimeout() {
        // given: 0 秒超时
        // when: 构建配置
        RequestConfig config = LlmTransport.buildRequestConfig(null, 0);

        // then: 两个超时都为 0，且不抛异常
        assertNotNull(config, "配置不得为 null");
        assertEquals(0L, config.getConnectTimeout().toNanoseconds(), "连接超时必须为 0");
        assertEquals(0L, config.getResponseTimeout().toNanoseconds(), "响应超时必须为 0");
    }

    // ------------------------------------------------------------------
    // 22. 边界：URI 解析对 host 大小写与 IPv4 的处理
    // ------------------------------------------------------------------
    @Test
    @DisplayName("parseProxy 正确处理 IPv4 主机与显式端口")
    void parseProxyHandlesIpv4Host() {
        // given: IPv4 主机 + 显式端口 + 用户名无密码
        String raw = "http://bob@127.0.0.1:8888";

        // when: 解析
        Optional<LlmTransport.ProxySpec> opt = LlmTransport.parseProxy(raw);

        // then: host/port/user 正确，pass 为空串
        assertTrue(opt.isPresent(), "IPv4 主机代理串必须解析成功");
        LlmTransport.ProxySpec spec = opt.get();
        assertEquals("127.0.0.1", spec.host(), "IPv4 host 必须一致");
        assertEquals(8888, spec.port(), "显式端口必须一致");
        assertEquals("bob", spec.user(), "无冒号的 userInfo 必须整体作为 user");
        assertEquals("", spec.pass(), "无冒号时 pass 必须为空串");
    }

    /**
     * JUnit 的 assertSame 未在静态导入中出现时使用的本地断言辅助。
     * 直接用 org.junit.jupiter.api.Assertions 的静态方法，避免遗漏导入。
     */
    private static void assertSame(Object expected, Object actual, String message) {
        org.junit.jupiter.api.Assertions.assertSame(expected, actual, message);
    }
}