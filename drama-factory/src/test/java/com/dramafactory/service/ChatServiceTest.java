package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.mock;

class ChatServiceTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private ChatService newService(Function<ObjectNode, String> stub) {
        return new ChatService(mock(CredentialResolver.class), new ObjectMapper(), "m1", 2000, stub);
    }

    private static Records.ChatMessage msg(String role, String content) {
        return new Records.ChatMessage(role, content);
    }

    private static String role(ArrayNode messages, int index) {
        return messages.get(index).get("role").asText();
    }

    private static String content(ArrayNode messages, int index) {
        return messages.get(index).get("content").asText();
    }

    @Test
    void t1_nullMessage_rejected() {
        ChatService service = newService(body -> "unused");
        Records.ChatRequest request = new Records.ChatRequest(null, null, null);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.chat(request));
        assertEquals(true, ex.getMessage().contains("消息内容不能为空"));
    }

    @Test
    void t2_blankMessage_rejected() {
        ChatService service = newService(body -> "unused");
        Records.ChatRequest request = new Records.ChatRequest(" ", null, null);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.chat(request));
        assertEquals(true, ex.getMessage().contains("消息内容不能为空"));
    }

    @Test
    void t3_tooLongMessage_rejected() {
        ChatService service = newService(body -> "unused");
        Records.ChatRequest request = new Records.ChatRequest("a".repeat(4001), null, null);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.chat(request));
        assertEquals(true, ex.getMessage().contains("单轮消息过长"));
    }

    @Test
    void t4_successPath_buildsBody() {
        final ObjectNode[] captured = new ObjectNode[1];
        Function<ObjectNode, String> stub = body -> {
            captured[0] = body;
            return "hello";
        };
        ChatService service = newService(stub);

        Records.ChatResponse response = service.chat(new Records.ChatRequest("hi", null, null));

        assertEquals("hello", response.reply());
        assertEquals("m1", response.model());

        ObjectNode body = captured[0];
        assertEquals("m1", body.get("model").asText());
        assertEquals(2000, body.get("max_tokens").asInt());
        assertEquals(0.7, body.get("temperature").asDouble(), 0.0001);

        ArrayNode messages = (ArrayNode) body.get("messages");
        assertEquals(2, messages.size());
        assertEquals("system", role(messages, 0));
        assertEquals("user", role(messages, 1));
        assertEquals("hi", content(messages, 1));
    }

    @Test
    void t5_historyTruncatedToLastTwelve() {
        final ObjectNode[] captured = new ObjectNode[1];
        Function<ObjectNode, String> stub = body -> {
            captured[0] = body;
            return "ok";
        };
        ChatService service = newService(stub);

        List<Records.ChatMessage> history = new ArrayList<>();
        for (int i = 0; i < 15; i++) {
            history.add(msg("user", "h" + i));
        }
        service.chat(new Records.ChatRequest("now", null, history));

        ArrayNode messages = (ArrayNode) captured[0].get("messages");
        assertEquals(14, messages.size());
        assertEquals("system", role(messages, 0));
        assertEquals("h3", content(messages, 1));
        assertEquals("now", content(messages, 13));
    }

    @Test
    void t6_nullAndBlankHistoryEntriesSkipped() {
        final ObjectNode[] captured = new ObjectNode[1];
        Function<ObjectNode, String> stub = body -> {
            captured[0] = body;
            return "ok";
        };
        ChatService service = newService(stub);

        List<Records.ChatMessage> history = new ArrayList<>();
        history.add(msg("user", "keep"));
        history.add(null);
        history.add(msg("user", "   "));
        history.add(msg("user", null));
        service.chat(new Records.ChatRequest("now", null, history));

        ArrayNode messages = (ArrayNode) captured[0].get("messages");
        assertEquals(3, messages.size());
        assertEquals("system", role(messages, 0));
        assertEquals("keep", content(messages, 1));
        assertEquals("now", content(messages, 2));
    }

    @Test
    void t7_roleNormalization() {
        final ObjectNode[] captured = new ObjectNode[1];
        Function<ObjectNode, String> stub = body -> {
            captured[0] = body;
            return "ok";
        };
        ChatService service = newService(stub);

        List<Records.ChatMessage> history = new ArrayList<>();
        history.add(msg("assistant", "a"));
        history.add(msg("moderator", "m"));
        history.add(msg(null, "n"));
        history.add(msg("user", "u"));
        service.chat(new Records.ChatRequest("now", null, history));

        ArrayNode messages = (ArrayNode) captured[0].get("messages");
        assertEquals(6, messages.size());
        assertEquals("assistant", role(messages, 1));
        assertEquals("user", role(messages, 2));
        assertEquals("user", role(messages, 3));
        assertEquals("user", role(messages, 4));
    }

    @Test
    void t8_stubExceptionPropagated() {
        RuntimeException boom = new RuntimeException("炸了");
        ChatService service = newService(body -> {
            throw boom;
        });
        RuntimeException thrown = assertThrows(RuntimeException.class,
                () -> service.chat(new Records.ChatRequest("hi", null, null)));
        assertSame(boom, thrown);
    }

    @Test
    void t9_emptyHistoryOnlySystemAndUser() {
        final ObjectNode[] captured = new ObjectNode[1];
        Function<ObjectNode, String> stub = body -> {
            captured[0] = body;
            return "ok";
        };
        ChatService service = newService(stub);
        service.chat(new Records.ChatRequest("hi", null, new ArrayList<>()));

        ArrayNode messages = (ArrayNode) captured[0].get("messages");
        assertEquals(2, messages.size());
        assertEquals("system", role(messages, 0));
        assertEquals("user", role(messages, 1));
    }

    @Test
    void t10_exactlyFourThousandCharsAccepted() {
        final ObjectNode[] captured = new ObjectNode[1];
        Function<ObjectNode, String> stub = body -> {
            captured[0] = body;
            return "ok";
        };
        ChatService service = newService(stub);
        String message = "a".repeat(4000);
        Records.ChatResponse response = service.chat(new Records.ChatRequest(message, null, null));

        assertEquals("ok", response.reply());
        ArrayNode messages = (ArrayNode) captured[0].get("messages");
        assertEquals(message, content(messages, messages.size() - 1));
    }
}
