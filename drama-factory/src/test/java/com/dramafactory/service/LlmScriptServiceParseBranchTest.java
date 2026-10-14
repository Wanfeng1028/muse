
// LlmScriptService.parseChatResponse/textOrNull 分支覆盖（v2.14）
package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.*;

class LlmScriptServiceParseBranchTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    private LlmScriptService svc() {
        return new LlmScriptService(null, objectMapper, true, "test-model", 3000, 120, 2, null,
                new DramaMetrics(new SimpleMeterRegistry(), null, null));
    }

    @Test
    void parse_nullBody_throws() {
        LlmScriptService service = svc();
        LlmScriptUnavailableException ex = assertThrows(LlmScriptUnavailableException.class,
                () -> service.parseChatResponse(null));
        assertTrue(ex.getMessage().contains("AI 返回为空"),
                "异常消息应包含 'AI 返回为空'，实际为: " + ex.getMessage());
    }

    @Test
    void parse_blankBody_throws() {
        LlmScriptService service = svc();
        LlmScriptUnavailableException ex = assertThrows(LlmScriptUnavailableException.class,
                () -> service.parseChatResponse(" "));
        assertTrue(ex.getMessage().contains("AI 返回为空"),
                "异常消息应包含 'AI 返回为空'，实际为: " + ex.getMessage());
    }

    @Test
    void parse_nonJson_passthrough() {
        LlmScriptService service = svc();
        LlmScriptService.ModelCallResult result = service.parseChatResponse("hello");
        assertEquals("hello", result.content());
        assertEquals(0L, result.promptTokens());
        assertEquals(0L, result.completionTokens());
    }

    @Test
    void parse_emptyChoices_fallback() {
        LlmScriptService service = svc();
        String body = "{\"choices\":[]}";
        LlmScriptService.ModelCallResult result = service.parseChatResponse(body);
        assertEquals(body, result.content());
        assertEquals(0L, result.promptTokens());
        assertEquals(0L, result.completionTokens());
    }

    @Test
    void parse_nullContent_fallback() {
        LlmScriptService service = svc();
        String body = "{\"choices\":[{\"message\":{}}]}";
        LlmScriptService.ModelCallResult result = service.parseChatResponse(body);
        assertEquals(body, result.content());
        assertEquals(0L, result.promptTokens());
        assertEquals(0L, result.completionTokens());
    }

    @Test
    void parse_withUsage() {
        LlmScriptService service = svc();
        String body = "{\"choices\":[{\"message\":{\"content\":\"c\"}}],"
                + "\"usage\":{\"prompt_tokens\":5,\"completion_tokens\":7}}";
        LlmScriptService.ModelCallResult result = service.parseChatResponse(body);
        assertEquals("c", result.content());
        assertEquals(5L, result.promptTokens());
        assertEquals(7L, result.completionTokens());
    }

    @Test
    void textOrNull_missingField_returnsNull() throws Exception {
        JsonNode node = objectMapper.readTree("{\"a\":\"x\"}");
        Method m = LlmScriptService.class.getDeclaredMethod("textOrNull", JsonNode.class, String.class);
        m.setAccessible(true);
        Object result = m.invoke(null, node, "missing");
        assertNull(result);
    }

    @Test
    void textOrNull_explicitNull_returnsNull() throws Exception {
        JsonNode node = objectMapper.readTree("{\"a\":null}");
        Method m = LlmScriptService.class.getDeclaredMethod("textOrNull", JsonNode.class, String.class);
        m.setAccessible(true);
        Object result = m.invoke(null, node, "a");
        assertNull(result);
    }
}
