package com.dramafactory.service.byok;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.video.VideoProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.Set;

@Component("dashscopeImageProvider")
public class DashScopeImageProvider implements ImageProvider {

    private static final String DEFAULT_BASE = "https://dashscope.aliyuncs.com";
    private static final String PROBE_TASK_ID = "__connectivity_probe__";
    private static final Set<String> ALLOWED_SIZES = Set.of("1024*1024", "1024*1536", "1536*1024");

    private final CredentialResolver credentialResolver;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;
    private final ByokHttpGateway gateway;

    @Autowired
    public DashScopeImageProvider(CredentialResolver credentialResolver, ObjectMapper objectMapper) {
        this(credentialResolver, objectMapper, null);
    }

    DashScopeImageProvider(CredentialResolver credentialResolver, ObjectMapper objectMapper, ByokHttpGateway gateway) {
        this.credentialResolver = credentialResolver;
        this.objectMapper = objectMapper;
        this.gateway = gateway;
        this.httpClient = defaultGateway(HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build());
    }

    private static HttpClient defaultGateway(HttpClient client) {
        return client;
    }

    @Override
    public String name() {
        return "dashscope-image";
    }

    private Map.Entry<String, String> auth(String apiKey, String url) {
        return credentialResolver.dashscopeByokAuth(apiKey, url);
    }

    private String base(String apiBase) {
        String b = (apiBase == null || apiBase.isBlank()) ? DEFAULT_BASE : apiBase.trim();
        while (b.endsWith("/")) {
            b = b.substring(0, b.length() - 1);
        }
        // 兼容卡片 apiAddress 已带 /api/v1 的写法（如 presets.json）
        if (b.endsWith("/api/v1")) {
            b = b.substring(0, b.length() - "/api/v1".length());
        }
        return b;
    }

    @Override
    public SubmitResult submit(String apiKey, String apiBase, String modelId, String prompt, String size) {
        if (size == null || !ALLOWED_SIZES.contains(size)) {
            throw new IllegalArgumentException("不支持的图片尺寸：" + size);
        }
        String url = base(apiBase) + "/api/v1/services/aigc/text2image/image-synthesis";
        Map.Entry<String, String> credential = auth(apiKey, url);
        if (credential == null) {
            throw new IllegalStateException("未配置密钥：请先在通道管理填写该供应商的 API Key");
        }
        String authHeader = credential.getValue();

        String body;
        try {
            Map<String, Object> payload = Map.of(
                    "model", modelId,
                    "input", Map.of("prompt", prompt),
                    "parameters", Map.of("size", size, "n", 1)
            );
            body = objectMapper.writeValueAsString(payload);
        } catch (Exception e) {
            throw new RuntimeException("DashScope 图片提交失败, 请求体构建异常");
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(60))
                .header("Authorization", authHeader)
                .header("Content-Type", "application/json")
                .header("X-DashScope-Async", "enable")
                .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                .build();

        ByokHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            throw new RuntimeException("DashScope 图片提交失败, 网络不可达：请求发送失败");
        }

        int code = response.statusCode();
        String responseBody = response.body() == null ? "" : response.body();

        if (code < 200 || code >= 300) {
            throw new RuntimeException("DashScope 图片提交失败, HTTP " + code + ", 响应: " + truncate(responseBody, 300));
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(responseBody);
        } catch (Exception e) {
            throw new RuntimeException("DashScope 图片提交失败, 响应解析异常");
        }

        if (root.hasNonNull("code")) {
            throw new RuntimeException("DashScope 图片提交逻辑错误, 响应: " + truncate(responseBody, 300));
        }

        JsonNode taskIdNode = root.path("output").path("task_id");
        if (taskIdNode.isMissingNode() || taskIdNode.isNull() || taskIdNode.asText().isBlank()) {
            throw new RuntimeException("DashScope 图片提交失败, 未返回 task_id, 响应: " + truncate(responseBody, 300));
        }

        return new SubmitResult(taskIdNode.asText());
    }

    @Override
    public PollResult poll(String apiKey, String apiBase, String taskId) {
        String url = base(apiBase) + "/api/v1/tasks/" + taskId;
        Map.Entry<String, String> credential = auth(apiKey, url);
        if (credential == null) {
            throw new IllegalStateException("未配置密钥：请先在通道管理填写该供应商的 API Key");
        }
        String authHeader = credential.getValue();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(15))
                .header("Authorization", authHeader)
                .GET()
                .build();

        ByokHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            throw new RuntimeException("DashScope 图片轮询失败, 网络不可达：请求发送失败");
        }

        int code = response.statusCode();
        String responseBody = response.body() == null ? "" : response.body();

        if (code < 200 || code >= 300) {
            throw new RuntimeException("DashScope 图片轮询失败, HTTP " + code + ", 响应: " + truncate(responseBody, 300));
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(responseBody);
        } catch (Exception e) {
            throw new RuntimeException("DashScope 图片轮询失败, 响应解析异常");
        }

        String status = root.path("output").path("task_status").asText("");
        switch (status) {
            case "SUCCEEDED": {
                JsonNode results = root.path("output").path("results");
                if (!results.isArray() || results.isEmpty()) {
                    throw new RuntimeException("DashScope 图片轮询失败, 成功响应缺少 results, 响应: " + truncate(responseBody, 300));
                }
                JsonNode urlNode = results.get(0).path("url");
                if (urlNode.isMissingNode() || urlNode.isNull() || urlNode.asText().isBlank()) {
                    throw new RuntimeException("DashScope 图片轮询失败, 成功响应缺少图片 URL, 响应: " + truncate(responseBody, 300));
                }
                return new PollResult(RemoteStatus.SUCCEEDED, urlNode.asText(), null, 100);
            }
            case "FAILED": {
                JsonNode message = root.path("output").path("message");
                String errorMessage = message.isMissingNode() || message.isNull() ? null : message.asText();
                return new PollResult(RemoteStatus.FAILED, null, errorMessage, 100);
            }
            case "PENDING":
            case "RUNNING":
                return new PollResult(RemoteStatus.PROCESSING, null, null, 50);
            case "UNKNOWN":
                return new PollResult(RemoteStatus.QUEUED, null, null, 0);
            default:
                return new PollResult(RemoteStatus.QUEUED, null, null, 0);
        }
    }

    @Override
    public ConnectivityResult probe(String apiKey, String apiBase) {
        String url = base(apiBase) + "/api/v1/tasks/" + PROBE_TASK_ID;
        Map.Entry<String, String> credential = auth(apiKey, url);
        if (credential == null) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.AUTH_FAILED,
                    "未配置密钥：请先在通道管理填写该供应商的 API Key");
        }
        String authHeader = credential.getValue();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(15))
                .header("Authorization", authHeader)
                .GET()
                .build();

        ByokHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.UNREACHABLE, "网络不可达：请求发送失败");
        }

        int code = response.statusCode();
        if (code == 404) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.OK, "密钥有效，链路畅通");
        }
        if (code == 401 || code == 403) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.AUTH_FAILED, "密钥无效或鉴权失败");
        }
        if (code == 429) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.RATE_LIMITED, "触发提供方限流，请稍后再试");
        }
        if (code >= 200 && code < 300) {
            return new ConnectivityResult(VideoProvider.ConnectivityStatus.OK, "密钥有效，链路畅通");
        }
        return new ConnectivityResult(VideoProvider.ConnectivityStatus.PROVIDER_ERROR, "服务方返回异常状态码：" + code);
    }

    private String truncate(String value, int maxLength) {
        if (value == null) {
            return "";
        }
        if (value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }
}
