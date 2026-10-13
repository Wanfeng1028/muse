package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.ShotSize;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.video.SurrogateAuthClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 剧本拆分服务：调用微信 ChatAPI 大模型把剧本原文拆成结构化分镜并落库。
 */
@Service
public class ScriptSplitterService {

    /** 微信 ChatAPI 的 OpenAI 兼容对话补全地址。 */
    private static final String SPLIT_URL = "https://chatapi.weixin.qq.com/openai/v1/chat/completions";

    /** 代理鉴权使用的凭证标识。 */
    private static final String CREDENTIAL = "custom.weixin-chatapi";

    /** 系统提示词：严格要求只输出 JSON 数组。 */
    private static final String SYSTEM_PROMPT =
            "你是短剧分镜师。把用户粘贴的剧本原文拆成结构化分镜，只输出 JSON 数组，不要任何解释文字。"
                    + "数组每项字段：shotNo（整数，从1开始）、"
                    + "shotSize（只能是以下之一：特写/近景/中景/全景/远景）、"
                    + "cameraMove（只能是以下之一：固定机位/推镜头/拉镜头/摇镜头/移镜头/跟镜头/升降）、"
                    + "description（画面描述，中文）、"
                    + "durationSeconds（整数秒，3到8之间）、"
                    + "dialogue（对白或旁白，可为空字符串）、"
                    + "videoPrompt（英文视频生成提示词，cinematic 风格，注明 16:9）。"
                    + "分镜数量 2 到 8 个。";

    private final EpisodeRepository episodeRepository;
    private final ShotRepository shotRepository;
    private final VideoTaskRepository videoTaskRepository;
    private final SurrogateAuthClient surrogateAuthClient;
    private final ObjectMapper objectMapper;
    private final String model;
    private final int maxTokens;

    public ScriptSplitterService(EpisodeRepository episodeRepository,
                                 ShotRepository shotRepository,
                                 VideoTaskRepository videoTaskRepository,
                                 SurrogateAuthClient surrogateAuthClient,
                                 ObjectMapper objectMapper,
                                 @Value("${drama.script-splitter.model:Deepseek-v4-flash}") String model,
                                 @Value("${drama.script-splitter.max-tokens:3000}") int maxTokens) {
        this.episodeRepository = episodeRepository;
        this.shotRepository = shotRepository;
        this.videoTaskRepository = videoTaskRepository;
        this.surrogateAuthClient = surrogateAuthClient;
        this.objectMapper = objectMapper;
        this.model = model;
        this.maxTokens = maxTokens;
    }

    /**
     * 根据剧本原文拆分分镜并落库，返回新建分镜的响应列表。
     */
    @Transactional
    public List<Records.ShotResponse> splitFromScript(Long episodeId, String scriptText) {
        // 1. 参数校验
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));
        if (scriptText == null || scriptText.isBlank()) {
            throw new IllegalArgumentException("剧本原文不能为空");
        }

        // 2. 调用大模型
        String content = callModel(scriptText);

        // 3. 剥离 markdown 代码围栏
        String json = stripCodeFence(content);

        // 4. 解析为 JSON 数组
        ArrayNode array;
        try {
            JsonNode root = objectMapper.readTree(json);
            if (!root.isArray()) {
                throw new RuntimeException("大模型返回的不是 JSON 数组");
            }
            array = (ArrayNode) root;
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("解析大模型返回内容失败: " + e.getMessage(), e);
        }
        if (array.isEmpty()) {
            throw new RuntimeException("大模型未拆出任何分镜");
        }

        // 5. 删除该剧集旧分镜（先删关联的视频任务）
        List<Shot> oldShots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
        for (Shot oldShot : oldShots) {
            videoTaskRepository.deleteAll(videoTaskRepository.findByShotIdOrderByIdDesc(oldShot.getId()));
            shotRepository.delete(oldShot);
        }

        // 6. 遍历 JSON 数组建 Shot
        List<Shot> saved = new ArrayList<>();
        int index = 0;
        for (JsonNode node : array) {
            index++;
            Shot shot = new Shot();
            shot.setEpisode(episode);

            // shotNo：缺省用序号
            JsonNode shotNoNode = node.get("shotNo");
            int shotNo = (shotNoNode != null && shotNoNode.isInt()) ? shotNoNode.asInt() : index;
            shot.setShotNo(shotNo);

            // shotSize
            String shotSizeText = text(node, "shotSize");
            final ShotSize shotSize;
            try {
                shotSize = ShotSize.fromLabel(shotSizeText);
            } catch (IllegalArgumentException e) {
                throw new RuntimeException("第 " + index + " 个分镜的字段 shotSize 非法: " + shotSizeText, e);
            }
            shot.setShotSize(shotSize);

            // cameraMove
            String cameraMoveText = text(node, "cameraMove");
            final CameraMove cameraMove;
            try {
                cameraMove = CameraMove.fromLabel(cameraMoveText);
            } catch (IllegalArgumentException e) {
                throw new RuntimeException("第 " + index + " 个分镜的字段 cameraMove 非法: " + cameraMoveText, e);
            }
            shot.setCameraMove(cameraMove);

            // description / dialogue / videoPrompt
            shot.setDescription(text(node, "description"));
            shot.setDialogue(text(node, "dialogue"));
            shot.setVideoPrompt(text(node, "videoPrompt"));

            // durationSeconds：缺省 5
            JsonNode durationNode = node.get("durationSeconds");
            int duration = (durationNode != null && durationNode.isInt()) ? durationNode.asInt() : 5;
            shot.setDurationSeconds(duration);

            saved.add(shotRepository.save(shot));
        }

        // 7. 更新剧集状态
        episode.setStatus(EpisodeStatus.SCRIPTED);
        episodeRepository.save(episode);

        // 8. 返回响应
        List<Records.ShotResponse> responses = new ArrayList<>(saved.size());
        for (Shot shot : saved) {
            responses.add(toResponse(shot));
        }
        return responses;
    }

    /**
     * 调用微信 ChatAPI，返回 choices[0].message.content。
     */
    private String callModel(String scriptText) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();

        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", model);
        ArrayNode messages = body.putArray("messages");
        ObjectNode systemMsg = messages.addObject();
        systemMsg.put("role", "system");
        systemMsg.put("content", SYSTEM_PROMPT);
        ObjectNode userMsg = messages.addObject();
        userMsg.put("role", "user");
        userMsg.put("content", scriptText);
        body.put("max_tokens", maxTokens);

        String requestBody;
        try {
            requestBody = objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            throw new RuntimeException("构建请求体失败: " + e.getMessage(), e);
        }

        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(SPLIT_URL))
                .timeout(Duration.ofSeconds(90))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(requestBody));

        // 注入鉴权头（不打印凭证）
        Map.Entry<String, String> authHeader = surrogateAuthClient.authHeader(SPLIT_URL, CREDENTIAL);
        if (authHeader != null) {
            builder.header(authHeader.getKey(), authHeader.getValue());
        }

        HttpResponse<String> response;
        try {
            response = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new RuntimeException("调用大模型失败: " + e.getMessage(), e);
        }

        int status = response.statusCode();
        String responseBody = response.body();
        if (status < 200 || status >= 300) {
            String preview = responseBody == null ? "" : responseBody;
            if (preview.length() > 300) {
                preview = preview.substring(0, 300);
            }
            throw new RuntimeException("调用大模型失败，状态码 " + status + "，响应: " + preview);
        }

        String content;
        try {
            JsonNode root = objectMapper.readTree(responseBody);
            JsonNode choices = root.get("choices");
            if (choices == null || !choices.isArray() || choices.isEmpty()) {
                throw new RuntimeException("大模型返回内容为空");
            }
            JsonNode message = choices.get(0).get("message");
            if (message == null) {
                throw new RuntimeException("大模型返回内容为空");
            }
            JsonNode contentNode = message.get("content");
            content = contentNode == null ? null : contentNode.asText();
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("解析大模型响应失败: " + e.getMessage(), e);
        }

        if (content == null || content.isBlank()) {
            throw new RuntimeException("大模型返回内容为空");
        }
        return content;
    }

    /**
     * 去掉首尾可能存在的 markdown 代码围栏。
     */
    private String stripCodeFence(String content) {
        String trimmed = content.trim();
        if (trimmed.startsWith("```")) {
            int firstNewline = trimmed.indexOf('\n');
            if (firstNewline >= 0) {
                trimmed = trimmed.substring(firstNewline + 1);
            } else {
                trimmed = trimmed.substring(3);
            }
            int lastFence = trimmed.lastIndexOf("```");
            if (lastFence >= 0) {
                trimmed = trimmed.substring(0, lastFence);
            }
        }
        return trimmed.trim();
    }

    /**
     * 安全读取文本字段，缺失或非文本时返回 null。
     */
    private String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || value.isNull()) {
            return null;
        }
        return value.asText();
    }

    /**
     * 用对话确认后的分镜批量替换该剧集旧分镜并落库。
     *
     * <p>供"AI 对话"页使用：用户在对话里逐镜调整确认后，前端把最终分镜数组
     * 直接发过来，不再走一次 AI 拆分，保证落库内容与对话一致。</p>
     *
     * @param episodeId 剧集 ID
     * @param items     确认后的分镜项（景别/运镜为中文标签）
     * @return 新建分镜的响应列表
     */
    @Transactional
    public List<Records.ShotResponse> replaceShots(Long episodeId, List<Records.ShotBatchItem> items) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("分镜列表不能为空");
        }
        if (items.size() > 30) {
            throw new IllegalArgumentException("单次最多落库 30 个分镜");
        }

        // 删除旧分镜（先删关联的视频任务）
        List<Shot> oldShots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
        for (Shot oldShot : oldShots) {
            videoTaskRepository.deleteAll(videoTaskRepository.findByShotIdOrderByIdDesc(oldShot.getId()));
            shotRepository.delete(oldShot);
        }

        // 落库新分镜
        List<Shot> saved = new ArrayList<>(items.size());
        int index = 0;
        for (Records.ShotBatchItem item : items) {
            index++;
            if (item.shotNo() == null) {
                throw new IllegalArgumentException("第 " + index + " 个分镜缺少镜号");
            }
            Shot shot = new Shot();
            shot.setEpisode(episode);
            shot.setShotNo(item.shotNo());
            try {
                shot.setShotSize(ShotSize.fromLabel(item.shotSize()));
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException(
                        "第 " + index + " 个分镜的景别非法: " + item.shotSize(), e);
            }
            try {
                shot.setCameraMove(CameraMove.fromLabel(item.cameraMove()));
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException(
                        "第 " + index + " 个分镜的运镜非法: " + item.cameraMove(), e);
            }
            if (shot.getCameraMove() == null) {
                throw new IllegalArgumentException(
                        "第 " + index + " 个分镜的运镜非法: " + item.cameraMove());
            }
            shot.setDescription(item.description());
            shot.setDialogue(item.dialogue());
            shot.setVideoPrompt(item.videoPrompt());
            int duration = item.durationSeconds() != null ? item.durationSeconds() : 5;
            if (duration < 1 || duration > 30) {
                throw new IllegalArgumentException("第 " + index + " 个分镜的时长非法: " + duration);
            }
            shot.setDurationSeconds(duration);
            saved.add(shotRepository.save(shot));
        }

        episode.setStatus(EpisodeStatus.SCRIPTED);
        episodeRepository.save(episode);

        List<Records.ShotResponse> responses = new ArrayList<>(saved.size());
        for (Shot shot : saved) {
            responses.add(toResponse(shot));
        }
        return responses;
    }

    /**
     * 映射 Shot 到 ShotResponse，字段与 ShotService.toResponse 保持一致。
     */
    private Records.ShotResponse toResponse(Shot shot) {        return new Records.ShotResponse(
                shot.getId(),
                shot.getEpisode() == null ? null : shot.getEpisode().getId(),
                shot.getShotNo(),
                shot.getShotSize(),
                shot.getShotSize() == null ? null : shot.getShotSize().getLabel(),
                shot.getCameraMove(),
                shot.getCameraMove() == null ? null : shot.getCameraMove().getLabel(),
                shot.getDescription(),
                shot.getDurationSeconds(),
                shot.getDialogue(),
                shot.getVideoPrompt(),
                shot.getCreatedAt(),
                shot.getUpdatedAt()
        );
    }
}

