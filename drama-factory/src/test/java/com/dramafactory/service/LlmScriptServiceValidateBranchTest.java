// LlmScriptService.validate 分支覆盖（v2.14）
package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LlmScriptServiceValidateBranchTest {

    @TempDir
    Path tempDir;

    private LlmScriptService svc(boolean enabled, String model, int maxTokens, int timeoutSeconds, int maxRetries, String cliPath) {
        return new LlmScriptService(null, new ObjectMapper(), enabled, model, maxTokens, timeoutSeconds, maxRetries, cliPath,
                new DramaMetrics(new SimpleMeterRegistry(), null, null));
    }

    private Object effectiveCliPathOf(LlmScriptService s) throws Exception {
        Field f = LlmScriptService.class.getDeclaredField("effectiveCliPath");
        f.setAccessible(true);
        return f.get(s);
    }

    @Test
    void validate_disabled_noop() {
        LlmScriptService service = svc(false, null, 0, 0, -5, "/nonexistent/whatever.py");
        assertDoesNotThrow(service::validate);
    }

    @Test
    void validate_nullModel_throws() {
        LlmScriptService service = svc(true, null, 100, 10, 0, null);
        IllegalStateException ex = assertThrows(IllegalStateException.class, service::validate);
        assertTrue(ex.getMessage().contains("model 不能为空"),
                "消息应包含 'model 不能为空'，实际: " + ex.getMessage());
    }

    @Test
    void validate_blankModel_throws() {
        LlmScriptService service = svc(true, " ", 100, 10, 0, null);
        IllegalStateException ex = assertThrows(IllegalStateException.class, service::validate);
        assertTrue(ex.getMessage().contains("model 不能为空"),
                "消息应包含 'model 不能为空'，实际: " + ex.getMessage());
    }

    @Test
    void validate_zeroMaxTokens_throws() {
        LlmScriptService service = svc(true, "gpt-4o-mini", 0, 10, 0, null);
        IllegalStateException ex = assertThrows(IllegalStateException.class, service::validate);
        assertTrue(ex.getMessage().contains("max-tokens 必须大于 0"),
                "消息应包含 'max-tokens 必须大于 0'，实际: " + ex.getMessage());
    }

    @Test
    void validate_zeroTimeout_throws() {
        LlmScriptService service = svc(true, "gpt-4o-mini", 100, 0, 0, null);
        IllegalStateException ex = assertThrows(IllegalStateException.class, service::validate);
        assertTrue(ex.getMessage().contains("timeout-seconds 必须大于 0"),
                "消息应包含 'timeout-seconds 必须大于 0'，实际: " + ex.getMessage());
    }

    @Test
    void validate_negativeRetries_throws() {
        LlmScriptService service = svc(true, "gpt-4o-mini", 100, 10, -1, null);
        IllegalStateException ex = assertThrows(IllegalStateException.class, service::validate);
        assertTrue(ex.getMessage().contains("max-retries 不能为负数"),
                "消息应包含 'max-retries 不能为负数'，实际: " + ex.getMessage());
    }

    @Test
    void validate_badCliPath_throws() {
        LlmScriptService service = svc(true, "gpt-4o-mini", 100, 10, 0, "/nonexistent/xyz.py");
        IllegalStateException ex = assertThrows(IllegalStateException.class, service::validate);
        assertTrue(ex.getMessage().contains("cli-path 指定的文件不存在或不可执行"),
                "消息应包含 'cli-path 指定的文件不存在或不可执行'，实际: " + ex.getMessage());
    }

    @Test
    void validate_goodCliPath_setsEffective() throws Exception {
        Path script = tempDir.resolve("script.py");
        Files.writeString(script, "#!/usr/bin/env python3\nprint('ok')\n");
        File scriptFile = script.toFile();
        assertTrue(scriptFile.setExecutable(true), "测试前置：脚本文件应能被设置为可执行");
        assertTrue(scriptFile.isFile() && scriptFile.canExecute(), "测试前置：脚本应存在且可执行");

        String configured = scriptFile.getAbsolutePath();
        LlmScriptService service = svc(true, "gpt-4o-mini", 100, 10, 0, configured);

        assertDoesNotThrow(service::validate);

        Object effective = effectiveCliPathOf(service);
        assertNotNull(effective, "显式配置可执行脚本时 effectiveCliPath 不应为 null");
        assertEquals(configured, effective, "effectiveCliPath 应等于显式配置的路径");
    }

    @Test
    void validate_autoDetect_noCliFound() throws Exception {
        LlmScriptService service = svc(true, "gpt-4o-mini", 100, 10, 0, "");

        assertDoesNotThrow(service::validate);

        Object effective = effectiveCliPathOf(service);
        // 环境无关的后置条件：要么没探测到（null），要么指向真实存在的可执行文件
        if (effective != null) {
            File f = new File((String) effective);
            assertTrue(f.isFile() && f.canExecute(), "自动探测到的 CLI 路径应为可执行文件：" + effective);
        }
    }
}
