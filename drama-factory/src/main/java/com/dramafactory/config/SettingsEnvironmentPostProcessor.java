package com.dramafactory.config;

import com.dramafactory.service.SettingsService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 将 data/settings.json 中的扁平键值对注入 Spring Environment。
 *
 * <p>优先级：环境变量(systemEnvironment) &gt; settings.json &gt; application.yml。
 * 通过 addAfter("systemEnvironment", ...) 实现。文件不存在则静默跳过。
 * 绝不打印文件内容到日志。</p>
 */
public class SettingsEnvironmentPostProcessor implements EnvironmentPostProcessor {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment, SpringApplication application) {
        Path path = Paths.get(SettingsService.SETTINGS_PATH);
        if (!Files.isRegularFile(path)) {
            return;
        }
        Map<String, Object> flat;
        try {
            JsonNode root = MAPPER.readTree(Files.readAllBytes(path));
            if (root == null || !root.isObject()) {
                return;
            }
            flat = new LinkedHashMap<>();
            root.fields().forEachRemaining(e -> {
                String key = e.getKey();
                JsonNode v = e.getValue();
                if (key == null || key.isBlank() || v == null || v.isNull()) {
                    return;
                }
                String value = v.isTextual() ? v.asText() : v.toString();
                flat.put(key, value);
            });
        } catch (IOException e) {
            // 静默跳过，不打印内容
            return;
        }
        if (flat.isEmpty()) {
            return;
        }
        MapPropertySource source = new MapPropertySource("settingsJson", flat);
        if (environment.getPropertySources().contains("systemEnvironment")) {
            environment.getPropertySources().addAfter("systemEnvironment", source);
        } else {
            environment.getPropertySources().addLast(source);
        }
    }
}
