package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

/**
 * 由 {@link ProviderDescriptor} 驱动的视频提供方实现。
 * 所有 HTTP 交互经 {@link VideoHttpGateway}，便于测试注入假网关。
 */
public class DescriptorVideoProvider implements VideoProvider {

    private static final int PREVIEW_LIMIT = 300;
    /**
     * 单次请求硬超时：厂商接口只 hang 不返回时，宁可快速失败走降级，
     * 也不让调用线程无限期阻塞。
     */
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(60);

    private final ProviderDescriptor descriptor;
    private final ObjectMapper objectMapper;
    private final VideoHttpGateway gateway;
    private final Supplier<String> apiKeySupplier;

    public DescriptorVideoProvider(ProviderDescriptor descriptor, ObjectMapper objectMapper,
                                   VideoHttpGateway gateway, Supplier<String> apiKeySupplier) {
        if (descriptor == null) {
            throw new IllegalArgumentException("descriptor 不能为 null");
        }
        if (objectMapper == null) {
            throw new IllegalArgumentException("objectMapper 不能为 null");
        }
        if (gateway == null) {
            throw new IllegalArgumentException("gateway 不能为 null");
        }
        if (apiKeySupplier == null) {
            throw new IllegalArgumentException("apiKeySupplier 不能为 null");
        }
        descriptor.validate();
        this.descriptor = descriptor;
        this.objectMapper = objectMapper;
        this.gateway = gateway;
        this.apiKeySupplier = apiKeySupplier;
    }

    @Override
    public String name() {
        return "descriptor:" + descriptor.getId();
    }

    @Override
    public String submit(Shot shot, int seconds) {
        String prompt = shot.getVideoPrompt();
        if (prompt == null || prompt.isBlank()) {
            prompt = shot.getDescription();
        }
        if (prompt == null) {
            prompt = "";
        }
        ProviderDescriptor.DescriptorModel chosen = null;
        if (descriptor.getModels() != null) {
            for (ProviderDescriptor.DescriptorModel m : descriptor.getModels()) {
                if ("video".equals(m.getType())) {
                    chosen = m;
                    break;
                }
            }
        }
        String model = chosen == null || chosen.getId() == null ? "" : chosen.getId();

        List<String> violations = new VideoRequestValidator().validate(chosen, prompt, seconds);
        if (!violations.isEmpty()) {
            throw new VideoRequestConstraintException(
                    "视频请求参数违反通道硬约束：" + String.join("；", violations), violations);
        }

        Map<String, String> vars = new HashMap<>();
        vars.put("prompt", prompt);
        vars.put("seconds", String.valueOf(seconds));
        vars.put("model", model);

        String key = apiKeySupplier.get();
        if (key == null || key.isBlank()) {
            throw new IllegalStateException("描述符 " + descriptor.getId()
                    + " 未配置 API Key（keyRef=" + keyRefOf() + "）");
        }

        ProviderDescriptor.DescriptorEndpoint submit = descriptor.getSubmit();
        String url = renderTemplate(submit.getUrl(), vars);
        String body = renderTemplate(submit.getBody(), vars);
        String method = submit.getMethod() == null || submit.getMethod().isBlank()
                ? "POST" : submit.getMethod();

        HttpRequest.Builder builder = HttpRequest.newBuilder().uri(URI.create(url))
                .timeout(REQUEST_TIMEOUT);
        if (submit.getHeaders() != null) {
            for (Map.Entry<String, String> e : submit.getHeaders().entrySet()) {
                builder.header(e.getKey(), renderTemplate(e.getValue(), vars));
            }
        }
        applyAuth(builder, key);

        if ("GET".equalsIgnoreCase(method)) {
            builder.GET();
        } else if ("POST".equalsIgnoreCase(method)) {
            builder.POST(HttpRequest.BodyPublishers.ofString(body == null ? "" : body, StandardCharsets.UTF_8));
        } else {
            builder.method(method, HttpRequest.BodyPublishers.ofString(body == null ? "" : body, StandardCharsets.UTF_8));
        }

        VideoHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(builder.build());
        } catch (Exception e) {
            throw new RuntimeException("调用描述符通道失败: " + e.getMessage());
        }
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RuntimeException("提交失败，状态码 " + response.statusCode()
                    + "，响应: " + preview(response.body(), key));
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(response.body() == null ? "" : response.body());
        } catch (Exception e) {
            throw new RuntimeException("提交响应解析失败: " + e.getMessage());
        }
        JsonNode node = ProviderDescriptor.resolvePath(root, submit.getTaskIdPath());
        String taskId = node == null ? null : node.asText();
        if (taskId == null || taskId.isBlank()) {
            throw new RuntimeException("提交响应中未找到任务 ID（路径 " + submit.getTaskIdPath() + "）");
        }
        return taskId;
    }

    @Override
    public ProbeResult poll(String providerTaskId) {
        ProviderDescriptor.DescriptorPollEndpoint poll = descriptor.getPoll();
        Map<String, String> vars = new HashMap<>();
        vars.put("taskId", providerTaskId == null ? "" : providerTaskId);
        String url = renderTemplate(poll.getUrl(), vars);
        String method = poll.getMethod() == null || poll.getMethod().isBlank() ? "GET" : poll.getMethod();

        String key = apiKeySupplier.get();
        HttpRequest.Builder builder = HttpRequest.newBuilder().uri(URI.create(url))
                .timeout(REQUEST_TIMEOUT);
        if (key != null && !key.isBlank()) {
            applyAuth(builder, key);
        }
        if ("GET".equalsIgnoreCase(method)) {
            builder.GET();
        } else if (poll.getBody() != null && !poll.getBody().isBlank()) {
            builder.header("Content-Type", "application/json");
            builder.method(method, HttpRequest.BodyPublishers.ofString(
                    renderTemplate(poll.getBody(), vars), StandardCharsets.UTF_8));
        } else {
            builder.method(method, HttpRequest.BodyPublishers.noBody());
        }

        VideoHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(builder.build());
        } catch (Exception e) {
            throw new RuntimeException("调用描述符通道失败: " + e.getMessage());
        }
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RuntimeException("轮询失败，状态码 " + response.statusCode()
                    + "，响应: " + preview(response.body(), key));
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(response.body() == null ? "" : response.body());
        } catch (Exception e) {
            throw new RuntimeException("轮询响应解析失败: " + e.getMessage());
        }

        JsonNode statusNode = ProviderDescriptor.resolvePath(root, poll.getStatusPath());
        String rawStatus = statusNode == null ? null : statusNode.asText();
        String mapped = poll.getStatusMap() == null ? null : poll.getStatusMap().get(rawStatus);
        RemoteStatus status;
        if (mapped == null) {
            status = RemoteStatus.PROCESSING;
        } else {
            try {
                status = RemoteStatus.valueOf(mapped);
            } catch (IllegalArgumentException e) {
                status = RemoteStatus.PROCESSING;
            }
        }

        int progress = 0;
        JsonNode progressNode = ProviderDescriptor.resolvePath(root, poll.getProgressPath());
        if (progressNode != null && progressNode.isNumber()) {
            progress = progressNode.asInt();
        } else if (progressNode != null && progressNode.isTextual()) {
            try {
                progress = Integer.parseInt(progressNode.asText().trim());
            } catch (NumberFormatException ignored) {
                progress = 0;
            }
        }
        if (progress < 0) {
            progress = 0;
        }
        if (progress > 100) {
            progress = 100;
        }

        if (status == RemoteStatus.COMPLETED) {
            JsonNode videoNode = ProviderDescriptor.resolvePath(root, poll.getVideoUrlPath());
            String videoUrl = videoNode == null ? null : videoNode.asText();
            if (videoUrl == null || videoUrl.isBlank()) {
                return new ProbeResult(RemoteStatus.FAILED, null, "提供方未返回视频地址", 0);
            }
            return new ProbeResult(RemoteStatus.COMPLETED, videoUrl, null, progress);
        }
        if (status == RemoteStatus.FAILED) {
            JsonNode errorNode = ProviderDescriptor.resolvePath(root, poll.getErrorPath());
            String errorMessage = errorNode == null ? null : errorNode.asText();
            if (errorMessage == null || errorMessage.isBlank()) {
                errorMessage = "提供方返回失败";
            } else {
                errorMessage = preview(errorMessage, key);
            }
            return new ProbeResult(RemoteStatus.FAILED, null, errorMessage, progress);
        }
        return new ProbeResult(status, null, null, progress);
    }

    private String keyRefOf() {
        return descriptor.getAuth() == null ? null : descriptor.getAuth().getKeyRef();
    }

    private void applyAuth(HttpRequest.Builder builder, String key) {
        ProviderDescriptor.DescriptorAuth auth = descriptor.getAuth();
        if (auth == null || auth.getType() == null || "none".equals(auth.getType())) {
            return;
        }
        if ("bearer".equals(auth.getType())) {
            builder.header("Authorization", "Bearer " + key);
            return;
        }
        if ("header".equals(auth.getType())) {
            String headerName = auth.getHeaderName() == null || auth.getHeaderName().isBlank()
                    ? "X-Api-Key" : auth.getHeaderName();
            builder.header(headerName, key);
        }
    }

    private static String preview(String body, String key) {
        if (body == null) {
            return "";
        }
        String text = body.length() > PREVIEW_LIMIT ? body.substring(0, PREVIEW_LIMIT) : body;
        if (key != null && !key.isBlank()) {
            text = text.replace(key, "****");
        }
        return text;
    }

    /**
     * 渲染模板：{{key}} 替换为 vars 中对应值，缺 key 替换成空串。
     *
     * @param template 模板文本
     * @param vars     变量表
     * @return 渲染结果，template 为 null 时返回 null
     */
    static String renderTemplate(String template, Map<String, String> vars) {
        if (template == null) {
            return null;
        }
        StringBuilder sb = new StringBuilder();
        int i = 0;
        while (i < template.length()) {
            int start = template.indexOf("{{", i);
            if (start < 0) {
                sb.append(template, i, template.length());
                break;
            }
            int end = template.indexOf("}}", start + 2);
            if (end < 0) {
                sb.append(template, i, template.length());
                break;
            }
            sb.append(template, i, start);
            String name = template.substring(start + 2, end).trim();
            String value = vars == null ? null : vars.get(name);
            sb.append(value == null ? "" : value);
            i = end + 2;
        }
        return sb.toString();
    }
}

