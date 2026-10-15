package com.dramafactory.service;

/*
 * 覆盖说明（行号 -> 测试方法）
 * 62  if (bytes.length == 0) true 臂  -> emptyFileReturnsEmptyMap
 * 68  if (raw != null) true 臂        -> jsonNullReturnsEmptyMap
 * 70  key.isBlank() true 臂           -> blankKeySkipped
 * 73  value == null ? "" 的 null 臂   -> nullValueBecomesEmptyString
 * 92  if (patch != null) false 臂     -> nullPatchDoesNotThrow
 * 95  key == null / key.isBlank() 两 true 臂 -> nullAndBlankKeysSkipped
 * 99  value == null 臂（非 secret 删除）-> nullValueRemovesKey
 * 122 parent != null && !isDirectory 两臂 -> writeCreatesMissingParentDir / writeWithNoParentRelativePath
 * 210 if (options != null) true 臂    -> schemaFieldOptionsAndHints
 * 213 if (hint != null) true 臂       -> schemaFieldOptionsAndHints
 * 226 allowedKeys() 调用              -> allowedKeysMatchesSchema
 *
 * 诚实跳过清单（不可达分支，未写测试）
 * 70  e.getKey() == null 臂：JSON 对象键恒为字符串，Jackson 反序列化不可能产出 null 键，不可达。
 * 146 maskedView 中 value == null ? "" 的 null 臂：loadAll() 在第 73 行已把 null 值转为 ""，
 *     故进入 maskedView 的所有 value 均非 null，此臂不可达。
 */

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SettingsServiceBranchTest {

    @TempDir
    Path tempDir;

    private Path settingsFile() {
        return tempDir.resolve("settings.json");
    }

    @Test
    void emptyFileReturnsEmptyMap() throws IOException {
        Path file = settingsFile();
        Files.write(file, new byte[0]);
        SettingsService service = new SettingsService(file);
        Map<String, String> result = service.loadAll();
        assertTrue(result.isEmpty());
    }

    @Test
    void jsonNullReturnsEmptyMap() throws IOException {
        Path file = settingsFile();
        Files.write(file, "null".getBytes(StandardCharsets.UTF_8));
        SettingsService service = new SettingsService(file);
        Map<String, String> result = service.loadAll();
        assertTrue(result.isEmpty());
    }

    @Test
    void blankKeySkipped() throws IOException {
        Path file = settingsFile();
        Files.write(file, "{\"\": \"x\", \"a\": \"b\"}".getBytes(StandardCharsets.UTF_8));
        SettingsService service = new SettingsService(file);
        Map<String, String> result = service.loadAll();
        assertFalse(result.containsKey(""));
        assertEquals("b", result.get("a"));
    }

    @Test
    void nullValueBecomesEmptyString() throws IOException {
        Path file = settingsFile();
        Files.write(file, "{\"a\": null}".getBytes(StandardCharsets.UTF_8));
        SettingsService service = new SettingsService(file);
        Map<String, String> result = service.loadAll();
        assertEquals("", result.get("a"));
    }

    @Test
    void nullPatchDoesNotThrow() {
        SettingsService service = new SettingsService(settingsFile());
        service.saveAll(null);
        assertTrue(service.loadAll().isEmpty());
    }

    @Test
    void nullAndBlankKeysSkipped() {
        SettingsService service = new SettingsService(settingsFile());
        Map<String, String> patch = new HashMap<>();
        patch.put(null, "nv");
        patch.put("", "ev");
        service.saveAll(patch);
        Map<String, String> result = service.loadAll();
        assertFalse(result.containsKey(""));
        assertFalse(result.containsKey(null));
        assertTrue(result.isEmpty());
    }

    @Test
    void nullValueRemovesKey() {
        SettingsService service = new SettingsService(settingsFile());
        service.saveAll(Map.of("k1", "v1"));
        assertEquals("v1", service.loadAll().get("k1"));

        Map<String, String> patch = new HashMap<>();
        patch.put("k1", null);
        service.saveAll(patch);

        Map<String, String> result = service.loadAll();
        assertFalse(result.containsKey("k1"));
    }

    @Test
    void writeCreatesMissingParentDir() {
        Path file = tempDir.resolve("sub").resolve("s.json");
        SettingsService service = new SettingsService(file);
        service.saveAll(Map.of("k", "v"));
        assertTrue(Files.isRegularFile(file));
    }

    @Test
    void writeWithNoParentRelativePath() throws IOException {
        Path relative = Paths.get("v18-branch-test-settings.json");
        try {
            SettingsService service = new SettingsService(relative);
            service.saveAll(Map.of("k", "v"));
            assertTrue(Files.isRegularFile(relative));
        } finally {
            Files.deleteIfExists(relative);
        }
    }

    @Test
    void schemaFieldOptionsAndHints() {
        SettingsService service = new SettingsService(settingsFile());
        List<Map<String, Object>> schema = service.schema();
        assertFalse(schema.isEmpty());

        Map<String, Object> providerField = null;
        for (Map<String, Object> field : schema) {
            assertTrue(field.containsKey("hint"));
            if ("drama.video.provider".equals(field.get("key"))) {
                providerField = field;
            }
        }
        assertNotNull(providerField);

        Object options = providerField.get("options");
        assertNotNull(options);
        assertTrue(options instanceof List);
        assertTrue(((List<?>) options).contains("mock"));
    }

    @Test
    void allowedKeysMatchesSchema() {
        SettingsService service = new SettingsService(settingsFile());
        Set<String> keys = service.allowedKeys();
        assertTrue(keys.contains("deepseek.api-key"));
        assertEquals(service.schema().size(), keys.size());
    }
}
