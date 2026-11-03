// LlmScriptService.parseScenes 分支覆盖（v2.14）
package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class LlmScriptServiceScenesBranchTest {

    private static class Stub extends LlmScriptService {
        private final List<String> responses;

        Stub(List<String> responses) {
            super(null, new ObjectMapper(), true, "test-model", 3000, 120, 0, null,
                    new DramaMetrics(new SimpleMeterRegistry(), null, null));
            this.responses = responses;
        }

        @Override
        LlmScriptService.ModelCallResult callModelWithUsage(ObjectNode body) {
            return new LlmScriptService.ModelCallResult(responses.get(0), 0, 0);
        }
    }

    private static Episode ep() {
        Episode e = new Episode();
        e.setId(1L);
        e.setOutline("ol");
        DramaProject p = new DramaProject();
        p.setTitle("t");
        p.setGenre("g");
        e.setProject(p);
        return e;
    }

    private static final String S1 = "{\"sceneNo\":1,\"location\":\"L1\",\"timeOfDay\":\"白天\",\"description\":\"D1\",\"dialogue\":\"G1\",\"prompt\":\"P1\"}";
    private static final String S2 = "{\"sceneNo\":2,\"location\":\"L2\",\"timeOfDay\":\"夜晚\",\"description\":\"D2\",\"dialogue\":\"G2\",\"prompt\":\"P2\"}";
    private static final String S3 = "{\"sceneNo\":3,\"location\":\"L3\",\"timeOfDay\":\"白天\",\"description\":\"D3\",\"dialogue\":\"G3\",\"prompt\":\"P3\"}";
    private static final String S4 = "{\"sceneNo\":4,\"location\":\"L4\",\"timeOfDay\":\"黄昏\",\"description\":\"D4\",\"dialogue\":\"G4\",\"prompt\":\"P4\"}";

    private LlmScriptUnavailableException fails(String content) {
        List<String> rs = new ArrayList<>();
        rs.add(content);
        Stub stub = new Stub(rs);
        LlmScriptUnavailableException outer =
                assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(ep(), "chars"));
        // generate() 会把解析异常包一层"已重试 N 次"外壳，具体校验消息在 cause 里
        return (LlmScriptUnavailableException) outer.getCause();
    }

    @Test
    void scenes_nullContent_throws() {
        LlmScriptUnavailableException ex = fails(null);
        assertTrue(ex.getMessage().contains("content 为 null"), ex.getMessage());
    }

    @Test
    void scenes_noJsonStructure_throws() {
        LlmScriptUnavailableException ex = fails("just some text");
        assertTrue(ex.getMessage().contains("未找到 JSON 结构"), ex.getMessage());
    }

    @Test
    void scenes_invalidJson_throws() {
        LlmScriptUnavailableException ex = fails("{invalid json}");
        assertTrue(ex.getMessage().contains("JSON 解析失败"), ex.getMessage());
    }

    @Test
    void scenes_arrayRoot_parses() {
        List<String> rs = new ArrayList<>();
        rs.add("[" + S1 + "," + S2 + "," + S3 + "," + S4 + "]");
        Stub stub = new Stub(rs);
        LlmScriptService.LlmScriptResult result = stub.generate(ep(), "chars");
        List<ScriptGenerator.SceneDraft> scenes = result.scenes();
        assertNotNull(scenes);
        assertEquals(4, scenes.size());
        assertEquals(1, scenes.get(0).sceneNo());
        assertEquals("L1", scenes.get(0).location());
        assertEquals("白天", scenes.get(0).timeOfDay());
        assertEquals("D1", scenes.get(0).description());
        assertEquals("G1", scenes.get(0).dialogue());
        assertEquals("P1", scenes.get(0).prompt());
    }

    @Test
    void scenes_nonObject_throws() {
        LlmScriptUnavailableException ex = fails("{\"scenes\":[1,2,3,4]}");
        assertTrue(ex.getMessage().contains("第 1 场不是对象"), ex.getMessage());
    }

    @Test
    void scenes_sceneNoOutOfRange_throws() {
        String bad = "{\"sceneNo\":5,\"location\":\"L1\",\"timeOfDay\":\"白天\",\"description\":\"D1\",\"dialogue\":\"G1\",\"prompt\":\"P1\"}";
        LlmScriptUnavailableException ex = fails("{\"scenes\":[" + bad + "," + S2 + "," + S3 + "," + S4 + "]}");
        assertTrue(ex.getMessage().contains("sceneNo 越界"), ex.getMessage());
    }

    @Test
    void scenes_blankLocation_throws() {
        String bad = "{\"sceneNo\":1,\"location\":\"\",\"timeOfDay\":\"白天\",\"description\":\"D1\",\"dialogue\":\"G1\",\"prompt\":\"P1\"}";
        LlmScriptUnavailableException ex = fails("{\"scenes\":[" + bad + "," + S2 + "," + S3 + "," + S4 + "]}");
        assertTrue(ex.getMessage().contains("location 为空"), ex.getMessage());
    }

    @Test
    void scenes_missingTimeOfDay_defaults() {
        String a = "{\"sceneNo\":1,\"location\":\"L1\",\"description\":\"D1\",\"dialogue\":\"G1\"}";
        String b = "{\"sceneNo\":2,\"location\":\"L2\",\"description\":\"D2\",\"dialogue\":\"G2\"}";
        String c = "{\"sceneNo\":3,\"location\":\"L3\",\"description\":\"D3\",\"dialogue\":\"G3\"}";
        String d = "{\"sceneNo\":4,\"location\":\"L4\",\"description\":\"D4\",\"dialogue\":\"G4\"}";
        List<String> rs = new ArrayList<>();
        rs.add("{\"scenes\":[" + a + "," + b + "," + c + "," + d + "]}");
        Stub stub = new Stub(rs);
        LlmScriptService.LlmScriptResult result = stub.generate(ep(), "chars");
        List<ScriptGenerator.SceneDraft> scenes = result.scenes();
        assertNotNull(scenes);
        assertEquals(4, scenes.size());
        assertEquals("白天", scenes.get(0).timeOfDay());
        assertEquals("L1", scenes.get(0).location());
        assertEquals("D1", scenes.get(0).description());
        assertEquals("G1", scenes.get(0).dialogue());
    }
}
