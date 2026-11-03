package com.dramafactory.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SettingsServiceTest {

    @TempDir
    Path tempDir;

    private SettingsService service;

    @BeforeEach
    void setUp() {
        // 用隔离路径，避免污染真实 data/settings.json（user.dir hack 对 Paths.get 无效）
        service = new SettingsService(tempDir.resolve("settings.json"));
    }

    @Test
    void saveAndLoadMerge() {
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("drama.video.provider", "qwen");
        patch.put("deepseek.model", "deepseek-chat");
        service.saveAll(patch);

        Map<String, String> loaded = service.loadAll();
        assertEquals("qwen", loaded.get("drama.video.provider"));
        assertEquals("deepseek-chat", loaded.get("deepseek.model"));

        // 删除非 secret 键
        Map<String, String> del = new LinkedHashMap<>();
        del.put("deepseek.model", "");
        service.saveAll(del);
        Map<String, String> after = service.loadAll();
        assertFalse(after.containsKey("deepseek.model"));
        assertEquals("qwen", after.get("drama.video.provider"));
    }

    @Test
    void secretEmptyKeepsOriginal() {
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("deepseek.api-key", "sk-abcdef123456");
        service.saveAll(patch);

        // secret 空串不覆盖
        Map<String, String> emptyPatch = new LinkedHashMap<>();
        emptyPatch.put("deepseek.api-key", "");
        service.saveAll(emptyPatch);

        Map<String, String> loaded = service.loadAll();
        assertEquals("sk-abcdef123456", loaded.get("deepseek.api-key"));
    }

    @Test
    void maskKeepsLast4() {
        assertEquals("****3456", SettingsService.mask("sk-abcdef123456"));
        assertEquals("", SettingsService.mask(""));
        assertEquals("", SettingsService.mask(null));
        assertEquals("****", SettingsService.mask("abc"));
    }

    @Test
    void maskedViewHidesSecret() {
        Map<String, String> patch = new LinkedHashMap<>();
        patch.put("deepseek.api-key", "sk-abcdef123456");
        patch.put("drama.video.provider", "mock");
        service.saveAll(patch);

        Map<String, Object> view = service.maskedView();
        assertEquals("****3456", view.get("deepseek.api-key"));
        assertEquals("mock", view.get("drama.video.provider"));
        // 非 secret 无掩码
        assertFalse(String.valueOf(view.get("drama.video.provider")).contains("****"));
    }

    @Test
    void loadAllMissingReturnsEmpty() {
        Map<String, String> loaded = service.loadAll();
        assertTrue(loaded.isEmpty());
    }
}
