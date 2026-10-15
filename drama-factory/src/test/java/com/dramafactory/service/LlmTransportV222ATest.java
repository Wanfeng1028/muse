package com.dramafactory.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.http.message.BasicClassicHttpResponse;
import org.apache.hc.core5.http.io.support.ClassicResponseBuilder;
import org.junit.jupiter.api.Test;

/**
 * LlmTransport 补覆盖测试（针对 jacoco missed-branch 清单）。
 *
 * 诚实跳过清单（经源码级论证不可达，不写测试）：
 * 1) L250 4参 postJson 的 `catch (Exception e)` 通用包装臂：
 *    4参 try 块内调用的 resolveProxy()/toHttpHost()/buildRequestConfig()/HttpClients.custom().build()
 *    以及5参 postJson 均不声明受检异常；5参内部已把受检异常包装成 RuntimeException。
 *    故 4参 try 块不可能抛出非 RuntimeException 的受检异常，该臂不可达。
 * 2) L273 4参 postJson finally 内 `client.close()` 抛异常的 catch：
 *    client 是方法内通过 HttpClients.custom().build() 真实构建的 CloseableHttpClient，
 *    无任何注入点，测试无法让其在 close() 时抛异常，该臂不可达。
 *    （finally 内 `if (client != null)` 的 client==null 跳过臂由 url=null 用例覆盖。）
 */
class LlmTransportV222ATest {

    // ---------- L70：parseProxy 的 null 臂 / blank 臂 ----------

    @Test
    void parseProxy_nullRawReturnsEmpty() {
        Optional<LlmTransport.ProxySpec> result = LlmTransport.parseProxy(null);
        assertTrue(result.isEmpty());
    }

    @Test
    void parseProxy_blankRawReturnsEmpty() {
        Optional<LlmTransport.ProxySpec> result = LlmTransport.parseProxy("   \t  ");
        assertTrue(result.isEmpty());
    }

    // ---------- L80：URI.create 抛 IllegalArgumentException 的 catch 臂 ----------

    @Test
    void parseProxy_invalidUriWithSpaceReturnsEmpty() {
        Optional<LlmTransport.ProxySpec> result = LlmTransport.parseProxy("http://exa mple.com");
        assertTrue(result.isEmpty());
    }

    // ---------- L100：port<=0 默认 3128 臂 ----------

    @Test
    void parseProxy_noPortDefaultsTo3128() {
        Optional<LlmTransport.ProxySpec> result = LlmTransport.parseProxy("http://user:pass@proxy.example.com");
        assertTrue(result.isPresent());
        LlmTransport.ProxySpec spec = result.get();
        assertEquals("proxy.example.com", spec.host());
        assertEquals(3128, spec.port());
        assertEquals("user", spec.user());
        assertEquals("pass", spec.pass());
    }

    // ---------- L110：resolveProxy 第一个 key 解析失败、继续试第二个 key 臂 ----------

    @Test
    void resolveProxy_firstKeyUnparsableFallsBackToSecondKey() {
        Map<String, String> env = new HashMap<>();
        env.put("HTTPS_PROXY", "http://exa mple.com");
        env.put("https_proxy", "http://ok:3128");
        Optional<LlmTransport.ProxySpec> result = LlmTransport.resolveProxy(env);
        assertTrue(result.isPresent());
        LlmTransport.ProxySpec spec = result.get();
        assertEquals("ok", spec.host());
        assertEquals(3128, spec.port());
        assertNull(spec.user());
        assertNull(spec.pass());
    }

    // ---------- L178：200 + entity 为 null → 返回 "" ----------

    @Test
    void postJson_successWithNullEntityReturnsEmptyString() {
        LlmTransport.HttpExecutor executor =
                (post, ctx) -> ClassicResponseBuilder.create(200).build();
        String body = LlmTransport.postJson("https://api.example.com/v1", "{}", null, 5, executor);
        assertEquals("", body);
    }

    // ---------- L182：status<200 臂（199） ----------

    @Test
    void postJson_statusBelow200Throws() {
        LlmTransport.HttpExecutor executor =
                (post, ctx) -> ClassicResponseBuilder.create(199)
                        .setEntity("early hints", ContentType.TEXT_PLAIN).build();
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson("https://api.example.com/v1", "{}", null, 5, executor));
        assertEquals("大模型接口返回非 2xx: 199, body=early hints", ex.getMessage());
    }

    // ---------- L183：非 2xx + 超长 body 的截断臂（preview 恰好 300 字符） ----------

    @Test
    void postJson_non2xxTruncatesLongBodyToExactly300Chars() {
        String longBody = "x".repeat(400);
        LlmTransport.HttpExecutor executor =
                (post, ctx) -> ClassicResponseBuilder.create(500)
                        .setEntity(longBody, ContentType.TEXT_PLAIN).build();
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> LlmTransport.postJson("https://api.example.com/v1", "{}", null, 5, executor));
        String expected = "大模型接口返回非 2xx: 500, body=" + "x".repeat(300);
        assertEquals(expected, ex.getMessage());
    }

    // ---------- L215 + L230 + L273(client==null 跳过臂)：url=null → NPE 透传 ----------

    @Test
    void postJson_fourArgWithNullUrlPropagatesNpeUnwrapped() {
        NullPointerException npe = assertThrows(NullPointerException.class,
                () -> LlmTransport.postJson(null, "{}", null, 5));
        // 断言就是 NPE 本体，未被包装成 RuntimeException("调用大模型接口失败: ...")
        assertNotNull(npe);
        assertInstanceOf(NullPointerException.class, npe);
    }

    // ---------- 补充：确认 5参 postJson 对 RuntimeException 的重抛臂（L215）走通 ----------

    @Test
    void postJson_fiveArgRuntimeExceptionFromExecutorIsRethrownAsSameInstance() {
        IllegalStateException original = new IllegalStateException("boom-from-executor");
        LlmTransport.HttpExecutor executor = (post, ctx) -> {
            throw original;
        };
        IllegalStateException thrown = assertThrows(IllegalStateException.class,
                () -> LlmTransport.postJson("https://api.example.com/v1", "{}", null, 5, executor));
        assertSame(original, thrown);
        assertEquals("boom-from-executor", thrown.getMessage());
    }

    // ---------- 补充：BasicClassicHttpResponse 真实路径的 200 正常返回 ----------

    @Test
    void postJson_successWithTextEntityReturnsBody() throws Exception {
        BasicClassicHttpResponse response = new BasicClassicHttpResponse(200);
        response.setEntity(new org.apache.hc.core5.http.io.entity.StringEntity("hello-body", ContentType.TEXT_PLAIN));
        LlmTransport.HttpExecutor executor = (post, ctx) -> response;
        String body = LlmTransport.postJson("https://api.example.com/v1", "{}", null, 5, executor);
        assertEquals("hello-body", body);
        EntityUtils.consume(response.getEntity());
    }
}
