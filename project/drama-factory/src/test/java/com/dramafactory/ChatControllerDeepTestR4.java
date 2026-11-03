package com.dramafactory;

import com.dramafactory.controller.ChatController;
import com.dramafactory.dto.Records;
import com.dramafactory.service.ChatService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ChatControllerDeepTestR4 {

    private final ObjectMapper objectMapper = new ObjectMapper();

    private MockMvc buildMockMvc(ChatService chatService) {
        LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        return MockMvcBuilders.standaloneSetup(new ChatController(chatService))
                .setValidator(validator)
                .build();
    }

    @Test
    void chat_valid_returns200WithReply() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        when(chatService.chat(any(Records.ChatRequest.class)))
                .thenReturn(new Records.ChatResponse("你好，我是编剧助手", "Deepseek-v4-flash"));
        MockMvc mockMvc = buildMockMvc(chatService);

        Records.ChatRequest request = new Records.ChatRequest("写个开场", null, null);

        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reply").value("你好，我是编剧助手"))
                .andExpect(jsonPath("$.model").value("Deepseek-v4-flash"));
    }

    @Test
    void chat_withHistory_passesThrough() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        when(chatService.chat(any(Records.ChatRequest.class)))
                .thenReturn(new Records.ChatResponse("ok", "m"));
        MockMvc mockMvc = buildMockMvc(chatService);

        List<Records.ChatMessage> history = new ArrayList<>();
        history.add(new Records.ChatMessage("user", "第一句"));
        history.add(new Records.ChatMessage("assistant", "第二句"));
        Records.ChatRequest request = new Records.ChatRequest("继续写", null, history);

        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());

        ArgumentCaptor<Records.ChatRequest> captor = ArgumentCaptor.forClass(Records.ChatRequest.class);
        Mockito.verify(chatService, times(1)).chat(captor.capture());
        Records.ChatRequest captured = captor.getValue();
        assertEquals(2, captured.history().size());
        assertEquals("继续写", captured.message());
    }

    @Test
    void chat_withEpisodeId_passesThrough() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        when(chatService.chat(any(Records.ChatRequest.class)))
                .thenReturn(new Records.ChatResponse("ok", "m"));
        MockMvc mockMvc = buildMockMvc(chatService);

        Records.ChatRequest request = new Records.ChatRequest("写个开场", 42L, null);

        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());

        ArgumentCaptor<Records.ChatRequest> captor = ArgumentCaptor.forClass(Records.ChatRequest.class);
        Mockito.verify(chatService, times(1)).chat(captor.capture());
        assertEquals(42L, captor.getValue().episodeId());
    }

    @Test
    void chat_nullHistory_ok() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        when(chatService.chat(any(Records.ChatRequest.class)))
                .thenReturn(new Records.ChatResponse("ok", "m"));
        MockMvc mockMvc = buildMockMvc(chatService);

        Records.ChatRequest request = new Records.ChatRequest("写个开场", null, null);

        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());
    }

    @Test
    void chat_blankMessage_returns400() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        MockMvc mockMvc = buildMockMvc(chatService);

        Records.ChatRequest request = new Records.ChatRequest("", null, null);

        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void chat_nullMessage_returns400() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        MockMvc mockMvc = buildMockMvc(chatService);

        String json = "{\"episodeId\":7}";

        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest());
    }

    @Test
    void chat_missingBody_returns400() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        MockMvc mockMvc = buildMockMvc(chatService);

        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }

    @Test
    void chat_serviceThrows_propagatesAsServletException() {
        // 真实行为：standalone MockMvc 无 @ControllerAdvice，service 抛 RuntimeException 时
        // 包装为 jakarta.servlet.ServletException 抛出（而非 500 响应）
        ChatService chatService = Mockito.mock(ChatService.class);
        when(chatService.chat(any(Records.ChatRequest.class)))
                .thenThrow(new RuntimeException("llm down"));
        MockMvc mockMvc = buildMockMvc(chatService);

        Records.ChatRequest request = new Records.ChatRequest("写个开场", null, null);

        jakarta.servlet.ServletException thrown = org.junit.jupiter.api.Assertions.assertThrows(
                jakarta.servlet.ServletException.class,
                () -> mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request))));
        org.junit.jupiter.api.Assertions.assertTrue(
                thrown.getCause() instanceof RuntimeException
                        && "llm down".equals(thrown.getCause().getMessage()));
    }

    @Test
    void chat_wrongMethod_returns405() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        MockMvc mockMvc = buildMockMvc(chatService);

        mockMvc.perform(get("/api/chat"))
                .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void chat_wrongPath_returns404() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        MockMvc mockMvc = buildMockMvc(chatService);

        Records.ChatRequest request = new Records.ChatRequest("写个开场", null, null);

        mockMvc.perform(post("/api/chats")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isNotFound());
    }

    @Test
    void chat_replyContent_exactMatch() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        when(chatService.chat(any(Records.ChatRequest.class)))
                .thenReturn(new Records.ChatResponse("第一幕：雨夜，霓虹。", "Deepseek-v4-flash"));
        MockMvc mockMvc = buildMockMvc(chatService);

        Records.ChatRequest request = new Records.ChatRequest("写个开场", null, null);

        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reply").value("第一幕：雨夜，霓虹。"));
    }

    @Test
    void chat_verifyServiceCalledOnce() throws Exception {
        ChatService chatService = Mockito.mock(ChatService.class);
        when(chatService.chat(any(Records.ChatRequest.class)))
                .thenReturn(new Records.ChatResponse("ok", "m"));
        MockMvc mockMvc = buildMockMvc(chatService);

        Records.ChatRequest request = new Records.ChatRequest("写个开场", null, null);

        mockMvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());

        Mockito.verify(chatService, times(1)).chat(any(Records.ChatRequest.class));
    }
}