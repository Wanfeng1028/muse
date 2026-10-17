package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.service.ChatService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * ChatService 深测：消息收发、历史查询、参数校验。
 *
 * <p>ChatService 无状态、不落库，故本测试不依赖任何 repository。
 * 外部 LLM 调用通过包可见构造器注入 stub（modelCaller）隔离，杜绝真实网络。</p>
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:chatdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class ChatServiceDeepTest {

    @Autowired
    private ObjectMapper objectMapper;

    /** 捕获最近一次传给 modelCaller 的请求体，供断言使用。 */
    private List<String> capturedBodies;

    /** 可切换的 stub 返回内容。 */
    private String stubReply;

    private ChatService chatService;

    @BeforeEach
    void setUp() {
        capturedBodies = new ArrayList<>();
        stubReply = "好的，这是一个测试回复。";
        chatService = new ChatService(
                null,
                objectMapper,
                "Deepseek-v4-flash",
                2000,
                body -> {
                    capturedBodies.add(body.toString());
                    return stubReply;
                });
    }

    // ---------- 正常路径 ----------

    @Test
    void chat_returnsReplyAndModel() {
        Records.ChatRequest request = new Records.ChatRequest("帮我写一个开局钩子", null, List.of());
        Records.ChatResponse response = chatService.chat(request);

        assertNotNull(response, "响应不应为 null");
        assertEquals(stubReply, response.reply(), "回复正文应等于 stub 返回值");
        assertEquals("Deepseek-v4-flash", response.model(), "模型名应与构造注入一致");
    }

    @Test
    void chat_invokesModelCallerOnce() {
        Records.ChatRequest request = new Records.ChatRequest("讲个短剧点子", null, List.of());
        chatService.chat(request);

        assertEquals(1, capturedBodies.size(), "modelCaller 应被调用一次");
    }

    @Test
    void chat_requestBodyContainsModelAndParams() {
        Records.ChatRequest request = new Records.ChatRequest("写一段对白", null, List.of());
        chatService.chat(request);

        String body = capturedBodies.get(0);
        assertTrue(body.contains("Deepseek-v4-flash"), "请求体应包含模型名");
        assertTrue(body.contains("max_tokens"), "请求体应包含 max_tokens");
        assertTrue(body.contains("temperature"), "请求体应包含 temperature");
        assertTrue(body.contains("messages"), "请求体应包含 messages");
    }

    @Test
    void chat_includesSystemPromptInMessages() {
        Records.ChatRequest request = new Records.ChatRequest("拆分镜", null, List.of());
        chatService.chat(request);

        String body = capturedBodies.get(0);
        assertTrue(body.contains("system"), "messages 中应包含 system 角色");
        assertTrue(body.contains("AI 短剧工坊"), "system 提示词应包含固定文案片段");
    }

    @Test
    void chat_withHistory_keepsRecentTurns() {
        List<Records.ChatMessage> history = new ArrayList<>();
        history.add(new Records.ChatMessage("user", "第一轮提问"));
        history.add(new Records.ChatMessage("assistant", "第一轮回答"));
        Records.ChatRequest request = new Records.ChatRequest("第二轮提问", null, history);

        chatService.chat(request);

        String body = capturedBodies.get(0);
        assertTrue(body.contains("第一轮提问"), "历史 user 消息应被带上");
        assertTrue(body.contains("第一轮回答"), "历史 assistant 消息应被带上");
        assertTrue(body.contains("第二轮提问"), "本轮消息应被带上");
    }

    @Test
    void chat_withEmptyHistory_stillSucceeds() {
        Records.ChatRequest request = new Records.ChatRequest("没有历史", null, List.of());
        Records.ChatResponse response = chatService.chat(request);

        assertEquals(stubReply, response.reply(), "空历史也应正常返回");
    }

    @Test
    void chat_withNullHistory_stillSucceeds() {
        Records.ChatRequest request = new Records.ChatRequest("历史为 null", null, null);
        Records.ChatResponse response = chatService.chat(request);

        assertEquals(stubReply, response.reply(), "history 为 null 也应正常返回");
    }

    @Test
    void chat_skipsBlankHistoryEntries() {
        List<Records.ChatMessage> history = new ArrayList<>();
        history.add(new Records.ChatMessage("user", "有效历史"));
        history.add(new Records.ChatMessage("user", "   "));
        history.add(null);
        Records.ChatRequest request = new Records.ChatRequest("本轮", null, history);

        chatService.chat(request);

        String body = capturedBodies.get(0);
        assertTrue(body.contains("有效历史"), "有效历史应被带上");
    }

    // ---------- 参数非法 ----------

    @Test
    void chat_withNullMessage_throwsIllegalArgument() {
        Records.ChatRequest request = new Records.ChatRequest(null, null, List.of());
        assertThrows(IllegalArgumentException.class, () -> chatService.chat(request),
                "message 为 null 应抛 IllegalArgumentException");
    }

    @Test
    void chat_withBlankMessage_throwsIllegalArgument() {
        Records.ChatRequest request = new Records.ChatRequest("    ", null, List.of());
        assertThrows(IllegalArgumentException.class, () -> chatService.chat(request),
                "message 全空白应抛 IllegalArgumentException");
    }

    @Test
    void chat_withEmptyMessage_throwsIllegalArgument() {
        Records.ChatRequest request = new Records.ChatRequest("", null, List.of());
        assertThrows(IllegalArgumentException.class, () -> chatService.chat(request),
                "message 为空串应抛 IllegalArgumentException");
    }

    @Test
    void chat_messageOver4000_throwsIllegalArgument() {
        String tooLong = "a".repeat(4001);
        Records.ChatRequest request = new Records.ChatRequest(tooLong, null, List.of());
        assertThrows(IllegalArgumentException.class, () -> chatService.chat(request),
                "message 超过 4000 字应抛 IllegalArgumentException");
    }

    // ---------- 边界值 ----------

    @Test
    void chat_messageExactly4000_succeeds() {
        String boundary = "a".repeat(4000);
        Records.ChatRequest request = new Records.ChatRequest(boundary, null, List.of());
        Records.ChatResponse response = chatService.chat(request);

        assertEquals(stubReply, response.reply(), "恰好 4000 字应被接受");
    }

    @Test
    void chat_singleCharMessage_succeeds() {
        Records.ChatRequest request = new Records.ChatRequest("好", null, List.of());
        Records.ChatResponse response = chatService.chat(request);

        assertEquals(stubReply, response.reply(), "单字消息应被接受");
    }

    // ---------- 幂等 / 无状态 ----------

    @Test
    void chat_repeatedSameRequest_isIdempotentOnServiceState() {
        Records.ChatRequest request = new Records.ChatRequest("重复请求", null, List.of());
        Records.ChatResponse first = chatService.chat(request);
        Records.ChatResponse second = chatService.chat(request);

        assertEquals(first.reply(), second.reply(), "相同请求两次回复应一致");
        assertEquals(first.model(), second.model(), "相同请求两次模型应一致");
        assertEquals(2, capturedBodies.size(), "modelCaller 应被调用两次");
    }

    @Test
    void chat_historyTruncatedToMaxHistory() {
        List<Records.ChatMessage> history = new ArrayList<>();
        for (int i = 0; i < 20; i++) {
            history.add(new Records.ChatMessage("user", "历史消息" + i));
        }
        Records.ChatRequest request = new Records.ChatRequest("本轮", null, history);

        chatService.chat(request);

        String body = capturedBodies.get(0);
        assertTrue(body.contains("历史消息19"), "最近一条历史应被保留");
        assertTrue(body.contains("历史消息8"), "MAX_HISTORY=12 时第 8 条应仍在窗口内");
        assertTrue(!body.contains("历史消息0"), "过老的历史应被截断丢弃");
    }
}
