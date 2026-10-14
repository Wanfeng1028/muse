package com.dramafactory.service.byok;

import com.dramafactory.service.video.VideoProvider;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * ACE-Step 音乐模型的 BYOK 封装。
 * 按 OpenAI 兼容之外的第三方聚合 HTTP 形态接入：POST {apiBase}/api/v1/generate。
 */
@Component("aceStepMusicProvider")
public class AceStepMusicProvider implements MusicProvider {

    private static final Logger log = LoggerFactory.getLogger(AceStepMusicProvider.class);

    private static final String DEFAULT_MODEL = "ace-step";
    private static final String PROBE_MODEL = "__connectivity_probe__";
    private static final Duration GENERATE_TIMEOUT = Duration.ofSeconds(300);
    private static final Duration PROBE_TIMEOUT = Duration.ofSeconds(15);
    private static final int DETAIL_MAX_LEN = 300;

    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(15))
            .build();

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public String name() {
        return "ace-step-music";
    }

    @Override
    public GenerateResult generate(String apiKey, String apiBase, String modelId,
                                   String prompt, String lyrics, boolean instrumental) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException("未配置密钥：请先在通道管理填写该供应商的 API Key");
        }
        String base = normalizeBase(apiBase);
        String model = (modelId == null || modelId.isBlank()) ? DEFAULT_MODEL : modelId;

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("prompt", prompt == null ? "" : prompt);
        body.put("lyrics", instrumental ? "" : (lyrics == null ? "" : lyrics));
        body.put("model", model);
        body.put("instrumental", instrumental);

        String payload;
        try {
            payload = objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            throw new IllegalStateException("构建请求体失败：" + truncate(e.getMessage()));
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(base + "/api/v1/generate"))
                .timeout(GENERATE_TIMEOUT)
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException("请求作曲接口失败：" + truncate(e.getMessage()));
        }

        int code = response.statusCode();
        String responseBody = response.body() == null ? "" : response.body();
        if (code < 200 || code >= 300) {
            throw new IllegalStateException("作曲接口返回异常（HTTP " + code + "）：" + truncate(responseBody));
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(responseBody);
        } catch (Exception e) {
            throw new IllegalStateException("作曲接口响应解析失败：" + truncate(e.getMessage()));
        }

        String audioUrl = extractAudioUrl(root);
        if (audioUrl == null || audioUrl.isBlank()) {
            throw new IllegalStateException("作曲接口未返回音频地址：" + truncate(responseBody));
        }
        Integer durationMs = extractDurationMs(root);
        return new GenerateResult(audioUrl, durationMs);
    }

    @Override
    public ConnectivityResult probe(String apiKey, String apiBase) {
        if (apiKey == null || apiKey.isBlank()) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.AUTH_FAILED,
                    "未配置密钥：请先在通道管理填写该供应商的 API Key");
        }
        String base = normalizeBase(apiBase);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("prompt", "");
        body.put("lyrics", "");
        body.put("model", PROBE_MODEL);
        body.put("instrumental", true);

        String payload;
        try {
            payload = objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.UNREACHABLE,
                    "构建探针请求体失败：" + truncate(e.getMessage()));
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(base + "/api/v1/generate"))
                .timeout(PROBE_TIMEOUT)
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (Exception e) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.UNREACHABLE,
                    "连接失败：" + truncate(e.getMessage()));
        }

        int code = response.statusCode();
        String responseBody = response.body() == null ? "" : response.body();

        if (code == 401 || code == 403) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.AUTH_FAILED,
                    "鉴权失败（HTTP " + code + "）：密钥无效或权限不足");
        }
        if (code == 429) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.RATE_LIMITED,
                    "请求被限流（HTTP 429）：请稍后重试");
        }
        if (code >= 500) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.PROVIDER_ERROR,
                    "供应商服务异常（HTTP " + code + "）：" + truncate(responseBody));
        }
        if (code >= 400) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.OK,
                    "密钥有效，探针返回 HTTP " + code + "（探针模型不被接受属预期）");
        }
        return new ConnectivityResult(VideoProvider.ConnectivityStatus.OK,
                "连接自检通过（HTTP " + code + "）");
    }

    private String extractAudioUrl(JsonNode root) {
        JsonNode data = root.path("data");
        if (data.isObject()) {
            JsonNode audio = data.path("audio_url");
            if (audio.isTextual() && !audio.asText().isBlank()) {
                return audio.asText();
            }
            JsonNode url = data.path("url");
            if (url.isTextual() && !url.asText().isBlank()) {
                return url.asText();
            }
        }
        JsonNode top = root.path("audio_url");
        if (top.isTextual() && !top.asText().isBlank()) {
            return top.asText();
        }
        return null;
    }

    private Integer extractDurationMs(JsonNode root) {
        JsonNode data = root.path("data");
        if (data.isObject()) {
            JsonNode ms = data.path("duration_ms");
            if (ms.isNumber()) {
                return ms.asInt();
            }
            JsonNode sec = data.path("duration");
            if (sec.isNumber()) {
                return (int) Math.round(sec.asDouble() * 1000.0);
            }
        }
        JsonNode ms = root.path("duration_ms");
        if (ms.isNumber()) {
            return ms.asInt();
        }
        JsonNode sec = root.path("duration");
        if (sec.isNumber()) {
            return (int) Math.round(sec.asDouble() * 1000.0);
        }
        return null;
    }

    private String normalizeBase(String apiBase) {
        if (apiBase == null || apiBase.isBlank()) {
            throw new IllegalStateException("未配置 API 地址：请先在通道管理填写该供应商的 API Base");
        }
        String base = apiBase.trim();
        while (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        return base;
    }

    private String truncate(String text) {
        if (text == null) {
            return "";
        }
        String trimmed = text.trim();
        if (trimmed.length() <= DETAIL_MAX_LEN) {
            return trimmed;
        }
        return trimmed.substring(0, DETAIL_MAX_LEN) + "…";
    }
}
