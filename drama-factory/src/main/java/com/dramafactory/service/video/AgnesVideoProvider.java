package com.dramafactory.service.video;

import com.dramafactory.model.Shot;


import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
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

/**
 * Agnes 视频生成 API 对接实现。
 * 负责向 Agnes 提交视频生成任务并轮询任务状态。
 */
@Component("agnesRawVideoProvider")
public class AgnesVideoProvider implements VideoProvider {

    /** Agnes 视频生成接口地址（提交任务）。 */
    private static final String SUBMIT_URL = "https://apihub.agnes-ai.com/v1/videos";

    /** Agnes 任务查询接口基础地址。 */
    private static final String QUERY_BASE = "https://apihub.agnes-ai.com/agnesapi";

    /** 使用的模型名称。 */
    private static final String MODEL = "agnes-video-2.5-flash";

    /** 代理鉴权客户端，用于注入请求头。 */
    private final SurrogateAuthClient surrogateAuthClient;

    /** HTTP 客户端，连接超时 15 秒。 */
    private final HttpClient httpClient;

    /** JSON 序列化/反序列化工具。 */
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 构造器注入代理鉴权客户端，并初始化 HTTP 客户端。
     *
     * @param surrogateAuthClient 代理鉴权客户端
     */
    public AgnesVideoProvider(SurrogateAuthClient surrogateAuthClient) {
        this.surrogateAuthClient = surrogateAuthClient;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();
    }

    @Override
    public String name() {
        return "agnes";
    }

    /**
     * 提交视频生成任务。
     * prompt 优先取 shot.getVideoPrompt()，为空则用描述 + 景别 + 运镜拼接。
     *
     * @param shot    镜头实体
     * @param seconds 期望时长（秒）
     * @return Agnes 返回的任务 ID
     */
    @Override
    public String submit(Shot shot, int seconds) {
        // 组装提示词
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

        // 构造请求体
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", MODEL);
        body.put("prompt", prompt);
        body.put("seconds", String.valueOf(seconds));
        body.put("mode", "text");
        body.put("size", "720P");
        body.put("aspect_ratio", "16:9");

        String jsonBody;
        try {
            jsonBody = objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            throw new RuntimeException("序列化 Agnes 请求体失败: " + e.getMessage(), e);
        }

        // 构建 HTTP 请求
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(SUBMIT_URL))
                .timeout(Duration.ofSeconds(60))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8));

        // 注入鉴权头
        Map.Entry<String, String> auth = surrogateAuthClient.authHeader(SUBMIT_URL);
        builder.header(auth.getKey(), auth.getValue());

        HttpResponse<String> response;
        try {
            response = httpClient.send(builder.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new RuntimeException("请求 Agnes 提交接口失败: " + e.getMessage(), e);
        }

        int status = response.statusCode();
        // 限流处理
        if (status == 429) {
            throw new RateLimitedException("agnes 限流", 60);
        }
        // 其他非 2xx 抛异常，附带响应体前 300 字符
        if (status < 200 || status >= 300) {
            String resp = response.body();
            String snippet = resp == null ? "" : resp.substring(0, Math.min(300, resp.length()));
            throw new RuntimeException("Agnes 提交失败，状态码: " + status + "，响应: " + snippet);
        }

        // 解析返回，取 video_id，无则取 id
        try {
            JsonNode root = objectMapper.readTree(response.body());
            JsonNode idNode = root.get("video_id");
            if (idNode == null || idNode.isNull()) {
                idNode = root.get("id");
            }
            if (idNode == null || idNode.isNull()) {
                throw new RuntimeException("Agnes 提交响应缺少 video_id/id 字段");
            }
            return idNode.asText();
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("解析 Agnes 提交响应失败: " + e.getMessage(), e);
        }
    }

    /**
     * 轮询任务状态。
     *
     * @param providerTaskId Agnes 返回的任务 ID
     * @return 轮询结果
     */
    @Override
    public ProbeResult poll(String providerTaskId) {
        // URL 编码参数
        String encodedId = URLEncoder.encode(providerTaskId, StandardCharsets.UTF_8);
        String encodedModel = URLEncoder.encode(MODEL, StandardCharsets.UTF_8);
        String url = QUERY_BASE + "?video_id=" + encodedId + "&model_name=" + encodedModel;

        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(60))
                .GET();

        // 注入鉴权头
        Map.Entry<String, String> auth = surrogateAuthClient.authHeader(url);
        builder.header(auth.getKey(), auth.getValue());

        HttpResponse<String> response;
        try {
            response = httpClient.send(builder.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new RuntimeException("请求 Agnes 查询接口失败: " + e.getMessage(), e);
        }

        int status = response.statusCode();
        // 限流处理
        if (status == 429) {
            throw new RateLimitedException("agnes 限流", 60);
        }
        if (status < 200 || status >= 300) {
            String resp = response.body();
            String snippet = resp == null ? "" : resp.substring(0, Math.min(300, resp.length()));
            throw new RuntimeException("Agnes 查询失败，状态码: " + status + "，响应: " + snippet);
        }

        // 解析状态
        try {
            JsonNode root = objectMapper.readTree(response.body());
            JsonNode statusNode = root.get("status");
            String statusText = statusNode == null || statusNode.isNull() ? "" : statusNode.asText();

            if ("completed".equalsIgnoreCase(statusText)) {
                // 取视频地址：优先 metadata.url，其次 url
                String videoUrl = null;
                JsonNode metadata = root.get("metadata");
                if (metadata != null && !metadata.isNull()) {
                    JsonNode urlNode = metadata.get("url");
                    if (urlNode != null && !urlNode.isNull()) {
                        videoUrl = urlNode.asText();
                    }
                }
                if (videoUrl == null) {
                    JsonNode urlNode = root.get("url");
                    if (urlNode != null && !urlNode.isNull()) {
                        videoUrl = urlNode.asText();
                    }
                }
                return new ProbeResult(RemoteStatus.COMPLETED, videoUrl, null, 100);
            } else if ("failed".equalsIgnoreCase(statusText)) {
                // 取错误信息：优先 message，其次 error
                String errorMessage = null;
                JsonNode msgNode = root.get("message");
                if (msgNode != null && !msgNode.isNull()) {
                    errorMessage = msgNode.asText();
                } else {
                    JsonNode errNode = root.get("error");
                    if (errNode != null && !errNode.isNull()) {
                        errorMessage = errNode.asText();
                    }
                }
                return new ProbeResult(RemoteStatus.FAILED, null, errorMessage, 0);
            } else {
                // 处理中，尽量解析 progress
                int progress = 0;
                JsonNode progressNode = root.get("progress");
                if (progressNode != null && !progressNode.isNull()) {
                    if (progressNode.isNumber()) {
                        progress = progressNode.asInt();
                    } else {
                        try {
                            progress = Integer.parseInt(progressNode.asText().trim());
                        } catch (NumberFormatException ignored) {
                            progress = 0;
                        }
                    }
                }
                return new ProbeResult(RemoteStatus.PROCESSING, null, null, progress);
            }
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("解析 Agnes 查询响应失败: " + e.getMessage(), e);
        }
    }
}
