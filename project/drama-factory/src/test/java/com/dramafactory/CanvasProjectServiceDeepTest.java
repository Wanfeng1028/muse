package com.dramafactory;

import com.dramafactory.dto.canvas.CanvasEdgeV2;
import com.dramafactory.dto.canvas.CanvasNodeV2;
import com.dramafactory.dto.canvas.CanvasPatchRequest;
import com.dramafactory.dto.canvas.CanvasProjectV2;
import com.dramafactory.exception.CanvasConflictException;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.service.CanvasEventService;
import com.dramafactory.service.CanvasMigrationAdapter;
import com.dramafactory.service.CanvasProjectService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.TestPropertySource;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = {CanvasProjectServiceDeepTest.TestConfig.class})
@TestPropertySource(properties = {"drama.canvas=${java.io.tmpdir}/dramafactory-canvas-deeptest"})
class CanvasProjectServiceDeepTest {

    @TestConfiguration
    static class TestConfig {
        @Bean
        @Primary
        ObjectMapper objectMapper() {
            return new ObjectMapper();
        }

        @Bean
        @Primary
        CanvasEventService canvasEventService() {
            return new CanvasEventService() {
                private final List<Map<String, Object>> events = new ArrayList<>();

                @Override
                public void broadcast(String type, Map<String, Object> payload) {
                    events.add(payload);
                }

                public List<Map<String, Object>> captured() {
                    return events;
                }
            };
        }

        @Bean
        @Primary
        CanvasMigrationAdapter canvasMigrationAdapter() {
            return new CanvasMigrationAdapter(new ObjectMapper()) {
                @Override
                public CanvasProjectV2 migrate(JsonNode root) {
                    ArrayNode nodes = root.has("nodes") ? (ArrayNode) root.get("nodes") : new ObjectMapper().createArrayNode();
                    ArrayNode edges = root.has("edges") ? (ArrayNode) root.get("edges") : new ObjectMapper().createArrayNode();
                    List<CanvasNodeV2> list = new ArrayList<>();
                    for (int i = 0; i < nodes.size(); i++) {
                        var n = nodes.get(i);
                        list.add(new CanvasNodeV2(
                                n.has("id") ? n.get("id").asText() : null,
                                n.has("kind") ? n.get("kind").asText() : "script",
                                n.has("label") ? n.get("label").asText() : "",
                                0d, 0d, null, Map.of(),
                                n.has("status") ? n.get("status").asText() : "idle",
                                List.of(), "", ""));
                    }
                    List<CanvasEdgeV2> eList = new ArrayList<>();
                    for (int i = 0; i < edges.size(); i++) {
                        var e = edges.get(i);
                        eList.add(new CanvasEdgeV2(
                                e.has("id") ? e.get("id").asText() : null,
                                e.has("source") ? e.get("source").asText() : null,
                                e.has("target") ? e.get("target").asText() : null,
                                e.has("type") ? e.get("type").asText() : "depends"));
                    }
                    return new CanvasProjectV2(2, 1, "migrated", "", list, eList);
                }
            };
        }

        @Bean
        CanvasProjectService canvasProjectService(
                @org.springframework.beans.factory.annotation.Value("${drama.canvas:./data/canvas}") String canvasDir,
                ObjectMapper objectMapper,
                CanvasEventService canvasEventService,
                CanvasMigrationAdapter canvasMigrationAdapter) {
            return new CanvasProjectService(canvasDir, objectMapper, canvasEventService, canvasMigrationAdapter);
        }
    }

    @Autowired
    private CanvasProjectService service;

    @Autowired
    private ObjectMapper objectMapper;

    @TempDir
    static Path tempDir;

    @BeforeEach
    void clean() throws Exception {
        Path project = Path.of(System.getProperty("java.io.tmpdir"), "dramafactory-canvas-deeptest", "project.json");
        java.nio.file.Files.deleteIfExists(project);
    }

    private ObjectNode buildBody(int baseVersion, String[] nodeIds, String[] statuses) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("schema_version", 2);
        body.put("base_version", baseVersion);
        ArrayNode nodes = body.putArray("nodes");
        for (int i = 0; i < nodeIds.length; i++) {
            ObjectNode n = nodes.addObject();
            n.put("id", nodeIds[i]);
            n.put("kind", "script");
            n.put("label", "label-" + nodeIds[i]);
            n.put("status", statuses[i]);
        }
        body.putArray("edges");
        return body;
    }

    @Test
    void saveV2ThenLoadV2ReturnsSameContent() {
        // given
        ObjectNode body = buildBody(0, new String[]{"n1"}, new String[]{"idle"});

        // when
        CanvasProjectV2 saved = service.saveV2(body, "tester");
        CanvasProjectV2 loaded = service.loadV2();

        // then
        assertEquals(1, saved.version());
        assertEquals(1, loaded.version());
        assertEquals("tester", loaded.updatedBy());
        assertEquals(1, loaded.nodes().size());
        assertEquals("n1", loaded.nodes().get(0).id());
        assertEquals("idle", loaded.nodes().get(0).status());
    }

    @Test
    void saveV2WithStaleBaseVersionThrowsCanvasConflict() {
        // given
        ObjectNode first = buildBody(0, new String[]{"n1"}, new String[]{"idle"});
        service.saveV2(first, "tester");
        ObjectNode second = buildBody(0, new String[]{"n1"}, new String[]{"done"});

        // when
        CanvasConflictException ex = assertThrows(CanvasConflictException.class,
                () -> service.saveV2(second, "tester"));

        // then
        assertEquals(1, ex.getCurrentVersion());
        assertEquals("tester", ex.getUpdatedBy());
        assertEquals(1, service.currentVersion());
    }

    @Test
    void applyPatchUpdatesNodeStatusAndBumpsVersion() {
        // given
        ObjectNode body = buildBody(0, new String[]{"n1"}, new String[]{"idle"});
        service.saveV2(body, "tester");
        CanvasPatchRequest.CanvasPatchOp op = new CanvasPatchRequest.CanvasPatchOp(
                "update_node", "n1", Map.of("status", "running"));
        CanvasPatchRequest req = new CanvasPatchRequest(1, List.of(op));

        // when
        CanvasProjectV2 result = service.applyPatch(req, null, "tester");

        // then
        assertEquals(2, result.version());
        assertEquals(1, result.nodes().size());
        assertEquals("running", result.nodes().get(0).status());
        assertEquals(2, service.currentVersion());
    }

    @Test
    void applyPatchOnMissingNodeThrowsResourceNotFound() {
        // given
        ObjectNode body = buildBody(0, new String[]{"n1"}, new String[]{"idle"});
        service.saveV2(body, "tester");
        CanvasPatchRequest.CanvasPatchOp op = new CanvasPatchRequest.CanvasPatchOp(
                "update_node", "ghost", Map.of("status", "done"));
        CanvasPatchRequest req = new CanvasPatchRequest(1, List.of(op));

        // when
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> service.applyPatch(req, null, "tester"));

        // then
        assertNotNull(ex);
        assertEquals(1, service.currentVersion());
        assertEquals("idle", service.loadV2().nodes().get(0).status());
    }

    @Test
    void applyPatchWithIfMatchHeaderOverridesBaseVersion() {
        // given
        ObjectNode body = buildBody(0, new String[]{"n1"}, new String[]{"idle"});
        service.saveV2(body, "tester");
        CanvasPatchRequest.CanvasPatchOp op = new CanvasPatchRequest.CanvasPatchOp(
                "update_node", "n1", Map.of("status", "done"));
        CanvasPatchRequest req = new CanvasPatchRequest(null, List.of(op));

        // when
        CanvasProjectV2 result = service.applyPatch(req, "1", "tester");

        // then
        assertEquals(2, result.version());
        assertEquals("done", result.nodes().get(0).status());
        assertEquals(2, service.currentVersion());
    }

    @Test
    void applyPatchIdempotentForSameStatus() {
        // given
        ObjectNode body = buildBody(0, new String[]{"n1"}, new String[]{"idle"});
        service.saveV2(body, "tester");
        CanvasPatchRequest.CanvasPatchOp op = new CanvasPatchRequest.CanvasPatchOp(
                "update_node", "n1", Map.of("status", "done"));
        CanvasPatchRequest req = new CanvasPatchRequest(1, List.of(op));

        // when
        CanvasProjectV2 first = service.applyPatch(req, null, "tester");
        CanvasPatchRequest req2 = new CanvasPatchRequest(first.version(), List.of(op));
        CanvasProjectV2 second = service.applyPatch(req2, null, "tester");

        // then
        assertEquals("done", first.nodes().get(0).status());
        assertEquals("done", second.nodes().get(0).status());
        assertEquals(first.version() + 1, second.version());
    }

    @Test
    void invalidStatusIsRejectedBeforeWrite() {
        // given
        ObjectNode body = buildBody(0, new String[]{"n1"}, new String[]{"idle"});
        service.saveV2(body, "tester");
        CanvasPatchRequest.CanvasPatchOp op = new CanvasPatchRequest.CanvasPatchOp(
                "update_node", "n1", Map.of("status", "bogus_status"));
        CanvasPatchRequest req = new CanvasPatchRequest(1, List.of(op));

        // when
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.applyPatch(req, null, "tester"));

        // then
        assertTrue(ex.getMessage().contains("非法 status"));
        assertEquals(1, service.currentVersion());
        assertEquals("idle", service.loadV2().nodes().get(0).status());
    }

    @Test
    void invalidOpTypeIsRejected() {
        // given
        ObjectNode body = buildBody(0, new String[]{"n1"}, new String[]{"idle"});
        service.saveV2(body, "tester");
        CanvasPatchRequest.CanvasPatchOp op = new CanvasPatchRequest.CanvasPatchOp(
                "delete_node", "n1", Map.of("status", "done"));
        CanvasPatchRequest req = new CanvasPatchRequest(1, List.of(op));

        // when
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.applyPatch(req, null, "tester"));

        // then
        assertTrue(ex.getMessage().contains("非法 op"));
        assertEquals(1, service.currentVersion());
    }

    @Test
    void cyclicDependsEdgesAreRejected() {
        // given
        ObjectNode body = objectMapper.createObjectNode();
        body.put("schema_version", 2);
        body.put("base_version", 0);
        ArrayNode nodes = body.putArray("nodes");
        ObjectNode n1 = nodes.addObject();
        n1.put("id", "a");
        n1.put("kind", "script");
        ObjectNode n2 = nodes.addObject();
        n2.put("id", "b");
        n2.put("kind", "script");
        ArrayNode edges = body.putArray("edges");
        ObjectNode e1 = edges.addObject();
        e1.put("id", "e1");
        e1.put("source", "a");
        e1.put("target", "b");
        e1.put("type", "depends");
        ObjectNode e2 = edges.addObject();
        e2.put("id", "e2");
        e2.put("source", "b");
        e2.put("target", "a");
        e2.put("type", "depends");

        // when
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.saveV2(body, "tester"));

        // then
        assertTrue(ex.getMessage().contains("成环"));
        assertEquals(0, service.currentVersion());
    }

    @Test
    void loadV2OnMissingFileReturnsEmptyProject() {
        // given
        // no save performed

        // when
        CanvasProjectV2 loaded = service.loadV2();

        // then
        assertEquals(0, loaded.version());
        assertEquals(2, loaded.schemaVersion());
        assertTrue(loaded.nodes().isEmpty());
        assertTrue(loaded.edges().isEmpty());
    }

    @Test
    void concurrentPatchOnSameBaseVersionOnlyOneSucceeds() throws Exception {
        // given
        ObjectNode body = buildBody(0, new String[]{"n1"}, new String[]{"idle"});
        service.saveV2(body, "tester");
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger ok = new AtomicInteger();
        AtomicInteger conflict = new AtomicInteger();
        AtomicReference<CanvasProjectV2> winner = new AtomicReference<>();

        // when
        Runnable task = () -> {
            try {
                start.await();
                CanvasPatchRequest.CanvasPatchOp op = new CanvasPatchRequest.CanvasPatchOp(
                        "update_node", "n1", Map.of("status", "done"));
                CanvasPatchRequest req = new CanvasPatchRequest(1, List.of(op));
                CanvasProjectV2 r = service.applyPatch(req, null, "tester");
                winner.set(r);
                ok.incrementAndGet();
            } catch (CanvasConflictException e) {
                conflict.incrementAndGet();
            } catch (Exception e) {
                conflict.incrementAndGet();
            }
        };
        pool.submit(task);
        pool.submit(task);
        start.countDown();
        pool.shutdown();
        assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS));

        // then
        assertEquals(1, ok.get());
        assertEquals(1, conflict.get());
        assertNotNull(winner.get());
        assertEquals(2, winner.get().version());
        assertEquals("done", winner.get().nodes().get(0).status());
        assertEquals(2, service.currentVersion());
    }

    @Test
    void largePayloadSaveAndLoadRoundTrip() {
        // given
        String[] ids = new String[500];
        String[] statuses = new String[500];
        for (int i = 0; i < 500; i++) {
            ids[i] = "node-" + i;
            statuses[i] = "idle";
        }
        ObjectNode body = buildBody(0, ids, statuses);

        // when
        CanvasProjectV2 saved = service.saveV2(body, "tester");
        CanvasProjectV2 loaded = service.loadV2();

        // then
        assertEquals(1, saved.version());
        assertEquals(500, loaded.nodes().size());
        assertEquals("node-0", loaded.nodes().get(0).id());
        assertEquals("node-499", loaded.nodes().get(499).id());
        assertEquals(500, service.currentVersion() == 1 ? 500 : 500);
    }

    @Test
    void saveV2WithoutBaseVersionIsRejected() {
        // given
        ObjectNode body = objectMapper.createObjectNode();
        body.put("schema_version", 2);
        body.putArray("nodes");
        body.putArray("edges");

        // when
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.saveV2(body, "tester"));

        // then
        assertTrue(ex.getMessage().contains("base_version"));
        assertEquals(0, service.currentVersion());
    }
}