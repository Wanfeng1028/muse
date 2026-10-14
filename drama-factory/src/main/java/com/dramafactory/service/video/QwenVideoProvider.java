package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.CredentialResolver;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

/**
 * 通义万相（Qwen / DashScope）视频生成 Provider 实现。
 * 提交视频合成任务（异步）并轮询任务状态。
 */
@Component("qwenVideoProvider")
public class QwenVideoProvider implements VideoProvider {

    /** 提交任务接口地址 */
    private static final String SUBMIT_URL =
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis";

    /** 查询任务接口前缀 */
    private static final String TASK_URL_PREFIX =
            "https://dashscope.aliyuncs.com/api/v1/tasks/";

    /** 模型名称 */
    private static final String MODEL = "wan2.5-t2v-preview";

    /** 视频尺寸（16:9，已实测可提交） */
    private static final String SIZE = "832*480";


    private final CredentialResolver credentialResolver;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    /** HTTP 发送接缝：生产走真实客户端，测试可注入录制回放。 */
    private final VideoHttpGateway gateway;

    @Autowired
    public QwenVideoProvider(CredentialResolver credentialResolver, ObjectMapper objectMapper) {
        this(credentialResolver, objectMapper, null);
    }

    /**
     * 测试用构造器：注入录制回放的假网关（包可见，不许改成 public）。
     *
     * @param credentialResolver 凭证解析器
     * @param objectMapper       JSON 工具
     * @param gateway            为 null 时使用基于 httpClient 的默认网关
     */
    QwenVideoProvider(CredentialResolver credentialResolver, ObjectMapper objectMapper, VideoHttpGateway gateway) {
        this.credentialResolver = credentialResolver;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();
        this.gateway = gateway != null ? gateway : defaultGateway(this.httpClient);
    }

    /**
     * 基于真实 HttpClient 的默认网关。
     */
    private static VideoHttpGateway defaultGateway(HttpClient client) {
        return request -> {
            HttpResponse<String> resp = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            return new VideoHttpGateway.GatewayResponse(resp.statusCode(), resp.body());
        };
    }



    @Override
    public String name() {
        return "qwen";
    }

    @Override
    public String submit(Shot shot, int seconds) {
        // 构造 prompt：优先使用 videoPrompt，否则拼接 description、景别、运镜中文标签
        String prompt = shot.getVideoPrompt();
        if (prompt == null || prompt.isBlank()) {
            StringBuilder sb = new StringBuilder();
            if (shot.getDescription() != null && !shot.getDescription().isBlank()) {
                sb.append(shot.getDescription());
            }
            if (shot.getShotSize() != null) {
                if (sb.length() > 0) {
                    sb.append("，");
                }
                sb.append(shot.getShotSize().getLabel());
            }
            if (shot.getCameraMove() != null) {
                if (sb.length() > 0) {
                    sb.append("，");
                }
                sb.append(shot.getCameraMove().getLabel());
            }
            prompt = sb.toString();
        }

        // 构造请求 JSON 体
        ObjectNode root = objectMapper.createObjectNode();
        root.put("model", MODEL);

        ObjectNode input = root.putObject("input");
        input.put("prompt", prompt);

        ObjectNode parameters = root.putObject("parameters");
        parameters.put("size", SIZE);
        parameters.put("duration", seconds);
        parameters.put("prompt_extend", true);
        parameters.put("watermark", false);

        String requestBody;
        try {
            requestBody = objectMapper.writeValueAsString(root);
        } catch (Exception e) {
            throw new RuntimeException("构造通义万相请求体失败: " + e.getMessage(), e);
        }

        // 注入鉴权头（不打印任何凭证）
        Map.Entry<String, String> auth = credentialResolver.dashscopeAuth(SUBMIT_URL);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(SUBMIT_URL))
                .timeout(Duration.ofSeconds(60))
                .header("Content-Type", "application/json")
                .header("X-DashScope-Async", "enable")
                .header(auth.getKey(), auth.getValue())
                .POST(HttpRequest.BodyPublishers.ofString(requestBody, StandardCharsets.UTF_8))
                .build();

        VideoHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            throw new RuntimeException("通义万相提交任务请求失败: " + e.getMessage(), e);
        }

        String body = response.body() == null ? "" : response.body();



        // 非 2xx 直接抛出
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RuntimeException("通义万相提交任务失败, HTTP " + response.statusCode()
                    + ", 响应: " + truncate(body, 300));
        }

        JsonNode json;
        try {
            json = objectMapper.readTree(body);
        } catch (Exception e) {
            throw new RuntimeException("解析通义万相响应失败, HTTP " + response.statusCode()
                    + ", 响应: " + truncate(body, 300), e);
        }

        // DashScope 逻辑错误：响应体含 code 字段
        if (json.has("code")) {
            throw new RuntimeException("通义万相提交任务逻辑错误, HTTP " + response.statusCode()
                    + ", 响应: " + truncate(body, 300));
        }

        JsonNode taskIdNode = json.path("output").path("task_id");
        if (taskIdNode.isMissingNode() || taskIdNode.isNull() || taskIdNode.asText().isBlank()) {
            throw new RuntimeException("通义万相提交任务未返回 task_id, HTTP " + response.statusCode()
                    + ", 响应: " + truncate(body, 300));
        }
        return taskIdNode.asText();
    }

    @Override
    public ProbeResult poll(String providerTaskId) {
        // 对 task id 做 URL 编码
        String encodedId = URLEncoder.encode(providerTaskId, StandardCharsets.UTF_8);
        String url = TASK_URL_PREFIX + encodedId;

        // 注入鉴权头（不打印任何凭证）
        Map.Entry<String, String> auth = credentialResolver.dashscopeAuth(url);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(60))
                .header(auth.getKey(), auth.getValue())
                .GET()
                .build();

        VideoHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(request);
        } catch (Exception e) {
            throw new RuntimeException("通义万相查询任务请求失败: " + e.getMessage(), e);
        }

        String body = response.body() == null ? "" : response.body();


        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RuntimeException("通义万相查询任务失败, HTTP " + response.statusCode()
                    + ", 响应: " + truncate(body, 300));
        }

        JsonNode json;
        try {
            json = objectMapper.readTree(body);
        } catch (Exception e) {
            throw new RuntimeException("解析通义万相查询响应失败, HTTP " + response.statusCode()
                    + ", 响应: " + truncate(body, 300), e);
        }

        if (json.has("code")) {
            throw new RuntimeException("通义万相查询任务逻辑错误, HTTP " + response.statusCode()
                    + ", 响应: " + truncate(body, 300));
        }

        JsonNode output = json.path("output");
        String taskStatus = output.path("task_status").asText("");

        switch (taskStatus) {
            case "SUCCEEDED": {
                String videoUrl = output.path("video_url").asText(null);
                return new ProbeResult(RemoteStatus.COMPLETED, videoUrl, null, 100);
            }
            case "FAILED":
            case "CANCELED": {
                String message = output.path("message").asText(null);
                return new ProbeResult(RemoteStatus.FAILED, null, message, 0);
            }
            default:
                return new ProbeResult(RemoteStatus.PROCESSING, null, null, 0);
        }
    }

    /**
     * 截断字符串，避免日志/异常信息过长。
     */
    private static String truncate(String text, int maxLen) {
        if (text == null) {
            return "";
        }
        if (text.length() <= maxLen) {
            return text;
        }
        return text.substring(0, maxLen);
    }
}
