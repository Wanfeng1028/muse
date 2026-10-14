
package com.dramafactory.service.video;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SurrogateAuthClient 单测：通过 SocketExchange 接缝注入桩，覆盖校验、通信、解析与提取分支。
 * 注意：surrogate 为敏感凭证，断言仅使用占位值，禁止打印密钥原文。
 */
class SurrogateAuthClientTest {

    /** 合法 host（白名单内）。 */
    private static final String ALLOWED_URL = "https://chatapi.weixin.qq.com/openai/v1/chat/completions";

    private static SurrogateAuthClient client(SurrogateAuthClient.SocketExchange ex) {
        return new SurrogateAuthClient(new ObjectMapper(), ex);
    }

    private static String okResponse(int status, String body) {
        return "HTTP/1.1 " + status + " OK\r\nContent-Type: application/json\r\n\r\n" + body;
    }

    private static String bearerBody() {
        return "{\"credentials\":[{\"surrogate\":\"surr-abc\",\"placement\":\"bearer_header\"}]}";
    }

    private static String customBody() {
        return "{\"credentials\":[{\"surrogate\":\"surr-xyz\",\"placement\":{\"custom_header\":\"X-Api-Key\"}}]}";
    }

    // ==================== A. authHeader 校验分支 ====================

    @Test
    void authHeaderShouldRejectNullUrl() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, bearerBody()));
        assertThrows(IllegalArgumentException.class, () -> c.authHeader(null));
    }

    @Test
    void authHeaderShouldRejectBlankUrl() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, bearerBody()));
        assertThrows(IllegalArgumentException.class, () -> c.authHeader("   "));
    }

    @Test
    void authHeaderShouldRejectBlankCredentialName() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, bearerBody()));
        assertThrows(IllegalArgumentException.class, () -> c.authHeader(ALLOWED_URL, "  "));
    }

    @Test
    void authHeaderShouldRejectUnparsableUrl() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, bearerBody()));
        assertThrows(IllegalArgumentException.class, () -> c.authHeader("://missing-host"));
    }

    @Test
    void authHeaderShouldRejectHostNotInWhitelist() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, bearerBody()));
        assertThrows(IllegalArgumentException.class, () -> c.authHeader("https://evil.com/x"));
    }

    @Test
    void authHeaderShouldReturnBearerHeaderForDefaultCredential() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, bearerBody()));
        Map.Entry<String, String> entry = c.authHeader(ALLOWED_URL);
        assertEquals("Authorization", entry.getKey());
        assertEquals("Bearer surr-abc", entry.getValue());
    }

    // ==================== B. requestSurrogateHeader 分支 ====================

    @Test
    void requestSurrogateHeaderShouldWrapIoException() {
        SurrogateAuthClient c = client((p, n) -> {
            throw new IOException("boom");
        });
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> c.authHeader(ALLOWED_URL));
        assertEquals("与 authd 通信失败", ex.getMessage());
    }

    @Test
    void requestSurrogateHeaderShouldRejectNon200Status() {
        SurrogateAuthClient c = client((p, n) -> okResponse(500, bearerBody()));
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> c.authHeader(ALLOWED_URL));
        assertTrue(ex.getMessage().contains("非 200"), "实际消息: " + ex.getMessage());
    }

    @Test
    void requestSurrogateHeaderShouldReturnCustomHeader() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, customBody()));
        Map.Entry<String, String> entry = c.authHeader(ALLOWED_URL);
        assertEquals("X-Api-Key", entry.getKey());
        assertEquals("surr-xyz", entry.getValue());
    }

    // ==================== C. parseHttpResponse 分支 ====================

    @Test
    void parseHttpResponseShouldRejectMissingSeparator() {
        SurrogateAuthClient c = client((p, n) -> "HTTP/1.1 200 OK" + bearerBody());
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> c.authHeader(ALLOWED_URL));
        assertTrue(ex.getMessage().contains("缺少头体分隔符"), "实际消息: " + ex.getMessage());
    }

    @Test
    void parseHttpResponseShouldRejectInvalidStatusLine() {
        SurrogateAuthClient c = client((p, n) -> "NOTASTATUSLINE\r\n\r\n{}");
        assertThrows(IllegalStateException.class, () -> c.authHeader(ALLOWED_URL));
    }

    @Test
    void parseHttpResponseShouldRejectNonNumericStatusCode() {
        SurrogateAuthClient c = client((p, n) -> "HTTP/1.1 ABC OK\r\n\r\n{}");
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> c.authHeader(ALLOWED_URL));
        assertTrue(ex.getMessage().contains("状态码无法解析"), "实际消息: " + ex.getMessage());
    }

    @Test
    void parseHttpResponseShouldPassBodyThrough() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, bearerBody()));
        Map.Entry<String, String> entry = c.authHeader(ALLOWED_URL);
        assertEquals("Authorization", entry.getKey());
        assertEquals("Bearer surr-abc", entry.getValue());
    }

    // ==================== D. extractHeader 分支 ====================

    @Test
    void extractHeaderShouldRejectInvalidJson() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, "{not json"));
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> c.authHeader(ALLOWED_URL));
        assertTrue(ex.getMessage().contains("JSON 解析失败"), "实际消息: " + ex.getMessage());
    }

    @Test
    void extractHeaderShouldRejectCredentialsNotArray() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, "{\"credentials\":{}}"));
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> c.authHeader(ALLOWED_URL));
        assertTrue(ex.getMessage().contains("缺少 credentials 数组"), "实际消息: " + ex.getMessage());
    }

    @Test
    void extractHeaderShouldRejectEmptyCredentials() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200, "{\"credentials\":[]}"));
        assertThrows(IllegalStateException.class, () -> c.authHeader(ALLOWED_URL));
    }

    @Test
    void extractHeaderShouldRejectBlankSurrogate() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200,
                "{\"credentials\":[{\"surrogate\":\" \",\"placement\":\"bearer_header\"}]}"));
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> c.authHeader(ALLOWED_URL));
        assertTrue(ex.getMessage().contains("缺少 surrogate 值"), "实际消息: " + ex.getMessage());
    }

    @Test
    void extractHeaderShouldRejectUnsupportedPlacement() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200,
                "{\"credentials\":[{\"surrogate\":\"s\",\"placement\":\"weird\"}]}"));
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> c.authHeader(ALLOWED_URL));
        assertTrue(ex.getMessage().contains("placement 格式不受支持"), "实际消息: " + ex.getMessage());
    }

    @Test
    void extractHeaderShouldRejectMissingCustomHeader() {
        SurrogateAuthClient c = client((p, n) -> okResponse(200,
                "{\"credentials\":[{\"surrogate\":\"s\",\"placement\":{}}]}"));
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> c.authHeader(ALLOWED_URL));
        assertTrue(ex.getMessage().contains("缺少 custom_header"), "实际消息: " + ex.getMessage());
    }
}
