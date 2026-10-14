// LlmScriptService.buildRequestBody/buildUserContent 分支覆盖（v2.14）。
package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class LlmScriptServiceBuildBranchTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    private LlmScriptService svc() {
        return new LlmScriptService(null, objectMapper, true, "test-model", 3000, 120, 2, null,
                new DramaMetrics(new SimpleMeterRegistry(), null, null));
    }

    private Episode episode(String title, String genre, String outline) {
        Episode e = new Episode();
        e.setId(1L);
        e.setOutline(outline);
        DramaProject p = new DramaProject();
        p.setTitle(title);
        p.setGenre(genre);
        e.setProject(p);
        return e;
    }

    private ObjectNode buildBody(Episode e, String chars, String skill) throws Exception {
        Method m = LlmScriptService.class.getDeclaredMethod("buildRequestBody", Episode.class, String.class, String.class);
        m.setAccessible(true);
        return (ObjectNode) m.invoke(svc(), e, chars, skill);
    }

    private String buildUser(Episode e, String chars) throws Exception {
        Method m = LlmScriptService.class.getDeclaredMethod("buildUserContent", Episode.class, String.class);
        m.setAccessible(true);
        return (String) m.invoke(svc(), e, chars);
    }

    @Test
    void body_nullSkill_noAugment() throws Exception {
        ObjectNode root = buildBody(episode("T", "G", "ol"), "chars", null);
        String systemContent = root.get("messages").get(0).get("content").asText();
        assertFalse(systemContent.contains("Skill 增强"), "null skillPrompt 不应注入增强标记");
        assertEquals("test-model", root.get("model").asText());
        assertEquals(3000, root.get("max_tokens").asInt());
    }

    @Test
    void body_blankSkill_noAugment() throws Exception {
        ObjectNode root = buildBody(episode("T", "G", "ol"), "chars", " ");
        String systemContent = root.get("messages").get(0).get("content").asText();
        assertFalse(systemContent.contains("Skill 增强"), "空白 skillPrompt 不应注入增强标记");
        assertEquals("system", root.get("messages").get(0).get("role").asText());
    }

    @Test
    void body_withSkill_augments() throws Exception {
        ObjectNode root = buildBody(episode("T", "G", "ol"), "chars", "SKILL-X");
        String systemContent = root.get("messages").get(0).get("content").asText();
        assertTrue(systemContent.contains("【Skill 增强】"), "应包含增强标记，实际: " + systemContent);
        assertTrue(systemContent.contains("SKILL-X"), "应包含传入的 skillPrompt");
        assertTrue(systemContent.contains("\n\n【Skill 增强】\nSKILL-X"),
                "增强内容应以真实换行分隔并紧跟 skillPrompt，实际: " + systemContent);
    }

    @Test
    void user_projectThrows_fallback() throws Exception {
        Episode e = mock(Episode.class);
        when(e.getProject()).thenThrow(new RuntimeException("lazy"));
        when(e.getOutline()).thenReturn("ol");
        String content = buildUser(e, "chars");
        assertTrue(content.contains("未命名"), "project 抛异常时标题应回退为未命名");
        assertTrue(content.contains("未指定"), "project 抛异常时题材应回退为未指定");
    }

    @Test
    void user_blankChars_noCastSection() throws Exception {
        String content = buildUser(episode("T", "G", "ol"), "");
        assertTrue(content.contains("项目标题：T"), "应包含项目标题");
        assertFalse(content.contains("角色表："), "空白 charactersSummary 不应输出角色表段");
    }
}
