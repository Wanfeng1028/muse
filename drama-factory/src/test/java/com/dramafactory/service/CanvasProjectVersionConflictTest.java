package com.dramafactory.service;
import com.dramafactory.dto.canvas.*;

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
        return new CanvasProjectService(dir.toString(), om, new CanvasEventService(), new CanvasMigrationAdapter(om));
    }

    private ObjectNode bodyWithBase(int base) {
        ObjectNode p = om.createObjectNode();
        p.put("schema_version", 2);
        p.set("nodes", om.createArrayNode());
        p.set("edges", om.createArrayNode());
        p.put("base_version", base);
        return p;
    }

    @Test
    void saveWithoutBaseVersion_throws400(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        ObjectNode body = om.createObjectNode();
        body.put("schema_version", 2);
        body.set("nodes", om.createArrayNode());
        body.set("edges", om.createArrayNode());
        assertThrows(IllegalArgumentException.class, () -> service.saveV2(body, "editor"));
    }

    @Test
    void saveWithStaleBaseVersion_throws409(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        // 空项目版本号为 0（见 emptyV2），首次保存用 base 0
        service.saveV2(bodyWithBase(0), "editor");
        CanvasConflictException ex = assertThrows(CanvasConflictException.class,
                () -> service.saveV2(bodyWithBase(0), "agent"));
        assertEquals(1, ex.getCurrentVersion());
        assertEquals("editor", ex.getUpdatedBy());
    }

    @Test
    void bidirectionalConflict_editorStaleAfterAgentWrite(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        service.saveV2(bodyWithBase(0), "editor");
        service.saveV2(bodyWithBase(1), "agent");
        CanvasConflictException ex = assertThrows(CanvasConflictException.class,
                () -> service.saveV2(bodyWithBase(1), "editor"));
        assertEquals(2, ex.getCurrentVersion());
        assertEquals("agent", ex.getUpdatedBy());
    }

    @Test
    void saveReturnsIncrementedVersion(@TempDir Path dir) throws Exception {
        CanvasProjectService service = newService(dir);
        CanvasProjectV2 saved = service.saveV2(bodyWithBase(0), "editor");
        assertEquals(1, saved.version());
        assertEquals("editor", saved.updatedBy());
        String onDisk = Files.readString(dir.resolve("project.json"));
        assertFalse(onDisk.contains("\"base_version\""), "落盘 JSON 不应包含 base_version 字段");
        assertTrue(onDisk.contains("\"schema_version\""), "落盘应为 v2 形状");
    }

    @Test
    void loadNormalizesLegacyFile(@TempDir Path dir) throws Exception {
        ObjectNode legacy = om.createObjectNode();
        legacy.put("version", 1);
        legacy.put("revision", 6);
        legacy.put("updated_by", "editor");
        legacy.set("nodes", om.createArrayNode());
        legacy.set("edges", om.createArrayNode());
        Files.writeString(dir.resolve("project.json"), om.writeValueAsString(legacy));
        CanvasProjectService service = newService(dir);
        CanvasProjectV2 loaded = service.loadV2();
        assertEquals(2, loaded.schemaVersion());
        assertEquals(6, loaded.version());
        assertEquals("editor", loaded.updatedBy());
    }

    @Test
    void saveWithNonIntBaseVersion_throws400(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        ObjectNode body = bodyWithBase(1);
        body.put("base_version", "1");
        assertThrows(IllegalArgumentException.class, () -> service.saveV2(body, "editor"));
    }

    @Test
    void concurrentSave_sameBaseVersion_onlyOneWins(@TempDir Path dir) throws Exception {
        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        try {
            for (int round = 0; round < 20; round++) {
                Path roundDir = dir.resolve("round-" + round);
                CanvasProjectService service = newService(roundDir);
                CountDownLatch startGate = new CountDownLatch(1);
                CountDownLatch doneGate = new CountDownLatch(threads);
                AtomicInteger successCount = new AtomicInteger(0);
                AtomicInteger conflictCount = new AtomicInteger(0);
                AtomicInteger otherCount = new AtomicInteger(0);
                for (int i = 0; i < threads; i++) {
                    pool.submit(() -> {
                        try {
                            startGate.await();
                            service.saveV2(bodyWithBase(1), "editor");
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
                assertTrue(doneGate.await(10, TimeUnit.SECONDS), "第" + round + "轮：并发保存未在超时内完成");
                assertEquals(0, otherCount.get(), "第" + round + "轮：出现了非 CanvasConflictException 的异常");
                assertEquals(1, successCount.get(), "第" + round + "轮：恰好应有 1 个线程保存成功");
                assertEquals(7, conflictCount.get(), "第" + round + "轮：其余 7 线程应全部抛 CanvasConflictException");
                assertEquals(2, service.loadV2().version(), "第" + round + "轮：最终 version 应为 base+1");
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
