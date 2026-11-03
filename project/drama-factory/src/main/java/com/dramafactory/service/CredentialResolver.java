package com.dramafactory.service;

import com.dramafactory.service.video.SurrogateAuthClient;
import org.springframework.stereotype.Service;

import java.util.Map;

/**
 * 凭证解析器：优先使用用户在设置中心填写的 API Key，否则回退到 SurrogateAuthClient。
 *
 * <p>密钥仅从设置文件读取，绝不打印到日志。</p>
 */
@Service
public class CredentialResolver {

    private final SettingsService settingsService;
    private final SurrogateAuthClient surrogateAuthClient;

    public CredentialResolver(SettingsService settingsService, SurrogateAuthClient surrogateAuthClient) {
        this.settingsService = settingsService;
        this.surrogateAuthClient = surrogateAuthClient;
    }

    /**
     * 解析聊天模型鉴权头。
     *
     * @return Authorization 头；无凭证时返回 null
     */
    public Map.Entry<String, String> chatAuth() {
        String key = readKey("deepseek.api-key");
        if (key != null) {
            return Map.entry("Authorization", "Bearer " + key);
        }
        return surrogateAuthClient.authHeader(
                "https://chatapi.weixin.qq.com/openai/v1/chat/completions",
                "custom.weixin-chatapi");
    }

    /**
     * 解析 DashScope 鉴权头。
     *
     * @param url 目标地址
     * @return Authorization 头；无凭证时返回 null
     */
    public Map.Entry<String, String> dashscopeAuth(String url) {
        String key = readKey("dashscope.api-key");
        if (key != null) {
            return Map.entry("Authorization", "Bearer " + key);
        }
        return surrogateAuthClient.authHeader(url, "custom.qwen-cloud-cn");
    }

    /**
     * 解析 Agnes 鉴权头。
     *
     * @param url 目标地址
     * @return Authorization 头；无凭证时返回 null
     */
    public Map.Entry<String, String> agnesAuth(String url) {
        String key = readKey("agnes.api-key");
        if (key != null) {
            return Map.entry("Authorization", "Bearer " + key);
        }
        return surrogateAuthClient.authHeader(url);
    }

    /**
     * 解析 NovAI 鉴权头。
     *
     * @param url 目标地址
     * @return Authorization 头；无凭证时走 surrogate 通道（custom.novai-api）
     */
    public Map.Entry<String, String> novaiAuth(String url) {
        String key = readKey("novai.api-key");
        if (key != null) {
            return Map.entry("Authorization", "Bearer " + key);
        }
        return surrogateAuthClient.authHeader(url, "custom.novai-api");
    }

    /**
     * 解析 DashScope BYOK 鉴权头：卡片 key → 设置中心 → surrogate。
     */
    public Map.Entry<String, String> dashscopeByokAuth(String cardKey, String url) {
        if (cardKey != null && !cardKey.isBlank()) {
            return Map.entry("Authorization", "Bearer " + cardKey.trim());
        }
        String key = readKey("dashscope.api-key");
        if (key != null) {
            return Map.entry("Authorization", "Bearer " + key);
        }
        return surrogateAuthClient.authHeader(url, "custom.qwen-cloud-cn");
    }

    /**
     * 解析 MiniMax 鉴权头：仅卡片 key 与设置中心 key，无 surrogate 通道。
     */
    public Map.Entry<String, String> minimaxAuth(String cardKey) {
        String key = (cardKey != null && !cardKey.isBlank()) ? cardKey.trim() : readKey("minimax.api-key");
        if (key != null) {
            return Map.entry("Authorization", "Bearer " + key);
        }
        return null;
    }

    /**
     * 解析 D-ID 鉴权头（Basic，用户名为 key）：仅卡片 key 与设置中心 key，无 surrogate 通道。
     */
    public Map.Entry<String, String> didAuth(String cardKey) {
        String key = (cardKey != null && !cardKey.isBlank()) ? cardKey.trim() : readKey("did.api-key");
        if (key == null) {
            return null;
        }
        String basic = java.util.Base64.getEncoder()
                .encodeToString((key + ":").getBytes(java.nio.charset.StandardCharsets.UTF_8));
        return Map.entry("Authorization", "Basic " + basic);
    }

    private String readKey(String settingKey) {
        Map<String, String> all = settingsService.loadAll();
        String value = all.get(settingKey);
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }
}
