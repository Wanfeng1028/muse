package com.dramafactory.service.byok;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.video.VideoProvider;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

/**
 * MiniMax 音乐生成 Provider。
 *
 * <p>重要提示：根据 MiniMax 官方公告，音乐生成 API 自 2026-08 起不再对新用户开放，
 * 免费档已停服，仅存量付费用户可继续使用。因此本 Provider 仅用于兼容既有付费用户，
 * 新接入请评估其他音乐生成服务。</p>
 */
@Component("minimaxMusicProvider")
public class MiniMaxMusicProvider implements MusicProvider {

    private static final String DEFAULT_API_BASE = "https://api.minimaxi.com";
    private static final String PROBE_MODEL = "__connectivity_probe__";
    private static final int ERROR_MSG_MAX_LEN = 300;
    private static final Duration GENERATE_TIMEOUT = Duration.ofSeconds(90);
    private static final Duration PROBE_TIMEOUT = Duration.ofSeconds(15);

    private final CredentialResolver credentialResolver;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;
    private final ByokHttpGateway gateway;

    @Autowired
    public MiniMaxMusicProvider(CredentialResolver credentialResolver, ObjectMapper objectMapper) {
        this(credentialResolver, objectMapper, null);
    }

    MiniMaxMusicProvider(CredentialResolver credentialResolver, ObjectMapper objectMapper, ByokHttpGateway gateway) {
        this.credentialResolver = credentialResolver;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        this.gateway = gateway != null ? gateway : defaultGateway(this.httpClient);
    }

    private static ByokHttpGateway defaultGateway(HttpClient client) {
        return request -> {
            HttpResponse<String> resp = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            return new ByokHttpGateway.GatewayResponse(resp.statusCode(), resp.body());
        };
    }

    @Override
    public String name() {
        return "minimax-music";
    }

    @Override
    public GenerateResult generate(String apiKey, String apiBase, String modelId, String prompt,
                                   String lyrics, boolean instrumental) {
        if (!instrumental && (lyrics == null || lyrics.isBlank())) {
            throw new IllegalArgumentException("非纯音乐模式请填写歌词");
        }

        Map.Entry<String, String> auth = credentialResolver.minimaxAuth(apiKey);
        if (auth == null || auth.getKey() == null || auth.getKey().isBlank()) {
            throw new IllegalStateException("未配置密钥：请先在通道管理填写该供应商的 API Key");
        }
        String resolvedKey = auth.getKey();

        String base = normalizeBase(apiBase);
        String url = base + "/v1/music_generation";

        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", modelId);
        body.put("prompt", prompt == null ? "" : prompt);
        body.put("lyrics", lyrics == null ? "" : lyrics);
        body.put("is_instrumental", instrumental);
        body.put("lyrics_optimizer", false);
        body.put("output_format", "url");

        ObjectNode audioSetting = objectMapper.createObjectNode();
        audioSetting.put("sample_rate", 44100);
        audioSetting.put("bitrate", 256000);
        audioSetting.put("format", "mp3");
        body.set("audio_setting", audioSetting);

        String payload;
        try {
            payload = objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            throw new RuntimeException("MiniMax 音乐生成失败, HTTP " + -1);
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(GENERATE_TIMEOUT)
                .header("Authorization", "Bearer " + resolvedKey)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(payload))
                .build();

        ByokHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            throw new RuntimeException("MiniMax 音乐生成失败, HTTP " + -1);
        }

        int code = response.statusCode();
        if (code < 200 || code >= 300) {
            throw new RuntimeException("MiniMax 音乐生成失败, HTTP " + code);
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(response.body());
        } catch (Exception e) {
            throw new RuntimeException("MiniMax 音乐生成失败, HTTP " + code);
        }

        JsonNode baseResp = root.path("base_resp");
        int statusCode = baseResp.path("status_code").asInt(0);
        if (statusCode != 0) {
            String statusMsg = baseResp.path("status_msg").asText("");
            throw new RuntimeException("MiniMax 生成失败：" + truncate(statusMsg, ERROR_MSG_MAX_LEN));
        }

        String audioUrl = root.path("data").path("audio").asText("");
        if (audioUrl == null || audioUrl.isBlank()) {
            throw new RuntimeException("MiniMax 未返回音频地址");
        }

        Integer durationMs = null;
        JsonNode durationNode = root.path("extra_info").path("music_duration");
        if (durationNode != null && durationNode.isNumber()) {
            durationMs = durationNode.asInt();
        }

        return new GenerateResult(audioUrl, durationMs);
    }

    @Override
    public ConnectivityResult probe(String apiKey, String apiBase) {
        Map.Entry<String, String> auth = credentialResolver.minimaxAuth(apiKey);
        if (auth == null || auth.getKey() == null || auth.getKey().isBlank()) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.AUTH_FAILED,
                    "未配置密钥：请先在通道管理填写该供应商的 API Key");
        }
        String resolvedKey = auth.getKey();

        String base = normalizeBase(apiBase);
        String url = base + "/v1/music_generation";

        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", PROBE_MODEL);
        body.put("prompt", "probe");

        String payload;
        try {
            payload = objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.UNREACHABLE, "探针请求构造失败");
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(PROBE_TIMEOUT)
                .header("Authorization", "Bearer " + resolvedKey)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(payload))
                .build();

        ByokHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.UNREACHABLE, "无法连接 MiniMax 服务");
        }

        int code = response.statusCode();
        if (code == 401 || code == 403) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.AUTH_FAILED, "密钥无效或鉴权失败");
        }
        if (code == 429) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.RATE_LIMITED, "请求频率受限");
        }
        if (code >= 400 && code < 500) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.OK, "密钥有效，链路畅通");
        }
        if (code >= 500) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, "MiniMax 服务端错误");
        }
        return new ConnectivityResult(VideoProvider.ConnectivityStatus.OK, "密钥有效，链路畅通");
    }

    private String normalizeBase(String apiBase) {
        String base = (apiBase == null || apiBase.isBlank()) ? DEFAULT_API_BASE : apiBase;
        while (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        return base;
    }

    private String truncate(String value, int maxLen) {
        if (value == null) {
            return "";
        }
        if (value.length() <= maxLen) {
            return value;
        }
        return value.substring(0, maxLen);
    }
}
