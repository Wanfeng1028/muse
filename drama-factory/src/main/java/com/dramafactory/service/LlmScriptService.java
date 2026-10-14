package com.dramafactory.service;

import com.dramafactory.model.Episode;
import com.fasterxml.jackson.databind.JsonNode;
import com.dramafactory.metrics.DramaMetrics;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * 真实大模型剧本生成服务（v2.3）。
 *
 * <p>调用微信 ChatAPI（DeepSeek-v4-flash，OpenAI 兼容接口）生成短剧剧本。
 * 若调用失败或返回格式无效，抛出 {@link LlmScriptUnavailableException}，
 * 由调用方降级为模板生成。密钥通过 {@link SurrogateAuthClient} 获取，
 * 绝不打印到日志。</p>
 */
@Service
public class LlmScriptService {

    private static final Logger log = LoggerFactory.getLogger(LlmScriptService.class);

    /** ChatAPI 端点（与 ChatService 保持一致）。 */
    private static final String CHAT_URL = "https://chatapi.weixin.qq.com/openai/v1/chat/completions";

    /** 鉴权凭据名（与 ChatService 保持一致）。 */
    private static final String CREDENTIAL = "custom.weixin-chatapi";

    private static final String SYSTEM_PROMPT = """
            你是资深短剧编剧。任务：根据用户给的项目信息创作恰好 4 场短剧剧本：
            1 开场钩子（前 3 秒抓人）、2 冲突升级、3 反转、4 高潮收尾。
            输出必须且只能是一个 JSON（可包在 ```json 代码块里），格式 {"scenes":[...]}，
            每场字段：
            - sceneNo（1-4 整数）
            - location（场景地点，8 字内）
            - timeOfDay（白天/黄昏/夜晚等）
            - description（画面描述 80-150 字，具体可拍，含人物动作与场景信息）
            - dialogue（对白，带人物名，口语化短句，可多行）
            - prompt（英文视频生成提示词，一句话，含镜头语言如 close-up/dolly）
            硬性要求：四场场景与节奏必须有明显区别，禁止连续多场同一场景同一机位；
            引用大纲关键词；对白符合短剧爽点节奏，不说空话。
            """;

    private final CredentialResolver credentialResolver;
    /** v2.4 指标埋点：LLM 调用次数/耗时。 */
    private final DramaMetrics dramaMetrics;
    private final ObjectMapper objectMapper;
    private final boolean enabled;
    private final String model;
    private final int maxTokens;
    private final int timeoutSeconds;
    private final int maxRetries;
    private final String cliPath;

    /** 启动时一次性解析出的 CLI 路径，null 表示无 CLI 回退。 */
    private String effectiveCliPath;

    /**
     * Spring 构造器。
     *
     * @param credentialResolver 凭证解析器（用户 Key 优先，回退平台凭证）
     * @param objectMapper        JSON 序列化器
     * @param enabled             是否启用 AI 剧本生成
     * @param model               模型名
     * @param maxTokens           最大生成 token 数
     * @param timeoutSeconds      单次请求超时（秒）
     * @param maxRetries          最大重试次数
     */


    /**
     * 构造器（Spring 通过 @Value 注入配置；测试可直接传参实例化）。
     *
     * @param credentialResolver 凭证解析器（用户 Key 优先，回退平台凭证）
     * @param objectMapper        JSON 序列化器
     * @param enabled             是否启用 AI 剧本生成
     * @param model               模型名
     * @param maxTokens           最大生成 token 数
     * @param timeoutSeconds      单次请求超时（秒）
     * @param maxRetries          最大重试次数
     * @param cliPath             CLI 回退路径（为空则自动探测）
     */
    public LlmScriptService(CredentialResolver credentialResolver,
                            ObjectMapper objectMapper,
                            @Value("${drama.script.llm.enabled:true}") boolean enabled,
                            @Value("${drama.script.llm.model:Deepseek-v4-flash}") String model,
                            @Value("${drama.script.llm.max-tokens:3000}") int maxTokens,
                            @Value("${drama.script.llm.timeout-seconds:120}") int timeoutSeconds,
                            @Value("${drama.script.llm.max-retries:2}") int maxRetries,
                            @Value("${drama.script.llm.cli-path:}") String cliPath,
                            DramaMetrics dramaMetrics) {
        this.credentialResolver = credentialResolver;
        this.dramaMetrics = dramaMetrics;
        this.objectMapper = objectMapper;
        this.enabled = enabled;
        this.model = model;
        this.maxTokens = maxTokens;
        this.timeoutSeconds = timeoutSeconds;
        this.maxRetries = maxRetries;
        this.cliPath = cliPath;
    }

    /**
     * 启动时校验配置，失败即 fail-fast。
     */
    @PostConstruct
    void validate() {
        if (enabled) {
            if (model == null || model.isBlank()) {
                throw new IllegalStateException("drama.script.llm.model 不能为空");
            }
            if (maxTokens <= 0) {
                throw new IllegalStateException("drama.script.llm.max-tokens 必须大于 0");
            }
            if (timeoutSeconds <= 0) {
                throw new IllegalStateException("drama.script.llm.timeout-seconds 必须大于 0");
            }
            if (maxRetries < 0) {
                throw new IllegalStateException("drama.script.llm.max-retries 不能为负数");
            }

            // CLI 回退路径解析：显式配置优先，否则按 HOME / user.home 自动探测 skill 路径
            // （注：容器/受管环境里 user.home 可能为 /root 而 HOME 指向真实家目录，两处都试）
            String configured = cliPath == null ? "" : cliPath.trim();
            String suffix = "/workspace/skills/weixin-chatapi/bin/chat.py";
            java.util.List<String> bases = new ArrayList<>();
            String envHome = System.getenv("HOME");
            if (envHome != null && !envHome.isBlank()) {
                bases.add(envHome);
            }
            String propHome = System.getProperty("user.home");
            if (propHome != null && !propHome.isBlank() && !bases.contains(propHome)) {
                bases.add(propHome);
            }
            if (!configured.isEmpty()) {
                File f = new File(configured);
                if (!f.isFile() || !f.canExecute()) {
                    throw new IllegalStateException(
                            "drama.script.llm.cli-path 指定的文件不存在或不可执行: " + configured);
                }
                effectiveCliPath = configured;
            } else {
                effectiveCliPath = null;
                for (String base : bases) {
                    File f = new File(base + suffix);
                    if (f.isFile() && f.canExecute()) {
                        effectiveCliPath = f.getAbsolutePath();
                        break;
                    }
                }
            }
            log.info("AI 剧本传输策略: HTTP 主用{}",
                    effectiveCliPath != null
                            ? "，CLI 回退可用(" + effectiveCliPath + ")"
                            : "（无 CLI 回退）");
        }
    }

    /**
     * AI 剧本生成结果。
     *
     * @param scenes           生成的 4 场场景草稿
     * @param model            使用的模型名
     * @param latencyMs        耗时（毫秒）
     * @param promptTokens     输入 token 数（usage 解析不到记 0）
     * @param completionTokens 输出 token 数（usage 解析不到记 0）
     */
    public record LlmScriptResult(List<ScriptGenerator.SceneDraft> scenes, String model, long latencyMs,
                                  long promptTokens, long completionTokens) {
    }

    /**
     * 模型调用结果：content 文本 + token 用量。
     * usage 解析失败时 promptTokens/completionTokens 为 0（诚实记 0，不编造）。
     */
    public record ModelCallResult(String content, long promptTokens, long completionTokens) {
    }

    /**
     * 调用大模型并解析用量。包可见且非 final，便于测试子类覆盖。
     *
     * <p>默认实现：走 HTTP（与 {@link #callModel} 同样的传输与 CLI 回退逻辑），
     * 解析 OpenAI 兼容响应的 {@code choices[0].message.content} 与 {@code usage}；
     * 若响应不是 OpenAI 格式，则整体当 content 处理、用量记 0（保持旧行为）。</p>
     *
     * @param body 请求体
     * @return content 文本与 token 用量
     */
    ModelCallResult callModelWithUsage(ObjectNode body) {
        try {
            String json = body.toString();
            Map.Entry<String, String> authHeader = credentialResolver.chatAuth();
            String responseBody = LlmTransport.postJson(CHAT_URL, json, authHeader, timeoutSeconds);
            return parseChatResponse(responseBody);
        } catch (RuntimeException httpEx) {
            if (effectiveCliPath == null) {
                throw httpEx;
            }
            log.warn("HTTP 传输失败，改用 CLI 回退: {}", httpEx.getMessage());
            String content = callModelViaCli(body);
            return new ModelCallResult(content, 0, 0);
        }
    }

    /**
     * 解析 OpenAI 兼容的 chat completion 响应，提取 content 与 usage。
     * 非 OpenAI 格式时整体当 content、用量记 0。包可见，便于测试。
     */
    ModelCallResult parseChatResponse(String responseBody) {
        if (responseBody == null || responseBody.isBlank()) {
            throw new LlmScriptUnavailableException("AI 返回为空");
        }
        JsonNode root;
        try {
            root = objectMapper.readTree(responseBody);
        } catch (IOException e) {
            // 不是 JSON：整体当 content，保持旧行为
            return new ModelCallResult(responseBody, 0, 0);
        }
        JsonNode choices = root.path("choices");
        String content;
        if (choices.isArray() && choices.size() > 0) {
            content = choices.get(0).path("message").path("content").asText(null);
            if (content == null) {
                content = responseBody;
            }
        } else {
            content = responseBody;
        }
        JsonNode usage = root.path("usage");
        long promptTokens = usage.path("prompt_tokens").asLong(0);
        long completionTokens = usage.path("completion_tokens").asLong(0);
        return new ModelCallResult(content, promptTokens, completionTokens);
    }

    /**
     * 调用大模型生成剧本。
     *
     * @param episode           剧集实体
     * @param charactersSummary 角色摘要（可为空字符串）
     * @return 生成结果
     * @throws LlmScriptUnavailableException 未启用 / 调用失败 / 返回格式无效
     */
    public LlmScriptResult generate(Episode episode, String charactersSummary) {
        long start = System.currentTimeMillis();
        try {
            LlmScriptResult result = doGenerate(episode, charactersSummary);
            dramaMetrics.recordScriptLlm(result.model(), System.currentTimeMillis() - start, true);
            return result;
        } catch (RuntimeException e) {
            dramaMetrics.recordScriptLlm(model, System.currentTimeMillis() - start, false);
            throw e;
        }
    }

    /**
     * generate 的实际执行体（指标 wrapper 之外）。
     */
    private LlmScriptResult doGenerate(Episode episode, String charactersSummary) {
        if (!enabled) {
            throw new LlmScriptUnavailableException("AI 剧本生成未启用（drama.script.llm.enabled=false）");
        }

        long start = System.currentTimeMillis();
        ObjectNode body = buildRequestBody(episode, charactersSummary);

        int attempts = maxRetries + 1;
        RuntimeException lastCause = null;
        for (int attempt = 0; attempt < attempts; attempt++) {
            try {
                ModelCallResult callResult = callModelWithUsage(body);
                List<ScriptGenerator.SceneDraft> scenes = parseScenes(callResult.content());
                long latencyMs = System.currentTimeMillis() - start;
                log.info("AI 剧本生成成功：model={}, 耗时={}ms, 场数={}, promptTokens={}, completionTokens={}",
                        model, latencyMs, scenes.size(), callResult.promptTokens(), callResult.completionTokens());
                return new LlmScriptResult(scenes, model, latencyMs,
                        callResult.promptTokens(), callResult.completionTokens());
            } catch (RuntimeException e) {
                lastCause = e;
                log.warn("AI 剧本生成第 {} 次尝试失败：{}", attempt + 1, e.getMessage());
                if (attempt < attempts - 1) {
                    long backoff = 1000L * (1L << attempt);
                    try {
                        Thread.sleep(backoff);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        throw new LlmScriptUnavailableException("AI 剧本生成被中断", ie);
                    }
                }
            }
        }
        throw new LlmScriptUnavailableException(
                "AI 剧本生成失败，已重试 " + maxRetries + " 次", lastCause);
    }

    /**
     * 构造请求体。
     *
     * @param episode           剧集实体
     * @param charactersSummary 角色摘要
     * @return JSON 请求体
     */
    private ObjectNode buildRequestBody(Episode episode, String charactersSummary) {
        ObjectNode root = objectMapper.createObjectNode();
        root.put("model", model);

        ArrayNode messages = root.putArray("messages");

        ObjectNode systemMsg = messages.addObject();
        systemMsg.put("role", "system");
        systemMsg.put("content", SYSTEM_PROMPT);

        ObjectNode userMsg = messages.addObject();
        userMsg.put("role", "user");
        userMsg.put("content", buildUserContent(episode, charactersSummary));

        root.put("max_tokens", maxTokens);
        root.put("temperature", 0.8);
        return root;
    }

    /**
     * 构造用户消息内容。
     *
     * @param episode           剧集实体
     * @param charactersSummary 角色摘要
     * @return 用户消息文本
     */
    private String buildUserContent(Episode episode, String charactersSummary) {
        StringBuilder sb = new StringBuilder();
        String title = null;
        String genre = null;
        try {
            if (episode.getProject() != null) {
                title = episode.getProject().getTitle();
                genre = episode.getProject().getGenre();
            }
        } catch (RuntimeException ignored) {
            // 防御性：project 懒加载等异常不应阻断主流程
        }
        sb.append("项目标题：").append(title == null || title.isBlank() ? "未命名" : title).append('\n');
        sb.append("题材：").append(genre == null || genre.isBlank() ? "未指定" : genre).append('\n');
        String outline = episode.getOutline();
        sb.append("大纲：").append(outline == null || outline.isBlank() ? "无大纲，请自由发挥" : outline).append('\n');
        if (charactersSummary != null && !charactersSummary.isBlank()) {
            sb.append("角色表：").append(charactersSummary).append('\n');
        }
        sb.append("请严格按系统提示输出恰好 4 场剧本的 JSON。");
        return sb.toString();
    }

        /**
     * 调用大模型接口。包可见且非 final，便于测试子类覆盖。
     *
     * <p>传输层走 {@link LlmTransport}（Apache HttpClient 5，预先代理认证），
     * 原因见该类 JavaDoc。</p>
     *
     * @param body 请求体
     * @return 模型返回的 content 文本
     */
    String callModel(ObjectNode body) {
        try {
            String json = body.toString();
            Map.Entry<String, String> authHeader =
                    credentialResolver.chatAuth();
            return LlmTransport.postJson(CHAT_URL, json, authHeader, timeoutSeconds);
        } catch (RuntimeException httpEx) {
            if (effectiveCliPath == null) {
                throw httpEx;
            }
            log.warn("HTTP 传输失败，改用 CLI 回退: {}", httpEx.getMessage());
            return callModelViaCli(body);
        }
    }

    /**
     * CLI 回退：在 Java 出站受限的环境中改调 chat.py（python 进程可正常出站）。
     *
     * <p>从请求体提取 system/user 文本，以命令行参数传给 CLI；stdout 即模型回复。</p>
     *
     * @param body 请求体
     * @return 模型返回的 content 文本
     */
    private String callModelViaCli(ObjectNode body) {
        String systemText = "";
        String userText = "";
        for (JsonNode m : body.path("messages")) {
            String role = m.path("role").asText("");
            String content = m.path("content").asText("");
            if ("system".equals(role)) {
                systemText = content;
            } else if ("user".equals(role)) {
                userText = content;
            }
        }
        List<String> cmd = new ArrayList<>(List.of(
                "python3", effectiveCliPath,
                "--model", model,
                "--max-tokens", String.valueOf(maxTokens)));
        if (!systemText.isBlank()) {
            cmd.add("--system");
            cmd.add(systemText);
        }
        cmd.add(userText);

        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.redirectErrorStream(false);
        Process process;
        try {
            process = pb.start();
        } catch (IOException e) {
            throw new RuntimeException("CLI 回退启动失败: " + e.getMessage(), e);
        }
        boolean done;
        try {
            done = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("CLI 回退被中断", e);
        }
        String stdout;
        String stderr;
        try {
            stdout = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
            stderr = new String(process.getErrorStream().readAllBytes(), StandardCharsets.UTF_8).trim();
        } catch (IOException e) {
            throw new RuntimeException("CLI 回退读取输出失败: " + e.getMessage(), e);
        }
        if (!done) {
            process.destroyForcibly();
            throw new RuntimeException("CLI 回退超时(" + timeoutSeconds + "s)");
        }
        if (process.exitValue() != 0) {
            String preview = stderr.length() > 300 ? stderr.substring(0, 300) : stderr;
            throw new RuntimeException("CLI 回退失败 exit=" + process.exitValue() + ": " + preview);
        }
        if (stdout.isEmpty()) {
            throw new RuntimeException("CLI 回退返回为空");
        }
        log.info("CLI 回退调用成功，返回长度={}", stdout.length());
        return stdout;
    }


    /**
     * 鲁棒解析模型返回内容为 4 场场景草稿。
     *
     * @param content 模型返回文本
     * @return 场景草稿列表
     * @throws LlmScriptUnavailableException 格式无效
     */
    private List<ScriptGenerator.SceneDraft> parseScenes(String content) {
        if (content == null) {
            throw new LlmScriptUnavailableException("AI 返回剧本格式无效: content 为 null");
        }
        String cleaned = content.trim();

        // 去掉 ```json ... ``` 或 ``` ... ``` 代码块围栏
        if (cleaned.startsWith("```")) {
            int firstNewline = cleaned.indexOf('\n');
            if (firstNewline > 0) {
                cleaned = cleaned.substring(firstNewline + 1);
            }
            int lastFence = cleaned.lastIndexOf("```");
            if (lastFence >= 0) {
                cleaned = cleaned.substring(0, lastFence);
            }
            cleaned = cleaned.trim();
        }

        // 截取第一个 '{' 到最后一个 '}'（或数组）
        int firstBrace = cleaned.indexOf('{');
        int lastBrace = cleaned.lastIndexOf('}');
        int firstBracket = cleaned.indexOf('[');
        int lastBracket = cleaned.lastIndexOf(']');

        String jsonText;
        if (firstBrace >= 0 && lastBrace > firstBrace
                && (firstBracket < 0 || firstBrace < firstBracket)) {
            jsonText = cleaned.substring(firstBrace, lastBrace + 1);
        } else if (firstBracket >= 0 && lastBracket > firstBracket) {
            jsonText = cleaned.substring(firstBracket, lastBracket + 1);
        } else {
            throw new LlmScriptUnavailableException("AI 返回剧本格式无效: 未找到 JSON 结构");
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(jsonText);
        } catch (IOException e) {
            throw new LlmScriptUnavailableException("AI 返回剧本格式无效: JSON 解析失败 " + e.getMessage(), e);
        }

        JsonNode scenesNode;
        if (root.isArray()) {
            scenesNode = root;
        } else {
            scenesNode = root.path("scenes");
        }
        if (!scenesNode.isArray()) {
            throw new LlmScriptUnavailableException("AI 返回剧本格式无效: 缺少 scenes 数组");
        }
        if (scenesNode.size() != 4) {
            throw new LlmScriptUnavailableException(
                    "AI 返回剧本格式无效: scenes 数量为 " + scenesNode.size() + "，应为 4");
        }

        List<ScriptGenerator.SceneDraft> drafts = new ArrayList<>(4);
        for (int i = 0; i < scenesNode.size(); i++) {
            JsonNode s = scenesNode.get(i);
            if (!s.isObject()) {
                throw new LlmScriptUnavailableException("AI 返回剧本格式无效: 第 " + (i + 1) + " 场不是对象");
            }
            JsonNode sceneNoNode = s.path("sceneNo");
            if (!sceneNoNode.isInt()) {
                throw new LlmScriptUnavailableException("AI 返回剧本格式无效: 第 " + (i + 1) + " 场 sceneNo 非法");
            }
            int sceneNo = sceneNoNode.asInt();
            if (sceneNo < 1 || sceneNo > 4) {
                throw new LlmScriptUnavailableException("AI 返回剧本格式无效: sceneNo 越界 " + sceneNo);
            }

            String location = textOrNull(s, "location");
            if (location == null || location.isBlank()) {
                throw new LlmScriptUnavailableException("AI 返回剧本格式无效: 第 " + (i + 1) + " 场 location 为空");
            }
            String description = textOrNull(s, "description");
            if (description == null || description.isBlank()) {
                throw new LlmScriptUnavailableException("AI 返回剧本格式无效: 第 " + (i + 1) + " 场 description 为空");
            }
            String dialogue = textOrNull(s, "dialogue");
            if (dialogue == null || dialogue.isBlank()) {
                throw new LlmScriptUnavailableException("AI 返回剧本格式无效: 第 " + (i + 1) + " 场 dialogue 为空");
            }

            String timeOfDay = textOrNull(s, "timeOfDay");
            if (timeOfDay == null || timeOfDay.isBlank()) {
                timeOfDay = "白天";
            }
            String prompt = textOrNull(s, "prompt");
            if (prompt == null) {
                prompt = "";
            }

            drafts.add(new ScriptGenerator.SceneDraft(sceneNo, location, timeOfDay, description, dialogue, prompt));
        }
        return drafts;
    }

    /**
     * 读取文本字段，不存在或非文本返回 null。
     *
     * @param node  JSON 节点
     * @param field 字段名
     * @return 文本或 null
     */
    private static String textOrNull(JsonNode node, String field) {
        JsonNode v = node.get(field);
        if (v == null || v.isNull()) {
            return null;
        }
        return v.asText();
    }

        

}

