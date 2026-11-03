// 文件：src/test/java/com/dramafactory/service/LlmScriptServiceV229Test.java

package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.Episode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * LlmScriptService 分支覆盖补齐（v2.2.9）。
 *
 * <p>纯单元测试，不起 Spring 上下文；不 mock 静态方法 {@link LlmTransport}，
 * 通过子类覆盖包可见方法隔离网络。</p>
 */
class LlmScriptServiceV229Test {

    private final ObjectMapper objectMapper = new ObjectMapper();

    private LlmScriptService newService(boolean enabled, String cliPath) {
        return new LlmScriptService(
                mock(CredentialResolver.class),
                objectMapper,
                enabled,
                "Deepseek-v4-flash",
                3000,
                120,
                2,
                cliPath,
                mock(DramaMetrics.class));
    }

    private LlmScriptService newService(boolean enabled, String cliPath, CredentialResolver credentialResolver) {
        return new LlmScriptService(
                credentialResolver,
                objectMapper,
                enabled,
                "Deepseek-v4-flash",
                3000,
                120,
                2,
                cliPath,
                mock(DramaMetrics.class));
    }

    private static String readEffectiveCliPath(LlmScriptService service) throws Exception {
        Field f = LlmScriptService.class.getDeclaredField("effectiveCliPath");
        f.setAccessible(true);
        return (String) f.get(service);
    }

    @Test
    @DisplayName("validate 开启且未配置 cliPath，自动探测到可执行 chat.py 时设置 effectiveCliPath（HOME 或 user.home 任一命中即可）")
    void validate_autoDetectFindsExecutableCli_setsEffectiveCliPath(@TempDir Path tempDir) throws Exception {
        Path skillDir = tempDir.resolve("workspace/skills/weixin-chatapi/bin");
        Files.createDirectories(skillDir);
        Path chatPy = skillDir.resolve("chat.py");
        Files.writeString(chatPy, "#!/usr/bin/env python3\n", StandardCharsets.UTF_8);
        File chatFile = chatPy.toFile();
        assertThat(chatFile.setExecutable(true, false)).isTrue();

        String originalHome = System.getProperty("user.home");
        System.setProperty("user.home", tempDir.toString());
        try {
            LlmScriptService service = newService(true, "");
            service.validate();

            String effective = readEffectiveCliPath(service);
            assertThat(effective).isNotNull();
            assertThat(effective).endsWith("/workspace/skills/weixin-chatapi/bin/chat.py");
        } finally {
            if (originalHome != null) {
                System.setProperty("user.home", originalHome);
            } else {
                System.clearProperty("user.home");
            }
        }
    }

    @Test
    @DisplayName("callModelWithUsage 无 CLI 回退时，chatAuth 抛 RuntimeException 原样向上抛")
    void callModelWithUsage_chatAuthThrowsWithoutCli_propagatesOriginalException() {
        CredentialResolver credentialResolver = mock(CredentialResolver.class);
        when(credentialResolver.chatAuth()).thenThrow(new RuntimeException("auth-fail"));
        LlmScriptService service = newService(false, null, credentialResolver);

        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", "Deepseek-v4-flash");

        assertThatThrownBy(() -> service.callModelWithUsage(body))
                .isInstanceOf(RuntimeException.class)
                .hasMessage("auth-fail");
    }

    private static String readEffectiveCliPathOrNull(LlmScriptService service) {
        try {
            return readEffectiveCliPath(service);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    @Test
    @DisplayName("parseScenes 缺 timeOfDay 默认白天、缺 prompt 默认空串")
    void parseScenes_missingTimeOfDayAndPrompt_usesDefaults() throws Exception {
        LlmScriptService service = newService(false, null);

        String json = "{\"scenes\":["
                + "{\"sceneNo\":1,\"location\":\"客厅\",\"description\":\"开场画面描述\",\"dialogue\":\"A：你好\"},"
                + "{\"sceneNo\":2,\"location\":\"街道\",\"timeOfDay\":\"黄昏\",\"description\":\"冲突升级描述\",\"dialogue\":\"B：不好\"},"
                + "{\"sceneNo\":3,\"location\":\"办公室\",\"timeOfDay\":\"夜晚\",\"description\":\"反转描述内容\",\"dialogue\":\"C：原来如此\",\"prompt\":\"close-up shot\"},"
                + "{\"sceneNo\":4,\"location\":\"天台\",\"timeOfDay\":\"夜晚\",\"description\":\"高潮收尾描述\",\"dialogue\":\"D：结束了\"}"
                + "]}";

        Method parseScenes = LlmScriptService.class.getDeclaredMethod("parseScenes", String.class);
        parseScenes.setAccessible(true);

        @SuppressWarnings("unchecked")
        List<ScriptGenerator.SceneDraft> drafts =
                (List<ScriptGenerator.SceneDraft>) parseScenes.invoke(service, json);

        assertThat(drafts).hasSize(4);

        ScriptGenerator.SceneDraft first = drafts.get(0);
        assertThat(first.sceneNo()).isEqualTo(1);
        assertThat(first.timeOfDay()).isEqualTo("白天");
        assertThat(first.prompt()).isEmpty();

        ScriptGenerator.SceneDraft fourth = drafts.get(3);
        assertThat(fourth.sceneNo()).isEqualTo(4);
        assertThat(fourth.timeOfDay()).isEqualTo("夜晚");
        assertThat(fourth.prompt()).isEmpty();

        ScriptGenerator.SceneDraft third = drafts.get(2);
        assertThat(third.prompt()).isEqualTo("close-up shot");
    }

    @Test
    @DisplayName("parseScenes 通过 generate 间接触发：默认值场景可成功生成 4 场")
    void generate_viaSubclassOverride_producesFourScenesWithDefaults() {
        String json = "{\"scenes\":["
                + "{\"sceneNo\":1,\"location\":\"客厅\",\"description\":\"开场画面描述\",\"dialogue\":\"A：你好\"},"
                + "{\"sceneNo\":2,\"location\":\"街道\",\"timeOfDay\":\"黄昏\",\"description\":\"冲突升级描述\",\"dialogue\":\"B：不好\"},"
                + "{\"sceneNo\":3,\"location\":\"办公室\",\"timeOfDay\":\"夜晚\",\"description\":\"反转描述内容\",\"dialogue\":\"C：原来如此\"},"
                + "{\"sceneNo\":4,\"location\":\"天台\",\"timeOfDay\":\"夜晚\",\"description\":\"高潮收尾描述\",\"dialogue\":\"D：结束了\"}"
                + "]}";

        LlmScriptService service = new LlmScriptService(
                mock(CredentialResolver.class),
                objectMapper,
                true,
                "Deepseek-v4-flash",
                3000,
                120,
                0,
                null,
                mock(DramaMetrics.class)) {
            @Override
            ModelCallResult callModelWithUsage(ObjectNode body) {
                return new ModelCallResult(json, 0, 0);
            }
        };

        Episode episode = new Episode();
        episode.setOutline("测试大纲");

        LlmScriptService.LlmScriptResult result = service.generate(episode, "", null);

        assertThat(result.scenes()).hasSize(4);
        assertThat(result.model()).isEqualTo("Deepseek-v4-flash");
        assertThat(result.scenes().get(0).timeOfDay()).isEqualTo("白天");
        assertThat(result.scenes().get(0).prompt()).isEmpty();
    }
}
