package com.dramafactory.service.video;

import com.dramafactory.service.SettingsService;
import org.springframework.stereotype.Component;

/**
 * 解析描述符中的 keyRef，支持 env:VAR 与 settings:xxx 两种来源。
 * 返回值为密钥明文，仅可在请求装配处使用，禁止写入日志或异常信息。
 */
@Component
public class DescriptorSecretResolver {

    private final SettingsService settingsService;

    public DescriptorSecretResolver(SettingsService settingsService) {
        this.settingsService = settingsService;
    }

    /**
     * 解析 keyRef。
     *
     * @param keyRef 形如 env:VAR 或 settings:xxx
     * @return 密钥明文
     */
    public String resolve(String keyRef) {
        if (keyRef == null) {
            throw new IllegalArgumentException("不支持的 keyRef 格式: " + keyRef);
        }
        if (keyRef.startsWith("env:")) {
            return System.getenv(keyRef.substring("env:".length()));
        }
        if (keyRef.startsWith("settings:")) {
            return settingsService.loadAll().get(keyRef.substring("settings:".length()));
        }
        throw new IllegalArgumentException("不支持的 keyRef 格式: " + keyRef);
    }
}

