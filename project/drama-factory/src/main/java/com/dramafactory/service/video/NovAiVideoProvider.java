package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.CredentialResolver;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

@Component("novAiVideoProvider")
public class NovAiVideoProvider implements VideoProvider {

    private static final String DEFAULT_BASE_URL = "https://aiapi-pro.com/v1";

    /**
     * NovAI API 基础地址，可用系统属性 novai.base-url 覆盖。
     * 测试环境可指向本地中继（Muse 平台限制 Java 直接 TCP 出站时）。
     */
    private static String baseUrl() {
        String override = System.getProperty("novai.base-url");
        if (override != null && !override.isBlank()) {
            return override.trim().replaceAll("/+$", "");
        }
        return DEFAULT_BASE_URL;
    }

    private static String submitUrl() {
        return baseUrl() + "/video/generations";
    }

    private static String queryUrl(String taskId) {
        return baseUrl() + "/video/generations/" + URLEncoder.encode(taskId, StandardCharsets.UTF_8);
    }

    private final CredentialResolver credentialResolver;
    private final HttpClient httpClient;
    private final VideoHttpGateway gateway;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Autowired
    public NovAiVideoProvider(CredentialResolver credentialResolver) {
        this(credentialResolver, null);
    }

    NovAiVideoProvider(CredentialResolver credentialResolver, VideoHttpGateway gateway) {
        this.credentialResolver = credentialResolver;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();
        this.gateway = gateway == null ? defaultGateway(this.httpClient) : gateway;
    }

    private static VideoHttpGateway defaultGateway(HttpClient client) {
        return request -> {
            HttpResponse<String> resp = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            return new VideoHttpGateway.GatewayResponse(resp.statusCode(), resp.body());
        };
    }

    @Override
    public String name() {
        return "novai";
    }

    @Override
    public String submit(Shot shot, int seconds) {
        String prompt = shot.getVideoPrompt();
        if (prompt == null || prompt.isBlank()) {
            StringBuilder sb = new StringBuilder();
            if (shot.getDescription() != null) {
                sb.append(shot.getDescription());
            }
            if (shot.getShotSize() != null) {
                sb.append("，").append(shot.getShotSize());
            }
            if (shot.getCameraMove() != null) {
                sb.append("，").append(shot.getCameraMove());
            }
            prompt = sb.toString();
        }

        // cogvideox-flash 实测使用 6 秒时长，低于 6 秒会被上游拒绝或降级，故取下限 6。
        int duration = Math.max(seconds, 6);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", "cogvideox-flash");
        body.put("prompt", prompt);
        body.put("resolution", "720p");
        body.put("duration", duration);

        String json;
        try {
            json = objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            throw new RuntimeException("novai 请求体序列化失败", e);
        }

        Map.Entry<String, String> auth = credentialResolver.novaiAuth(submitUrl());

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(submitUrl()))
                .timeout(Duration.ofSeconds(60))
                .header("Content-Type", "application/json")
                .header(auth.getKey(), auth.getValue())
                .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                .build();

        VideoHttpGateway.GatewayResponse resp;
        try {
            resp = gateway.exchange(request);
        } catch (Exception e) {
            throw new RuntimeException("novai 提交请求失败: " + e.getMessage(), e);
        }

        int code = resp.statusCode();
        String responseBody = resp.body() == null ? "" : resp.body();

        if (code == 429) {
            throw new RateLimitedException("novai 限流", 60);
        }
        if (code < 200 || code >= 300) {
            throw new RuntimeException("novai 提交失败, status=" + code + ", body=" + truncate(responseBody, 300));
        }

        try {
            JsonNode root = objectMapper.readTree(responseBody);
            JsonNode taskIdNode = root.get("task_id");
            if (taskIdNode == null || taskIdNode.isNull()) {
                taskIdNode = root.get("id");
            }
            if (taskIdNode == null || taskIdNode.isNull()) {
                throw new RuntimeException("novai 提交响应缺少 task_id/id: " + truncate(responseBody, 300));
            }
            return taskIdNode.asText();
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("novai 提交响应解析失败: " + truncate(responseBody, 300), e);
        }
    }

    @Override
    public ProbeResult poll(String providerTaskId) {
        String url = queryUrl(providerTaskId);
        Map.Entry<String, String> auth = credentialResolver.novaiAuth(url);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(30))
                .header(auth.getKey(), auth.getValue())
                .GET()
                .build();

        VideoHttpGateway.GatewayResponse resp;
        try {
            resp = gateway.exchange(request);
        } catch (Exception e) {
            throw new RuntimeException("novai 查询请求失败: " + e.getMessage(), e);
        }

        int code = resp.statusCode();
        String responseBody = resp.body() == null ? "" : resp.body();

        if (code == 429) {
            throw new RateLimitedException("novai 限流", 60);
        }
        if (code < 200 || code >= 300) {
            throw new RuntimeException("novai 查询失败, status=" + code + ", body=" + truncate(responseBody, 300));
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(responseBody);
        } catch (Exception e) {
            throw new RuntimeException("novai 查询响应解析失败: " + truncate(responseBody, 300), e);
        }

        String statusText = textOf(root, "task_status");
        if (statusText == null) {
            statusText = textOf(root, "status");
        }
        String normalized = statusText == null ? "" : statusText.trim();

        if ("completed".equalsIgnoreCase(normalized)
                || "succeeded".equalsIgnoreCase(normalized)
                || "SUCCESS".equals(normalized)) {
            String videoUrl = extractVideoUrl(root);
            return new ProbeResult(RemoteStatus.COMPLETED, videoUrl, null, 100);
        }

        if ("failed".equalsIgnoreCase(normalized)
                || "error".equalsIgnoreCase(normalized)
                || "cancelled".equalsIgnoreCase(normalized)
                || "FAILED".equals(normalized)) {
            String message = textOf(root, "message");
            if (message == null) {
                message = textOf(root, "error");
            }
            return new ProbeResult(RemoteStatus.FAILED, null, message, 0);
        }

        if (normalized.isEmpty()) {
            return new ProbeResult(RemoteStatus.QUEUED, null, null, 0);
        }
        return new ProbeResult(RemoteStatus.PROCESSING, null, null, 0);
    }

    private String extractVideoUrl(JsonNode root) {
        JsonNode videoResult = root.get("video_result");
        if (videoResult != null && videoResult.isArray() && videoResult.size() > 0) {
            JsonNode first = videoResult.get(0);
            if (first != null) {
                JsonNode urlNode = first.get("url");
                if (urlNode != null && !urlNode.isNull()) {
                    return urlNode.asText();
                }
            }
        }
        String videoUrl = textOf(root, "video_url");
        if (videoUrl != null) {
            return videoUrl;
        }
        String url = textOf(root, "url");
        if (url != null) {
            return url;
        }
        JsonNode dataNode = root.get("data");
        if (dataNode != null && !dataNode.isNull()) {
            JsonNode dataUrl = dataNode.get("url");
            if (dataUrl != null && !dataUrl.isNull()) {
                return dataUrl.asText();
            }
        }
        return null;
    }

    private static String textOf(JsonNode root, String field) {
        JsonNode node = root.get(field);
        if (node == null || node.isNull()) {
            return null;
        }
        return node.asText();
    }

    private static String truncate(String s, int max) {
        if (s == null) {
            return "";
        }
        return s.length() <= max ? s : s.substring(0, max);
    }

    @Override
    public ConnectivityResult probeConnectivity() {
        String url = queryUrl("__connectivity_probe__");
        try {
            Map.Entry<String, String> auth = credentialResolver.novaiAuth(url);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(20))
                    .header(auth.getKey(), auth.getValue())
                    .GET()
                    .build();

            VideoHttpGateway.GatewayResponse resp = gateway.exchange(request);
            int code = resp.statusCode();

            if (code == 404) {
                return new ConnectivityResult(ConnectivityStatus.OK, "密钥有效，链路畅通");
            }
            if (code == 401 || code == 403) {
                return new ConnectivityResult(ConnectivityStatus.AUTH_FAILED, "鉴权被拒绝，status=" + code);
            }
            if (code == 429) {
                return new ConnectivityResult(ConnectivityStatus.RATE_LIMITED, "请求被限流，status=" + code);
            }
            if (code >= 200 && code < 300) {
                return new ConnectivityResult(ConnectivityStatus.OK, "探测返回正常响应");
            }
            return new ConnectivityResult(ConnectivityStatus.PROVIDER_ERROR, "上游返回异常，status=" + code);
        } catch (Exception e) {
            return new ConnectivityResult(ConnectivityStatus.UNREACHABLE, "无法连通上游: " + e.getMessage());
        }
    }
}

