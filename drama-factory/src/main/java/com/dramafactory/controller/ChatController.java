package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.ChatService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * AI 对话接口：控制台"AI 对话"页的后端。
 *
 * <p>普通 JSON 请求/响应，不做流式。调用微信 ChatAPI 的 DeepSeek 模型，
 * 会消耗用户的 DeepSeek API 额度，前端必须明确提示。</p>
 */
@RestController
@RequestMapping("/api")
public class ChatController {

    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    /**
     * 发送一轮对话。
     *
     * @param request 对话请求（含本轮消息与历史）
     * @return 模型回复
     */
    @PostMapping("/chat")
    public ResponseEntity<Records.ChatResponse> chat(
            @Valid @RequestBody Records.ChatRequest request) {
        return ResponseEntity.ok(chatService.chat(request));
    }
}
