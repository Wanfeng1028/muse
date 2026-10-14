package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.io.File;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.io.TempDir;


import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class LlmScriptServiceTest {

    private static final String VALID_JSON = "{\"scenes\":["
            + "{\"sceneNo\":1,\"location\":\"LOC1\",\"timeOfDay\":\"DAY\",\"description\":\"D1\",\"dialogue\":\"DL1\",\"prompt\":\"P1\"},"
            + "{\"sceneNo\":2,\"location\":\"LOC2\",\"timeOfDay\":\"NIGHT\",\"description\":\"D2\",\"dialogue\":\"DL2\",\"prompt\":\"P2\"},"
            + "{\"sceneNo\":3,\"location\":\"LOC3\",\"timeOfDay\":\"DAY\",\"description\":\"D3\",\"dialogue\":\"DL3\",\"prompt\":\"P3\"},"
            + "{\"sceneNo\":4,\"location\":\"LOC4\",\"timeOfDay\":\"NIGHT\",\"description\":\"D4\",\"dialogue\":\"DL4\",\"prompt\":\"P4\"}"
            + "]}";

    private static final String THREE_SCENES_JSON = "{\"scenes\":["
            + "{\"sceneNo\":1,\"location\":\"LOC1\",\"description\":\"D1\",\"dialogue\":\"DL1\"},"
            + "{\"sceneNo\":2,\"location\":\"LOC2\",\"description\":\"D2\",\"dialogue\":\"DL2\"},"
            + "{\"sceneNo\":3,\"location\":\"LOC3\",\"description\":\"D3\",\"dialogue\":\"DL3\"}"
            + "]}";

    private static class StubLlmScriptService extends LlmScriptService {
        private final List<String> responses;
        private final boolean throwAlways;
        int callCount = 0;

        StubLlmScriptService(List<String> responses, boolean throwAlways, int maxRetries) {
            super(null, new ObjectMapper(), true, "test-model", 3000, 120, maxRetries, null,
                    new DramaMetrics(new SimpleMeterRegistry(), null, null));
            this.responses = responses;
            this.throwAlways = throwAlways;
        }

        @Override
        String callModel(ObjectNode body) {
            callCount++;
            if (throwAlways) {
                throw new RuntimeException("stub failure");
            }
            int idx = Math.min(callCount - 1, responses.size() - 1);
            return responses.get(idx);
        }
    }

    private static Episode buildEpisode() {
        Episode episode = new Episode();
        episode.setId(1L);
        episode.setOutline("outline");
        DramaProject project = new DramaProject();
        project.setTitle("title");
        project.setGenre("genre");
        episode.setProject(project);
        return episode;
    }

    @Test
    void parsesPlainJson() {
        StubLlmScriptService stub = new StubLlmScriptService(List.of(VALID_JSON), false, 0);
        LlmScriptService.LlmScriptResult result = stub.generate(buildEpisode(), "chars");

        List<ScriptGenerator.SceneDraft> scenes = result.scenes();
        assertEquals(4, scenes.size());
        assertEquals(1, scenes.get(0).sceneNo());
        assertEquals("LOC1", scenes.get(0).location());
        assertEquals("D1", scenes.get(0).description());
        assertEquals(2, scenes.get(1).sceneNo());
        assertEquals("LOC2", scenes.get(1).location());
    }

    @Test
    void parsesJsonInsideFencedCodeBlock() {
        String content = "```json\n" + VALID_JSON + "\n```";
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        LlmScriptService.LlmScriptResult result = stub.generate(buildEpisode(), "chars");

        assertEquals(4, result.scenes().size());
        assertEquals("LOC3", result.scenes().get(2).location());
    }

    @Test
    void parsesJsonWithSurroundingNoise() {
        String content = "Sure, here is your script:\n" + VALID_JSON + "\nHope that helps!";
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        LlmScriptService.LlmScriptResult result = stub.generate(buildEpisode(), "chars");

        assertEquals(4, result.scenes().size());
        assertEquals("LOC4", result.scenes().get(3).location());
    }

    @Test
    void invalidJsonThrows() {
        StubLlmScriptService stub = new StubLlmScriptService(List.of("not a json at all"), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void tooFewScenesThrows() {
        StubLlmScriptService stub = new StubLlmScriptService(List.of(THREE_SCENES_JSON), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void disabledServiceThrowsWithoutCallingModel() {
        StubLlmScriptService stub = new StubLlmScriptService(List.of(VALID_JSON), false, 0) {
        };
        // 使用一个 enabled=false 的桩：重写构造参数不方便，改用匿名子类方式
        LlmScriptService disabled = new LlmScriptService(null, new ObjectMapper(), false,
                "test-model", 3000, 120, 0, null,
                new DramaMetrics(new SimpleMeterRegistry(), null, null)) {
            @Override
            String callModel(ObjectNode body) {
                fail("callModel should not be invoked when disabled");
                return null;
            }
        };
        assertThrows(LlmScriptUnavailableException.class, () -> disabled.generate(buildEpisode(), "chars"));
    }

    @Test
    void retriesOnceOnInvalidThenSucceeds() {
        StubLlmScriptService stub = new StubLlmScriptService(
                List.of("garbage", VALID_JSON), false, 1);
        LlmScriptService.LlmScriptResult result = stub.generate(buildEpisode(), "chars");

        assertEquals(4, result.scenes().size());
        assertEquals(2, stub.callCount);
    }

    @Test
    void exhaustsRetriesWhenAlwaysThrowing() {
        StubLlmScriptService stub = new StubLlmScriptService(List.of(), true, 2);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
        assertEquals(3, stub.callCount);
    }

    private static LlmScriptService directService(boolean enabled, String model, int maxTokens, int timeoutSeconds, int maxRetries, String cliPath) {
        return new LlmScriptService(null, new ObjectMapper(), enabled, model, maxTokens, timeoutSeconds, maxRetries, cliPath,
                new DramaMetrics(new SimpleMeterRegistry(), null, null));
    }

    @Test
    void validate_disabledDoesNothing() {
        LlmScriptService service = directService(false, "m", 3000, 120, 0, null);
        assertDoesNotThrow(service::validate);
    }

    @Test
    void validate_rejectsBlankModel() {
        LlmScriptService service = directService(true, " ", 3000, 120, 0, null);
        assertThrows(IllegalStateException.class, service::validate);
    }

    @Test
    void validate_rejectsZeroMaxTokens() {
        LlmScriptService service = directService(true, "m", 0, 120, 0, null);
        assertThrows(IllegalStateException.class, service::validate);
    }

    @Test
    void validate_rejectsZeroTimeout() {
        LlmScriptService service = directService(true, "m", 3000, 0, 0, null);
        assertThrows(IllegalStateException.class, service::validate);
    }

    @Test
    void validate_rejectsNegativeMaxRetries() {
        LlmScriptService service = directService(true, "m", 3000, 120, -1, null);
        assertThrows(IllegalStateException.class, service::validate);
    }

    @Test
    void validate_rejectsMissingCliPath() {
        LlmScriptService service = directService(true, "m", 3000, 120, 0, "/no/such/file/chat.py");
        assertThrows(IllegalStateException.class, service::validate);
    }

    @Test
    void validate_rejectsNonExecutableCliPath(@TempDir Path tempDir) throws Exception {
        File f = tempDir.resolve("chat.py").toFile();
        f.createNewFile();
        LlmScriptService service = directService(true, "m", 3000, 120, 0, f.getAbsolutePath());
        assertThrows(IllegalStateException.class, service::validate);
    }

    @Test
    void validate_acceptsExecutableCliPath(@TempDir Path tempDir) throws Exception {
        File f = tempDir.resolve("chat.py").toFile();
        f.createNewFile();
        f.setExecutable(true);
        LlmScriptService service = directService(true, "m", 3000, 120, 0, f.getAbsolutePath());
        assertDoesNotThrow(service::validate);
    }

    @Test
    void validate_autoDetectWithoutCliConfig() {
        LlmScriptService service = directService(true, "m", 3000, 120, 0, null);
        assertDoesNotThrow(service::validate);
    }

    private static String oneScene(int no) {
        return "{\"sceneNo\":" + no + ",\"location\":\"LOC" + no + "\",\"timeOfDay\":\"DAY\",\"description\":\"D" + no + "\",\"dialogue\":\"DL" + no + "\",\"prompt\":\"P" + no + "\"}";
    }

    @Test
    void parseScenes_nullContent_throws() {
        StubLlmScriptService stub = new StubLlmScriptService(List.of("x"), false, 0) {
            @Override
            String callModel(ObjectNode body) {
                return null;
            }
        };
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void parseScenes_fenceWithoutClosingFence_parses() {
        String content = "```json\n" + VALID_JSON;
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        LlmScriptService.LlmScriptResult result = stub.generate(buildEpisode(), "chars");
        assertEquals(4, result.scenes().size());
    }

    @Test
    void parseScenes_fenceWithoutNewline_throws() {
        String content = "```" + VALID_JSON;
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void parseScenes_arrayRoot_parses() {
        String content = "[" + oneScene(1) + "," + oneScene(2) + "," + oneScene(3) + "," + oneScene(4) + "]";
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        LlmScriptService.LlmScriptResult result = stub.generate(buildEpisode(), "chars");
        assertEquals(4, result.scenes().size());
        assertEquals("LOC4", result.scenes().get(3).location());
    }

    @Test
    void parseScenes_missingScenesArray_throws() {
        StubLlmScriptService stub = new StubLlmScriptService(List.of("{}"), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void parseScenes_nonObjectScene_throws() {
        StubLlmScriptService stub = new StubLlmScriptService(List.of("{\"scenes\":[1,2,3,4]}"), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void parseScenes_stringSceneNo_throws() {
        String content = "{\"scenes\":[" + oneScene(1).replace("\"sceneNo\":1", "\"sceneNo\":\"1\"") + "]}";
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void parseScenes_sceneNoOutOfRange_throws() {
        String content = "{\"scenes\":[" + oneScene(1).replace("\"sceneNo\":1", "\"sceneNo\":5") + "]}";
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void parseScenes_blankLocation_throws() {
        String content = "{\"scenes\":[" + oneScene(1).replace("\"location\":\"LOC1\"", "\"location\":\"\"") + "]}";
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void parseScenes_missingDescription_throws() {
        String content = "{\"scenes\":[" + oneScene(1).replace(",\"description\":\"D1\"", "") + "]}";
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void parseScenes_blankDialogue_throws() {
        String content = "{\"scenes\":[" + oneScene(1).replace("\"dialogue\":\"DL1\"", "\"dialogue\":\"   \"") + "]}";
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        assertThrows(LlmScriptUnavailableException.class, () -> stub.generate(buildEpisode(), "chars"));
    }

    @Test
    void parseScenes_optionalFieldDefaults() {
        String first = oneScene(1).replace("\"timeOfDay\":\"DAY\"", "\"timeOfDay\":\"\"").replace("\"prompt\":\"P1\"", "\"prompt\":null");
        String content = "{\"scenes\":[" + first + "," + oneScene(2) + "," + oneScene(3) + "," + oneScene(4) + "]}";
        StubLlmScriptService stub = new StubLlmScriptService(List.of(content), false, 0);
        LlmScriptService.LlmScriptResult result = stub.generate(buildEpisode(), "chars");
        assertEquals(4, result.scenes().size());
        assertEquals("白天", result.scenes().get(0).timeOfDay());
        assertEquals("", result.scenes().get(0).prompt());
    }

    private static class CapturingLlmScriptService extends StubLlmScriptService {
        ObjectNode lastBody;

        CapturingLlmScriptService() {
            super(List.of(VALID_JSON), false, 0);
        }

        @Override
        String callModel(ObjectNode body) {
            lastBody = body;
            return super.callModel(body);
        }
    }

    private static String userContentOf(ObjectNode body) {
        for (JsonNode m : body.path("messages")) {
            if ("user".equals(m.path("role").asText(""))) {
                return m.path("content").asText("");
            }
        }
        return "";
    }

    @Test
    void buildUserContent_nullProject_usesDefaults() {
        Episode episode = new Episode();
        episode.setId(2L);
        episode.setOutline("o");
        CapturingLlmScriptService stub = new CapturingLlmScriptService();
        stub.generate(episode, "chars");
        String user = userContentOf(stub.lastBody);
        assertTrue(user.contains("未命名"));
        assertTrue(user.contains("未指定"));
    }

    @Test
    void buildUserContent_blankTitleAndOutline_usesDefaults() {
        DramaProject project = new DramaProject();
        project.setTitle(" ");
        project.setGenre(null);
        Episode episode = new Episode();
        episode.setId(3L);
        episode.setProject(project);
        episode.setOutline(" ");
        CapturingLlmScriptService stub = new CapturingLlmScriptService();
        stub.generate(episode, "chars");
        String user = userContentOf(stub.lastBody);
        assertTrue(user.contains("未命名"));
        assertTrue(user.contains("未指定"));
        assertTrue(user.contains("无大纲，请自由发挥"));
    }

    @Test
    void buildUserContent_nullCharactersSummary_omitsCastLine() {
        CapturingLlmScriptService stub = new CapturingLlmScriptService();
        stub.generate(buildEpisode(), null);
        assertFalse(userContentOf(stub.lastBody).contains("角色表："));
    }

    @Test
    void buildUserContent_blankCharactersSummary_omitsCastLine() {
        CapturingLlmScriptService stub = new CapturingLlmScriptService();
        stub.generate(buildEpisode(), "  ");
        assertFalse(userContentOf(stub.lastBody).contains("角色表："));
    }

    @Test
    void buildUserContent_projectGetterThrows_stillGenerates() {
        Episode episode = mock(Episode.class);
        when(episode.getProject()).thenThrow(new RuntimeException("lazy"));
        when(episode.getOutline()).thenReturn("t");
        CapturingLlmScriptService stub = new CapturingLlmScriptService();
        LlmScriptService.LlmScriptResult result = stub.generate(episode, "chars");
        assertEquals(4, result.scenes().size());
        assertTrue(userContentOf(stub.lastBody).contains("未命名"));
    }
}




