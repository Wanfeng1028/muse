package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.CredentialResolver;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
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
 * MiniMax H3 视频生成 API 对接实现（云端官方接口）。
 *
 * <p>官方接口（platform.minimax.io）：
 * <ul>
 *   <li>提交：POST {baseUrl}/v1/video_generation</li>
 *   <li>查询：GET {baseUrl}/v1/query/video_generation/{task_id}</li>
 * </ul>
 *
 * <p>H3 特性：4–15 秒/条，原生立体声音轨（对白 Shot 首选），支持 768P/1080P/2K。
 * 鉴权：Authorization: Bearer &lt;MiniMax API Key&gt;，经 {@link CredentialResolver#minimaxAuth} 解析。
 *
 * <p>本地部署版见子类 {@link LocalH3Provider}：同样的 MiniMax 兼容接口格式，
 * baseUrl 指向用户本地服务。
 */
@Component("miniMaxH3VideoProvider")
public class MiniMaxH3VideoProvider implements VideoProvider {

    /** 官方云端接口地址。 */
    private static final String CLOUD_BASE_URL = "https://api.minimax.io";

    /** H3 支持的最小时长（秒）。 */
    private static final int MIN_DURATION = 4;

    /** H3 支持的最大时长（秒）。 */
    private static final int MAX_DURATION = 15;

    /** 接口基地址（云端固定，本地版可配）。 */
    protected final String baseUrl;

    protected final CredentialResolver credentialResolver;
    private final HttpClient httpClient;
    private final VideoHttpGateway gateway;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 提交时使用的模型名，默认 MiniMax-H3（可切 MiniMax-Hailuo-2.3 降级为默片）。 */
    private final String model;

    /** 提交时使用的分辨率，默认 768P。 */
    private final String resolution;

    @Autowired
    public MiniMaxH3VideoProvider(
            CredentialResolver credentialResolver,
            @Value("${drama.video.minimax.model:MiniMax-H3}") String model,
            @Value("${drama.video.minimax.resolution:768P}") String resolution) {
        this(credentialResolver, CLOUD_BASE_URL, model, resolution, null);
    }

    /**
     * 测试用构造器：注入录制回放的假网关（包可见，不许改成 public）。
     */
    MiniMaxH3VideoProvider(CredentialResolver credentialResolver, String model,
                           String resolution, VideoHttpGateway gateway) {
        this(credentialResolver, CLOUD_BASE_URL, model, resolution, gateway);
    }

    /**
     * 子类构造器：允许覆盖 baseUrl（本地部署版用）。
     */
    protected MiniMaxH3VideoProvider(CredentialResolver credentialResolver, String baseUrl,
                                     String model, String resolution, VideoHttpGateway gateway) {
        this.credentialResolver = credentialResolver;
        this.baseUrl = baseUrl == null ? "" : baseUrl.strip().replaceAll("/$", "");
        this.model = model;
        this.resolution = resolution;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();
        this.gateway = gateway != null ? gateway : defaultGateway(this.httpClient);
    }

    private static VideoHttpGateway defaultGateway(HttpClient client) {
        return request -> {
            HttpResponse<String> resp = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            return new VideoHttpGateway.GatewayResponse(resp.statusCode(), resp.body());
        };
    }

    /**
     * 解析鉴权头。云端版走 CredentialResolver；本地版可重写（可选密钥）。
     *
     * @return 鉴权头；返回 null 表示不带鉴权头发请求
     */
    protected Map.Entry<String, String> resolveAuth() {
        return credentialResolver.minimaxAuth(null);
    }

    /**
     * 无可用鉴权头时的错误文案。返回 null 表示允许无鉴权请求（本地版）。
     */
    protected String missingKeyMessage() {
        return "未配置 MiniMax 密钥：请先在设置中心填写 minimax.api-key";
    }

    /**
     * 提交/查询前的前置校验钩子。本地版重写以校验 baseUrl 已配置。
     */
    protected void ensureConfigured() {
    }

    /** 负向探测用的不存在任务 ID：仅用于探测，零费用。 */
    private static final String PROBE_TASK_ID = "__connectivity_probe__";

    @Override
    public ConnectivityResult probeConnectivity() {
        ensureConfigured();
        String url = baseUrl + "/v1/query/video_generation/"
                + URLEncoder.encode(PROBE_TASK_ID, StandardCharsets.UTF_8);
        Map.Entry<String, String> auth = resolveAuth();
        if (auth == null && missingKeyMessage() != null) {
            return new ConnectivityResult(ConnectivityStatus.AUTH_FAILED, missingKeyMessage());
        }
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(15))
                .GET();
        if (auth != null) {
            builder.header(auth.getKey(), auth.getValue());
        }
        try {
            VideoHttpGateway.GatewayResponse resp = gateway.exchange(builder.build());
            int code = resp.statusCode();
            if (code == 401 || code == 403) {
                return new ConnectivityResult(ConnectivityStatus.AUTH_FAILED, "密钥无效或鉴权失败");
            }
            if (code == 429) {
                return new ConnectivityResult(ConnectivityStatus.RATE_LIMITED, "触发提供方限流，请稍后再试");
            }
            // 查询不存在的 task_id：只要不是鉴权失败/限流，即视为密钥有效、链路畅通
            // （MiniMax 对未知 task_id 返回业务错误码而非 404）
            if (code >= 200 && code < 500) {
                return new ConnectivityResult(ConnectivityStatus.OK, "密钥有效，链路畅通");
            }
            return new ConnectivityResult(ConnectivityStatus.PROVIDER_ERROR,
                    "服务方返回异常状态码：" + code);
        } catch (Exception e) {
            return new ConnectivityResult(ConnectivityStatus.UNREACHABLE,
                    "网络不可达：请求发送失败（DNS 解析 / 连接超时 / 连接被拒）");
        }
    }

    @Override
    public String name() {
        return "minimax";
    }

    @Override
    public String submit(Shot shot, int seconds) {
        ensureConfigured();
        String prompt = buildPrompt(shot);
        int duration = Math.max(MIN_DURATION, Math.min(MAX_DURATION, seconds));

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", model);
        body.put("prompt", prompt);
        body.put("duration", duration);
        body.put("resolution", resolution);

        String jsonBody;
        try {
            jsonBody = objectMapper.writeValueAsString(body);
        } catch (Exception e) {
            throw new RuntimeException("序列化 MiniMax 请求体失败: " + e.getMessage(), e);
        }

        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/v1/video_generation"))
                .timeout(Duration.ofSeconds(60))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8));

        applyAuth(builder, "提交");

        VideoHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(builder.build());
        } catch (Exception e) {
            throw new RuntimeException("请求 MiniMax 提交接口失败: " + e.getMessage(), e);
        }

        int status = response.statusCode();
        if (status == 429) {
            throw new RateLimitedException("minimax 限流", 60);
        }
        if (status < 200 || status >= 300) {
            String snippet = snippet(response.body());
            throw new RuntimeException("MiniMax 提交失败，状态码: " + status + "，响应: " + snippet);
        }

        try {
            JsonNode root = objectMapper.readTree(response.body());
            JsonNode taskIdNode = root.get("task_id");
            if (taskIdNode == null || taskIdNode.isNull()) {
                // 兼容 base_resp 包裹结构
                JsonNode baseResp = root.get("base_resp");
                if (baseResp != null && baseResp.get("status_code") != null
                        && baseResp.get("status_code").asInt() != 0) {
                    throw new RuntimeException("MiniMax 提交被拒: "
                            + baseResp.path("status_msg").asText("未知错误"));
                }
                throw new RuntimeException("MiniMax 提交响应缺少 task_id 字段");
            }
            return taskIdNode.asText();
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("解析 MiniMax 提交响应失败: " + e.getMessage(), e);
        }
    }

    @Override
    public ProbeResult poll(String providerTaskId) {
        ensureConfigured();
        String url = baseUrl + "/v1/query/video_generation/"
                + URLEncoder.encode(providerTaskId, StandardCharsets.UTF_8);

        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(60))
                .GET();

        applyAuth(builder, "查询");

        VideoHttpGateway.GatewayResponse response;
        try {
            response = gateway.exchange(builder.build());
        } catch (Exception e) {
            throw new RuntimeException("请求 MiniMax 查询接口失败: " + e.getMessage(), e);
        }

        int status = response.statusCode();
        if (status == 429) {
            throw new RateLimitedException("minimax 限流", 60);
        }
        if (status < 200 || status >= 300) {
            throw new RuntimeException("MiniMax 查询失败，状态码: " + status
                    + "，响应: " + snippet(response.body()));
        }

        try {
            JsonNode root = objectMapper.readTree(response.body());
            String statusText = root.path("status").asText("").toLowerCase();

            if ("success".equals(statusText)) {
                String videoUrl = root.path("file_id").asText(null);
                if (videoUrl == null || videoUrl.isBlank()) {
                    // 部分版本直接返回 download_url
                    videoUrl = root.path("download_url").asText(null);
                }
                if (videoUrl == null || videoUrl.isBlank()) {
                    // 回退：用 file_id 拼下载地址
                    String fileId = root.path("file_id").asText("");
                    videoUrl = fileId.isBlank() ? null
                            : baseUrl + "/v1/video_generation/file/" + fileId;
                }
                return new ProbeResult(RemoteStatus.COMPLETED, videoUrl, null, 100);
            }
            if ("failed".equals(statusText)) {
                String error = root.path("base_resp").path("status_msg").asText(null);
                if (error == null || error.isBlank()) {
                    error = "MiniMax 任务失败（未返回原因）";
                }
                return new ProbeResult(RemoteStatus.FAILED, null, error, 0);
            }
            // processing / preparing / queued 等一律视为生成中
            return new ProbeResult(RemoteStatus.PROCESSING, null, null, 50);
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("解析 MiniMax 查询响应失败: " + e.getMessage(), e);
        }
    }

    /**
     * 把鉴权头应用到请求上；无鉴权头且允许无鉴权时直接跳过。
     */
    private void applyAuth(HttpRequest.Builder builder, String op) {
        Map.Entry<String, String> auth = resolveAuth();
        if (auth == null) {
            String msg = missingKeyMessage();
            if (msg != null) {
                throw new IllegalStateException(msg);
            }
            return;
        }
        builder.header(auth.getKey(), auth.getValue());
    }

    /**
     * 组装提示词：优先取 shot.getVideoPrompt()，为空则用描述 + 景别 + 运镜拼接。
     * 与 AgnesVideoProvider 保持一致的拼接逻辑。
     */
    private static String buildPrompt(Shot shot) {
        String prompt = shot.getVideoPrompt();
        if (prompt != null && !prompt.isBlank()) {
            return prompt.strip();
        }
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
        return sb.toString();
    }

    private static String snippet(String body) {
        if (body == null) {
            return "";
        }
        return body.substring(0, Math.min(300, body.length()));
    }
}
