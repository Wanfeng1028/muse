package com.dramafactory.service;

import com.dramafactory.exception.CanvasConflictException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class CanvasProjectVersionConflictTest {

    private final ObjectMapper om = new ObjectMapper();

    private CanvasProjectService newService(Path dir) {
        return new CanvasProjectService(dir.toString(), om);
    }

    private ObjectNode bodyWithBase(int base) {
        ObjectNode p = om.createObjectNode();
        p.put("version", 1);
        p.set("nodes", om.createArrayNode());
        p.set("edges", om.createArrayNode());
        p.put("base_version", base);
        return p;
    }

    @Test
    void saveWithoutBaseVersion_throws400(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);

        ObjectNode body = om.createObjectNode();
        body.put("version", 1);
        body.set("nodes", om.createArrayNode());
        body.set("edges", om.createArrayNode());

        assertThrows(IllegalArgumentException.class, () -> service.save(body));
    }

    @Test
    void saveWithStaleBaseVersion_throws409(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);

        service.save(bodyWithBase(1), "editor");

        CanvasConflictException ex = assertThrows(
                CanvasConflictException.class,
                () -> service.save(bodyWithBase(1), "agent"));

        assertEquals(2, ex.getCurrentVersion());
        assertEquals("editor", ex.getUpdatedBy());
    }

    @Test
    void bidirectionalConflict_editorStaleAfterAgentWrite(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);

        // editor PUT 成功：revision 1 -> 2，updated_by = editor
        service.save(bodyWithBase(1), "editor");

        // agent patch 成功：revision 2 -> 3，updated_by = agent
        service.save(bodyWithBase(2), "agent");

        // editor 再次 PUT，仍带过期的 base_version=2 -> 冲突
        CanvasConflictException ex = assertThrows(
                CanvasConflictException.class,
                () -> service.save(bodyWithBase(2), "editor"));

        assertEquals(3, ex.getCurrentVersion());
        assertEquals("agent", ex.getUpdatedBy());
    }

    @Test
    void saveReturnsIncrementedRevision(@TempDir Path dir) throws Exception {
        CanvasProjectService service = newService(dir);

        JsonNode saved = service.save(bodyWithBase(1), "editor");

        assertEquals(2, saved.get("revision").asInt());
        assertEquals("editor", saved.get("updated_by").asText());

        String onDisk = Files.readString(dir.resolve("project.json"));
        assertFalse(onDisk.contains("\"base_version\""),
                "落盘 JSON 不应包含 base_version 字段");
    }

    @Test
    void loadNormalizesLegacyFile(@TempDir Path dir) throws Exception {
        ObjectNode legacy = om.createObjectNode();
        legacy.put("version", 1);
        legacy.set("nodes", om.createArrayNode());
        legacy.set("edges", om.createArrayNode());

        Files.writeString(
                dir.resolve("project.json"),
                om.writeValueAsString(legacy));

        CanvasProjectService service = newService(dir);
        JsonNode loaded = service.load();

        assertEquals(1, loaded.get("revision").asInt());
        assertEquals("editor", loaded.get("updated_by").asText());
    }

    @Test
    void saveWithNonIntBaseVersion_throws400(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);

        ObjectNode body = om.createObjectNode();
        body.put("version", 1);
        body.set("nodes", om.createArrayNode());
        body.set("edges", om.createArrayNode());
        body.put("base_version", "1");

        assertThrows(IllegalArgumentException.class, () -> service.save(body));
    }

    @Test
    void concurrentSave_sameBaseVersion_onlyOneWins(@TempDir Path dir) throws Exception {
        CanvasProjectService service = newService(dir);
        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneGate = new CountDownLatch(threads);
        AtomicInteger successCount = new AtomicInteger(0);
        AtomicInteger conflictCount = new AtomicInteger(0);
        AtomicInteger otherCount = new AtomicInteger(0);
        try {
            for (int i = 0; i < threads; i++) {
                pool.submit(() -> {
                    try {
                        startGate.await();
                        service.save(bodyWithBase(1), "editor");
                        successCount.incrementAndGet();
                    } catch (CanvasConflictException e) {
                        conflictCount.incrementAndGet();
                    } catch (Exception e) {
                        otherCount.incrementAndGet();
                    } finally {
                        doneGate.countDown();
                    }
                });
            }
            startGate.countDown();
            assertTrue(doneGate.await(10, TimeUnit.SECONDS), "并发保存未在超时内完成");
        } finally {
            pool.shutdownNow();
        }
        assertEquals(0, otherCount.get(), "出现了非 CanvasConflictException 的异常");
        assertEquals(1, successCount.get(), "恰好应有 1 个线程保存成功");
        assertEquals(threads - 1, conflictCount.get(), "其余线程应全部抛 CanvasConflictException");
        assertEquals(2, service.load().get("revision").asInt(), "最终 revision 应为 base+1");
    }
}
