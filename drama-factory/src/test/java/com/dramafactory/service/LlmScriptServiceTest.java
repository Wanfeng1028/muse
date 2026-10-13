package com.dramafactory.service;

import com.dramafactory.metrics.DramaMetrics;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

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
}
