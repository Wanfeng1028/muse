package com.dramafactory.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 章节事件抽取服务：把小说/故事原文按章节抽取为 {@link ChapterEvent} 列表。
 *
 * <p>只做抽取，不写库、不碰画布。请求走 OpenAI 兼容的 chat 接口，
 * 鉴权由 {@link CredentialResolver#chatAuth()} 提供。</p>
 */
@Service
public class ChapterEventService {

    private static final Logger log = LoggerFactory.getLogger(ChapterEventService.class);

    private static final String CHAT_URL = "https://chatapi.weixin.qq.com/openai/v1/chat/completions";

    private static final Pattern CHAPTER_HEADING = Pattern.compile("(?m)^[ \\t]*第[一二三四五六七八九十百千万\\d\\s]+[章节回][^\\n\\r]{0,40}");

    private static final String DEFAULT_MODEL = "Deepseek-v4-flash";
    private static final int DEFAULT_MAX_TOKENS = 4000;
    private static final int CHAPTER_BODY_MAX = 12000;

    /**
     * HTTP 调用接缝，便于单测替换。
     */
    @FunctionalInterface
    interface HttpExchange {
        HttpResponse<String> send(HttpRequest request) throws Exception;
    }

    /**
     * 切分后的章节标题与正文。
     */
    record ChapterTitle(String title, String body) {
    }

    private final CredentialResolver credentialResolver;
    private final ObjectMapper objectMapper;
    private final PromptFileService promptFileService;
    private final String model;
    private final int maxTokens;
    private final HttpExchange httpExchange;

    /**
     * Spring 注入用构造器，内部委托给全参构造器，并装配真实 HttpClient。
     */
    @Autowired
    public ChapterEventService(CredentialResolver credentialResolver,
                               ObjectMapper objectMapper,
                               PromptFileService promptFileService,
                               @Value("${drama.chapter-events.model:Deepseek-v4-flash}") String model,
                               @Value("${drama.chapter-events.max-tokens:4000}") int maxTokens) {
        this(credentialResolver, objectMapper, promptFileService, model, maxTokens, defaultExchange());
    }

    /**
     * 全参构造器（包可见），供单测注入 {@link HttpExchange} 接缝。
     */
    ChapterEventService(CredentialResolver credentialResolver,
                        ObjectMapper objectMapper,
                        PromptFileService promptFileService,
                        String model,
                        int maxTokens,
                        HttpExchange httpExchange) {
        this.credentialResolver = credentialResolver;
        this.objectMapper = objectMapper;
        this.promptFileService = promptFileService;
        this.model = (model == null || model.isBlank()) ? DEFAULT_MODEL : model;
        this.maxTokens = maxTokens <= 0 ? DEFAULT_MAX_TOKENS : maxTokens;
        this.httpExchange = httpExchange;
    }

    private static HttpExchange defaultExchange() {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();
        return request -> client.send(request, HttpResponse.BodyHandlers.ofString());
    }
    /**
     * 抽取原文全部章节的事件。
     *
     * @param novelText 小说/故事原文
     * @return 按章节顺序排列的事件列表
     */
    public List<ChapterEvent> extract(String novelText) {
        if (novelText == null || novelText.isBlank()) {
            throw new IllegalArgumentException("小说原文不能为空");
        }
        List<ChapterTitle> chapters = splitChapters(novelText);
        List<ChapterEvent> result = new ArrayList<>();
        for (int i = 0; i < chapters.size(); i++) {
            ChapterTitle chapter = chapters.get(i);
            int chapterIndex = i + 1;
            String content = callModel(chapter.title(), chapter.body());
            result.addAll(parseEvents(content, chapterIndex, chapter.title()));
        }
        return result;
    }

    /**
     * 按章节标题正则切分原文；无标题行时视为单章，标题为 "全文"。
     */
    static List<ChapterTitle> splitChapters(String text) {
        List<ChapterTitle> result = new ArrayList<>();
        if (text == null || text.isEmpty()) {
            return result;
        }
        Matcher matcher = CHAPTER_HEADING.matcher(text);
        List<int[]> headingRanges = new ArrayList<>();
        List<String> headingTitles = new ArrayList<>();
        while (matcher.find()) {
            headingRanges.add(new int[]{matcher.start(), matcher.end()});
            String raw = matcher.group();
            String title = raw.trim();
            if (title.length() > 40) {
                title = title.substring(0, 40);
            }
            headingTitles.add(title);
        }
        if (headingRanges.isEmpty()) {
            result.add(new ChapterTitle("全文", text));
            return result;
        }
        // 标题之前的引导文本，若有则作为序章
        int firstStart = headingRanges.get(0)[0];
        if (firstStart > 0) {
            String preamble = text.substring(0, firstStart);
            if (!preamble.isBlank()) {
                result.add(new ChapterTitle("序章", preamble));
            }
        }
        for (int i = 0; i < headingRanges.size(); i++) {
            int bodyStart = headingRanges.get(i)[1];
            int bodyEnd = (i + 1 < headingRanges.size()) ? headingRanges.get(i + 1)[0] : text.length();
            String body = text.substring(bodyStart, bodyEnd);
            result.add(new ChapterTitle(headingTitles.get(i), body));
        }
        return result;
    }

    private String callModel(String chapterTitle, String chapterText) {
        String system;
        try {
            system = promptFileService.render("chapter-events", Map.of("chapterTitle", chapterTitle));
        } catch (Exception e) {
            throw new RuntimeException("加载提示词 chapter-events 失败: " + e.getMessage());
        }
        String user = "【章节标题】\n" + chapterTitle + "\n【章节正文】\n" + truncate(chapterText, CHAPTER_BODY_MAX);

        Map<String, Object> payload = Map.of(
                "model", model,
                "messages", List.of(
                        Map.of("role", "system", "content", system),
                        Map.of("role", "user", "content", user)
                ),
                "max_tokens", maxTokens
        );

        String json;
        try {
            json = objectMapper.writeValueAsString(payload);
        } catch (Exception e) {
            throw new RuntimeException("构造请求体失败: " + e.getMessage());
        }

        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(CHAT_URL))
                .timeout(Duration.ofSeconds(90))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json));

        Map.Entry<String, String> auth = credentialResolver.chatAuth();
        if (auth != null) {
            builder.header(auth.getKey(), auth.getValue());
        }

        HttpResponse<String> response;
        try {
            response = httpExchange.send(builder.build());
        } catch (Exception e) {
            throw new RuntimeException("调用大模型失败: " + e.getMessage());
        }

        int status = response.statusCode();
        if (status < 200 || status >= 300) {
            String body = response.body();
            String snippet = body == null ? "" : (body.length() > 300 ? body.substring(0, 300) : body);
            throw new RuntimeException("调用大模型失败，状态码 " + status + "，响应: " + snippet);
        }

        try {
            JsonNode root = objectMapper.readTree(response.body());
            JsonNode content = root.path("choices").path(0).path("message").path("content");
            return content.isMissingNode() || content.isNull() ? "" : content.asText();
        } catch (Exception e) {
            throw new RuntimeException("解析大模型响应失败: " + e.getMessage());
        }
    }

    private List<ChapterEvent> parseEvents(String content, int chapterIndex, String chapterTitle) {
        String cleaned = stripCodeFence(content);
        JsonNode root;
        try {
            root = objectMapper.readTree(cleaned);
        } catch (Exception e) {
            throw new RuntimeException("解析大模型返回的 JSON 失败: " + e.getMessage());
        }
        if (root == null || !root.isArray()) {
            throw new RuntimeException("大模型返回的不是 JSON 数组");
        }
        if (root.isEmpty()) {
            throw new RuntimeException("大模型未抽取到任何事件");
        }
        List<ChapterEvent> events = new ArrayList<>();
        for (JsonNode node : root) {
            String coreEvent = textOf(node, "coreEvent");
            if (coreEvent.isBlank()) {
                continue;
            }
            String infoDensity = textOf(node, "infoDensity");
            if (!"高".equals(infoDensity) && !"中".equals(infoDensity) && !"低".equals(infoDensity)) {
                infoDensity = "";
            }
            events.add(new ChapterEvent(
                    chapterIndex,
                    chapterTitle,
                    stringList(node.path("characters")),
                    coreEvent,
                    textOf(node, "mainlineRelation"),
                    infoDensity,
                    intOf(node, "estimatedSeconds"),
                    textOf(node, "emotions")
            ));
        }
        return events;
    }

    private static String textOf(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (value.isMissingNode() || value.isNull()) {
            return "";
        }
        return value.asText("");
    }

    private static int intOf(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (value.isMissingNode() || value.isNull()) {
            return 0;
        }
        if (value.isNumber()) {
            return value.asInt(0);
        }
        try {
            return Integer.parseInt(value.asText().trim());
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private static List<String> stringList(JsonNode node) {
        if (node == null || node.isMissingNode() || node.isNull() || !node.isArray()) {
            return List.of();
        }
        List<String> list = new ArrayList<>();
        for (JsonNode item : node) {
            String v = item.asText("");
            if (!v.isBlank()) {
                list.add(v);
            }
        }
        return list;
    }

    /**
     * 去掉模型输出中可能存在的 ```json / ``` 围栏。
     */
    private static String stripCodeFence(String s) {
        if (s == null) {
            return "";
        }
        String trimmed = s.trim();
        if (!trimmed.startsWith("```")) {
            return trimmed;
        }
        int firstNewline = trimmed.indexOf('\n');
        if (firstNewline < 0) {
            return trimmed;
        }
        String inner = trimmed.substring(firstNewline + 1);
        int closing = inner.lastIndexOf("```");
        if (closing >= 0) {
            inner = inner.substring(0, closing);
        }
        return inner.trim();
    }

    private static String truncate(String s, int max) {
        if (s == null) {
            return "";
        }
        if (s.length() <= max) {
            return s;
        }
        return s.substring(0, max) + "\n…（后续内容已截断）";
    }
}