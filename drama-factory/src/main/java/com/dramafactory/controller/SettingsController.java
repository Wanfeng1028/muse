package com.dramafactory.controller;

import com.dramafactory.service.SettingsService;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * 设置中心接口。
 */
@RestController
@RequestMapping("/api/settings")
public class SettingsController {

    private final SettingsService settingsService;
    private final Environment environment;

    public SettingsController(SettingsService settingsService, Environment environment) {
        this.settingsService = settingsService;
        this.environment = environment;
    }

    /**
     * 获取 schema 与掩码后的值。
     *
     * @return {schema, values}
     */
    @GetMapping("")
    public Map<String, Object> get() {
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("schema", settingsService.schema());
        resp.put("values", settingsService.maskedView());
        return resp;
    }

    /**
     * 保存设置（secret 空串表示保持原值）。
     *
     * @param patch 待保存的键值对
     * @return 掩码视图；非法键返回 400
     */
    @PutMapping("")
    public ResponseEntity<Map<String, Object>> put(@RequestBody Map<String, String> patch) {
        Set<String> allowed = settingsService.allowedKeys();
        Map<String, String> cleaned = new LinkedHashMap<>();
        if (patch != null) {
            for (Map.Entry<String, String> e : patch.entrySet()) {
                String key = e.getKey();
                if (key == null || !allowed.contains(key)) {
                    return ResponseEntity.badRequest().body(Map.of("error", "非法设置键: " + key));
                }
                String value = e.getValue();
                if (SettingsService.SECRET_KEYS.contains(key) && (value == null || value.isBlank())) {
                    // secret 空串 = 保持原值，不传给 service
                    continue;
                }
                cleaned.put(key, value);
            }
        }
        settingsService.saveAll(cleaned);
        return ResponseEntity.ok(settingsService.maskedView());
    }

    /**
     * 获取当前生效的视频通道。
     *
     * @return {provider}
     */
    @GetMapping("/effective-provider")
    public Map<String, Object> effectiveProvider() {
        String provider = environment.getProperty("drama.video.provider", "mock");
        return Map.of("provider", provider);
    }
}
