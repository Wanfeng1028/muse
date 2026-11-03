// 文件：src/test/java/com/dramafactory/service/LlmScriptServiceV229D2Test.java

package com.dramafactory.service;

import com.dramafactory.service.LlmScriptService.ModelCallResult;
import com.dramafactory.metrics.DramaMetrics;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

// 不可达分支说明（未在本测试中覆盖，环境依赖，不硬测）：
// - line 141 envHome == null / isBlank（2 个）：System.getenv("HOME") 在测试进程内不可改，真实环境 HOME 恒非空。
// - line 157 for (String base : bases) 零次迭代（1 个）：bases 恒非空（同上）。
// - line 166 三元 effectiveCliPath == null（1 个）：探测失败分支依赖 HOME 与 user.home 下都没有可执行文件，环境依赖。
class LlmScriptServiceV229D2Test {

    private LlmScriptService newService(boolean enabled, String cliPath) {
        return new LlmScriptService(
                mock(CredentialResolver.class),
                new ObjectMapper(),
                enabled,
                "Deepseek-v4-flash",
                3000,
                120,
                2,
                cliPath,
                mock(DramaMetrics.class));
    }

    @Test
    @DisplayName("user.home 为空时跳过 user.home 探测，validate 正常完成")
    void validateSkipsBlankUserHome() {
        String original = System.getProperty("user.home");
        System.setProperty("user.home", "");
        try {
            LlmScriptService service = newService(true, "");
            service.validate();
        } finally {
            if (original == null) {
                System.clearProperty("user.home");
            } else {
                System.setProperty("user.home", original);
            }
        }
    }

    @Test
    @DisplayName("cliPath 指向存在但不可执行的文件时 validate 抛 IllegalStateException")
    void validateThrowsWhenCliFileNotExecutable(@TempDir Path tempDir) throws Exception {
        Path file = tempDir.resolve("not-executable.sh");
        Files.write(file, "#!/bin/sh\necho hi\n".getBytes(StandardCharsets.UTF_8));
        // 默认创建的文件不可执行，不调用 setExecutable
        assertThat(file.toFile().isFile()).isTrue();

        LlmScriptService service = newService(true, file.toAbsolutePath().toString());
        assertThatThrownBy(service::validate)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("不存在或不可执行");
    }

    @Test
    @DisplayName("HTTP 传输失败且 effectiveCliPath 非 null 时回退到 CLI 并返回内容")
    void fallsBackToCliWhenHttpFails(@TempDir Path tempDir) throws Exception {
        Path script = tempDir.resolve("chat.py");
        Files.write(script, "#!/usr/bin/env python3\nprint(\"cli-ok\")\n".getBytes(StandardCharsets.UTF_8));
        assertThat(script.toFile().setExecutable(true)).isTrue();

        CredentialResolver credentialResolver = mock(CredentialResolver.class);
        when(credentialResolver.chatAuth()).thenThrow(new RuntimeException("auth-fail"));

        LlmScriptService service = new LlmScriptService(
                credentialResolver,
                new ObjectMapper(),
                false,
                "Deepseek-v4-flash",
                3000,
                120,
                2,
                "",
                mock(DramaMetrics.class));

        java.lang.reflect.Field f = LlmScriptService.class.getDeclaredField("effectiveCliPath");
        f.setAccessible(true);
        f.set(service, script.toFile().getAbsolutePath());

        ObjectNode body = new ObjectMapper().createObjectNode();
        ModelCallResult result = service.callModelWithUsage(body);

        assertThat(result.content()).isEqualTo("cli-ok");
        assertThat(result.promptTokens()).isZero();
        assertThat(result.completionTokens()).isZero();
    }

    @Test
    @DisplayName("左方括号先于左花括号时走数组分支解析出 4 场场景")
    void parsesScenesViaArrayBranch() throws Exception {
        String content = "前置噪音 ["
                + scene(1, "咖啡店", "两人初次相遇", "今天天气不错", "DAY", "prompt-1") + ","
                + scene(2, "街道", "追逐戏份展开", "快跑", "NIGHT", "prompt-2") + ","
                + scene(3, "天台", "真相逐渐浮现", "原来是你", "DAWN", "prompt-3") + ","
                + scene(4, "车站", "最终告别时刻", "再见", "DUSK", "prompt-4")
                + "] 后置噪音";

        LlmScriptService service = newService(false, null);
        Method m = LlmScriptService.class.getDeclaredMethod("parseScenes", String.class);
        m.setAccessible(true);
        Object result = m.invoke(service, content);
        assertThat((List<?>) result).hasSize(4);
    }

    private String scene(int sceneNo, String location, String description, String dialogue, String timeOfDay, String prompt) {
        return "{\"sceneNo\":" + sceneNo
                + ",\"location\":\"" + location + "\""
                + ",\"description\":\"" + description + "\""
                + ",\"dialogue\":\"" + dialogue + "\""
                + ",\"timeOfDay\":\"" + timeOfDay + "\""
                + ",\"prompt\":\"" + prompt + "\"}";
    }
}