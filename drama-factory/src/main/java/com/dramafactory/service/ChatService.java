package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.service.video.SurrogateAuthClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * AI 对话服务：控制台"AI 对话"页的后端。
 *
 * <p>调用微信 ChatAPI（DeepSeek-v4-flash，OpenAI 兼容接口）做剧本创作/改写、
 * 分镜拆解对话、提示词优化。鉴权走代理凭证 {@code custom.weixin-chatapi}，
 * 密钥不进仓库、不打日志；前端需明确提示用户"对话会消耗 DeepSeek API 额度"。</p>
 *
 * <p>无状态设计：多轮历史由前端随请求带来（最近 N 轮），后端不存会话。</p>
 */
@Service
public class ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);

    /** 微信 ChatAPI 的 OpenAI 兼容对话补全地址。 */
    private static final String CHAT_URL = "https://chatapi.weixin.qq.com/openai/v1/chat/completions";

    /** 代理鉴权使用的凭证标识。 */
    private static final String CREDENTIAL = "custom.weixin-chatapi";

    /** 随请求带来的历史轮数上限，防止 token 失控。 */
    private static final int MAX_HISTORY = 12;

    /**
     * 编剧助手系统提示词（由 DeepSeek 起草，见 docs）。
     * 约束模型：分镜输出必须附 ```json {"shots": [...]} 代码块，景别/运镜只用中文标签。
     */
    private static final String SYSTEM_PROMPT =
            "你是「AI 短剧工坊」的资深短剧编剧兼分镜师，服务对象是短剧创作者。你的语气专业、简洁、直接给可执行方案，不说空话套话。"
                    + "你的能力范围包括：1. 剧本创作、改写、润色（人设、冲突、钩子、反转、台词节奏）；"
                    + "2. 将剧本拆解为结构化分镜脚本；3. 优化视频生成提示词（videoPrompt）；"
                    + "4. 解答短剧制作相关问题（节奏、爽点、卡点、平台适配等）。"
                    + "超出上述范围的请求（如法律、医疗、投资、代写论文等），礼貌说明不在职责内并引导回短剧创作。"
                    + "当用户要求「拆分镜 / 拆解 / 分镜化」时，除简要文字说明外，必须另附一个 ```json 代码块，格式为 {\"shots\": [...]}。"
                    + "每个分镜字段：shotNo（整数，从1开始）、shotSize（只能是「特写、近景、中景、全景、远景」之一）、"
                    + "cameraMove（只能是「固定机位、推镜头、拉镜头、摇镜头、移镜头、跟镜头、升降」之一）、"
                    + "description（画面描述，40–80字，具体可拍，含人物动作与场景信息）、durationSeconds（整数秒，3–8）、"
                    + "dialogue（该镜对白，可为空字符串）、videoPrompt（英文视频生成提示词，一句话，包含镜头语言）。"
                    + "JSON 代码块内只放纯 JSON，不加注释、不加多余文字。"
                    + "硬性要求：每个镜头的画面必须有明显区别，禁止连续多镜使用同一场景与同一机位景别；景别与运镜要形成节奏变化。"
                    + "当用户说「调整第N镜……」时，在保留其余镜头的前提下修改该镜，并重新输出完整更新后的 ```json 代码块。";

    private final SurrogateAuthClient surrogateAuthClient;
    private final ObjectMapper objectMapper;
    private final String model;
    private final int maxTokens;

    public ChatService(SurrogateAuthClient surrogateAuthClient,
                       ObjectMapper objectMapper,
                       @Value("${drama.chat.model:Deepseek-v4-flash}") String model,
                       @Value("${drama.chat.max-tokens:2000}") int maxTokens) {
        this.surrogateAuthClient = surrogateAuthClient;
        this.objectMapper = objectMapper;
        this.model = model;
        this.maxTokens = maxTokens;
    }

    /**
     * 一轮对话：system + 历史 + 本轮用户消息 → 模型回复。
     *
     * @param request 对话请求
     * @return 对话响应（回复正文 + 实际使用的模型）
     */
    public Records.ChatResponse chat(Records.ChatRequest request) {
        String message = request.message();
        if (message == null || message.isBlank()) {
            throw new IllegalArgumentException("消息内容不能为空");
        }
        if (message.length() > 4000) {
            throw new IllegalArgumentException("单轮消息过长（限 4000 字）");
        }

        ArrayNode messages = objectMapper.createArrayNode();
        messages.add(systemMessage());
        List<Records.ChatMessage> history = request.history();
        if (history != null && !history.isEmpty()) {
            int from = Math.max(0, history.size() - MAX_HISTORY);
            for (int i = from; i < history.size(); i++) {
                Records.ChatMessage h = history.get(i);
                if (h == null || h.content() == null || h.content().isBlank()) {
                    continue;
                }
                String role = "assistant".equals(h.role()) ? "assistant" : "user";
                messages.add(textMessage(role, h.content()));
            }
        }
        messages.add(textMessage("user", message));

        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", model);
        body.set("messages", messages);
        body.put("max_tokens", maxTokens);
        body.put("temperature", 0.7);

        String reply = callModel(body);
        log.info("AI 对话完成，model={}，回复长度={}", model, reply.length());
        return new Records.ChatResponse(reply, model);
    }

    private ObjectNode systemMessage() {
        return textMessage("system", SYSTEM_PROMPT);
    }

    private ObjectNode textMessage(String role, String content) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("role", role);
        node.put("content", content);
        return node;
    }

        /**
     * 调用微信 ChatAPI，返回 choices[0].message.content。
     *
     * <p>传输层走 {@link LlmTransport}（Apache HttpClient 5，预先代理认证），
     * 原因见该类 JavaDoc。鉴权头经代理注入，不打印凭证。</p>
     */
    private String callModel(ObjectNode body) {
        String json = body.toString();
        Map.Entry<String, String> authHeader =
                surrogateAuthClient.authHeader(CHAT_URL, CREDENTIAL);
        return LlmTransport.postJson(CHAT_URL, json, authHeader, 90);
    }

}
