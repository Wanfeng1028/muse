package com.dramafactory.service.video;

import com.dramafactory.service.CredentialResolver;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.Map;

/**
 * 用户本地部署的 H3 视频生成服务 Provider。
 *
 * <p>设计原则：我们只提供 Provider 接口，不规定用户本地怎么部署。
 * 用户可以用 ComfyUI+H3-Continuum、自己写的 server.py、或其他任何实现，
 * <b>只要本地服务兼容 MiniMax 视频 API 的接口格式</b>：
 * <ul>
 *   <li>提交：POST {baseUrl}/v1/video_generation
 *       body {"model":"MiniMax-H3","prompt":"...","duration":6,"resolution":"768P"}
 *       → 返回 {"task_id":"...","base_resp":{"status_code":0}}</li>
 *   <li>查询：GET {baseUrl}/v1/query/video_generation/{task_id}
 *       → 返回 {"status":"processing"|"success"|"failed",...}</li>
 * </ul>
 *
 * <p>配置项：
 * <ul>
 *   <li>{@code drama.video.local-h3.base-url}：本地服务地址，如 http://localhost:8188（必填）</li>
 *   <li>{@code drama.video.local-h3.api-key}：本地服务密钥（可选，不配则不带鉴权头）</li>
 * </ul>
 *
 * <p>提交/查询/轮询的完整逻辑复用父类 {@link MiniMaxH3VideoProvider}，
 * 这里只覆盖：服务名、鉴权方式（可选密钥）、baseUrl 必填校验。
 */
@Component("localH3VideoProvider")
public class LocalH3Provider extends MiniMaxH3VideoProvider {

    private final String apiKey;

    @Autowired
    public LocalH3Provider(
            CredentialResolver credentialResolver,
            @Value("${drama.video.local-h3.base-url:}") String baseUrl,
            @Value("${drama.video.local-h3.api-key:}") String apiKey,
            @Value("${drama.video.minimax.model:MiniMax-H3}") String model,
            @Value("${drama.video.minimax.resolution:768P}") String resolution) {
        this(credentialResolver, baseUrl, apiKey, model, resolution, null);
    }

    /**
     * 测试用构造器：注入录制回放的假网关（包可见，不许改成 public）。
     */
    LocalH3Provider(CredentialResolver credentialResolver, String baseUrl, String apiKey,
                    String model, String resolution, VideoHttpGateway gateway) {
        super(credentialResolver, baseUrl, model, resolution, gateway);
        this.apiKey = apiKey == null ? "" : apiKey.strip();
    }

    @Override
    public String name() {
        return "local-h3";
    }

    @Override
    protected Map.Entry<String, String> resolveAuth() {
        if (!apiKey.isEmpty()) {
            return Map.entry("Authorization", "Bearer " + apiKey);
        }
        // 本地服务可能不需要鉴权：允许无鉴权头请求
        return null;
    }

    @Override
    protected String missingKeyMessage() {
        // 本地版不强制要求密钥
        return null;
    }

    @Override
    protected void ensureConfigured() {
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new IllegalStateException(
                    "未配置本地 H3 服务地址：请设置 drama.video.local-h3.base-url，"
                            + "指向你本地部署的 MiniMax 兼容视频服务（如 http://localhost:8188）");
        }
    }

    @Override
    public ConnectivityResult probeConnectivity() {
        try {
            ensureConfigured();
        } catch (IllegalStateException e) {
            return new ConnectivityResult(ConnectivityStatus.AUTH_FAILED, e.getMessage());
        }
        return super.probeConnectivity();
    }
}
