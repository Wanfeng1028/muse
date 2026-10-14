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

@Component("didAvatarProvider")
public class DidAvatarProvider implements AvatarProvider {

    private static final String BASE_URL = "https://api.d-id.com";
    private static final Duration SUBMIT_TIMEOUT = Duration.ofSeconds(60);
    private static final Duration POLL_TIMEOUT = Duration.ofSeconds(15);
    private static final Duration PROBE_TIMEOUT = Duration.ofSeconds(15);

    private final CredentialResolver credentialResolver;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;
    private final ByokHttpGateway gateway;

    @Autowired
    public DidAvatarProvider(CredentialResolver credentialResolver, ObjectMapper objectMapper) {
        this(credentialResolver, objectMapper, null);
    }

    DidAvatarProvider(CredentialResolver credentialResolver, ObjectMapper objectMapper, ByokHttpGateway gateway) {
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
        return "did-avatar";
    }

    @Override
    public SubmitResult submit(String apiKey, String imageUrl, String audioUrlOrNull, String scriptOrNull) {
        boolean hasAudio = audioUrlOrNull != null && !audioUrlOrNull.isBlank();
        boolean hasScript = scriptOrNull != null && !scriptOrNull.isBlank();
        if (!hasAudio && !hasScript) {
            throw new IllegalArgumentException("请提供音频 URL 或文案");
        }

        ObjectNode body = objectMapper.createObjectNode();
        body.put("source_url", imageUrl);
        ObjectNode script = body.putObject("script");
        if (hasAudio) {
            script.put("type", "audio");
            script.put("audio_url", audioUrlOrNull);
        } else {
            script.put("type", "text");
            script.put("input", scriptOrNull);
        }

        String json;
        try {
            json = objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            throw new RuntimeException("D-ID 提交请求序列化失败");
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/talks"))
                .timeout(SUBMIT_TIMEOUT)
                .header("Authorization", buildAuthorization(apiKey))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                .build();

        ByokHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            throw new RuntimeException("D-ID 提交失败: " + e.getClass().getSimpleName());
        }

        int code = response.statusCode();
        String respBody = response.body();
        if (code < 200 || code >= 300) {
            throw new RuntimeException("D-ID 提交失败, HTTP " + code + ", 响应: " + truncate(respBody, 300));
        }

        try {
            JsonNode root = objectMapper.readTree(respBody);
            JsonNode idNode = root.get("id");
            if (idNode == null || idNode.isNull() || idNode.asText().isBlank()) {
                throw new RuntimeException("D-ID 提交失败: 响应缺少 id");
            }
            return new SubmitResult(idNode.asText());
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("D-ID 提交失败: 响应解析失败");
        }
    }

    @Override
    public PollResult poll(String apiKey, String talkId) {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/talks/" + talkId))
                .timeout(POLL_TIMEOUT)
                .header("Authorization", buildAuthorization(apiKey))
                .GET()
                .build();

        ByokHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            throw new RuntimeException("D-ID 轮询失败: " + e.getClass().getSimpleName());
        }

        int code = response.statusCode();
        String respBody = response.body();
        if (code < 200 || code >= 300) {
            throw new RuntimeException("D-ID 轮询失败, HTTP " + code + ", 响应: " + truncate(respBody, 300));
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(respBody);
        } catch (Exception e) {
            throw new RuntimeException("D-ID 轮询失败: 响应解析失败");
        }

        String status = root.path("status").asText("");
        switch (status) {
            case "done" -> {
                JsonNode resultUrl = root.get("result_url");
                if (resultUrl == null || resultUrl.isNull() || resultUrl.asText().isBlank()) {
                    throw new RuntimeException("D-ID 轮询失败: done 状态缺少 result_url");
                }
                return new PollResult(RemoteStatus.SUCCEEDED, resultUrl.asText(), null, 100);
            }
            case "error" -> {
                String message = root.path("message").asText("");
                if (message.isBlank()) {
                    message = "D-ID 生成失败";
                }
                return new PollResult(RemoteStatus.FAILED, null, message, 0);
            }
            case "created", "started" -> {
                return new PollResult(RemoteStatus.PROCESSING, null, null, 50);
            }
            default -> {
                return new PollResult(RemoteStatus.QUEUED, null, null, 0);
            }
        }
    }

    @Override
    public ConnectivityResult probe(String apiKey) {
        Map.Entry<String, String> auth = credentialResolver.didAuth(apiKey);
        if (auth == null) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.AUTH_FAILED,
                    "未配置密钥：请先在通道管理填写该供应商的 API Key");
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/credits"))
                .timeout(PROBE_TIMEOUT)
                .header(auth.getKey(), auth.getValue())
                .GET()
                .build();

        ByokHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.UNREACHABLE,
                    "D-ID 探针异常: " + e.getClass().getSimpleName());
        }

        int code = response.statusCode();
        if (code >= 200 && code < 300) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.OK, "D-ID 连通正常");
        }
        if (code == 401 || code == 403) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.AUTH_FAILED, "D-ID 鉴权失败, HTTP " + code);
        }
        if (code == 429) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.RATE_LIMITED, "D-ID 请求限流, HTTP 429");
        }
        return new ConnectivityResult(VideoProvider.ConnectivityStatus.PROVIDER_ERROR,
                "D-ID 供应商异常, HTTP " + code);
    }

    private String buildAuthorization(String apiKey) {
        String token = java.util.Base64.getEncoder()
                .encodeToString((apiKey + ":").getBytes(StandardCharsets.UTF_8));
        return "Basic " + token;
    }

    private String truncate(String value, int max) {
        if (value == null) {
            return "";
        }
        if (value.length() <= max) {
            return value;
        }
        return value.substring(0, max);
    }
}
