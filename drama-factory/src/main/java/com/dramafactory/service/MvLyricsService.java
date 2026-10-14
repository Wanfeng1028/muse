package com.dramafactory.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class MvLyricsService {

    private static final Logger log = LoggerFactory.getLogger(MvLyricsService.class);

    private final ObjectMapper objectMapper;
    private final LlmScriptService llmScriptService;

    public MvLyricsService(ObjectMapper objectMapper, LlmScriptService llmScriptService) {
        this.objectMapper = objectMapper;
        this.llmScriptService = llmScriptService;
    }

    public record LyricSection(String name, String lyrics, String mood, int estSeconds) {}

    public record LyricsResult(List<LyricSection> sections, String title, long promptTokens, long completionTokens) {}

    public LyricsResult generate(String theme, String mood, String style) {
        String systemPrompt = "你是资深作词人。只输出 JSON，不许输出其他文字。";

        StringBuilder user = new StringBuilder();
        user.append("主题：").append(theme == null ? "" : theme).append("\n");
        if (mood != null && !mood.isBlank()) {
            user.append("情绪：").append(mood).append("\n");
        }
        if (style != null && !style.isBlank()) {
            user.append("曲风：").append(style).append("\n");
        }
        user.append("\n请输出如下结构的 JSON：\n");
        user.append("{\"title\":\"歌名\",\"sections\":[{\"name\":\"verse1\",\"lyrics\":\"第一段歌词\",\"mood\":\"情绪标签\",\"estSeconds\":20}]}\n");
        user.append("要求：sections 4-6 段，name 取 verse1/chorus1/verse2/chorus2/bridge/outro 等，");
        user.append("每段 lyrics 为多行文本，estSeconds 为该段预估演唱秒数，全部段落合计 60-180 秒。");

        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", "deepseek-chat");
        ArrayNode messages = body.putArray("messages");
        messages.addObject().put("role", "system").put("content", systemPrompt);
        messages.addObject().put("role", "user").put("content", user.toString());
        body.put("temperature", 0.8);

        LlmScriptService.ModelCallResult callResult = llmScriptService.callModelWithUsage(body);
        String content = callResult.content();
        String json = stripFence(content);

        JsonNode root;
        try {
            root = objectMapper.readTree(json);
        } catch (Exception e) {
            log.warn("作词结果 JSON 解析失败: {}", e.getMessage());
            throw new IllegalStateException("作词结果解析失败");
        }

        String title = root.path("title").asText("");
        JsonNode sectionsNode = root.path("sections");
        if (!sectionsNode.isArray() || sectionsNode.isEmpty()) {
            throw new IllegalStateException("作词结果解析失败");
        }

        List<LyricSection> sections = new ArrayList<>();
        for (JsonNode n : sectionsNode) {
            String name = n.path("name").asText("");
            String lyrics = n.path("lyrics").asText("");
            String secMood = n.path("mood").asText("");
            int est = n.path("estSeconds").asInt(20);
            if (lyrics == null || lyrics.isBlank()) {
                throw new IllegalStateException("作词结果解析失败");
            }
            if (est < 5) {
                est = 5;
            } else if (est > 60) {
                est = 60;
            }
            sections.add(new LyricSection(name, lyrics, secMood, est));
        }

        return new LyricsResult(sections, title, callResult.promptTokens(), callResult.completionTokens());
    }

    public String toJson(LyricsResult r) {
        ObjectNode root = objectMapper.createObjectNode();
        root.put("title", r.title());
        ArrayNode arr = root.putArray("sections");
        for (LyricSection s : r.sections()) {
            ObjectNode o = arr.addObject();
            o.put("name", s.name());
            o.put("lyrics", s.lyrics());
            o.put("mood", s.mood());
            o.put("estSeconds", s.estSeconds());
        }
        try {
            return objectMapper.writeValueAsString(root);
        } catch (Exception e) {
            throw new IllegalStateException("作词结果序列化失败");
        }
    }

    private String stripFence(String content) {
        if (content == null) {
            return "";
        }
        String trimmed = content.trim();
        if (trimmed.startsWith("```")) {
            int firstNewline = trimmed.indexOf('\n');
            if (firstNewline >= 0) {
                trimmed = trimmed.substring(firstNewline + 1);
            }
            int lastFence = trimmed.lastIndexOf("```");
            if (lastFence >= 0) {
                trimmed = trimmed.substring(0, lastFence);
            }
        }
        return trimmed.trim();
    }
}
