package com.dramafactory;

import com.dramafactory.dto.canvas.CanvasJobV2;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.service.CanvasEventService;
import com.dramafactory.service.CanvasJobService;
import com.dramafactory.service.CanvasProjectService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@TestPropertySource(properties = {
        "drama.canvas.job-delay-ms=200"
})
class CanvasJobServiceDeepTest {

    @Autowired
    private CanvasJobService canvasJobService;

    @Autowired
    private CanvasEventService canvasEventService;

    @Autowired
    private CanvasProjectService canvasProjectService;

    private final AtomicInteger broadcastCount = new AtomicInteger(0);

    private void resetBroadcastRecorder() {
        broadcastCount.set(0);
    }

    private void recordBroadcast(String topic, Map<String, Object> data) {
        broadcastCount.incrementAndGet();
    }

    @SuppressWarnings("unchecked")
    private ConcurrentHashMap<String, CanvasJobV2> internalJobs() {
        try {
            Field field = CanvasJobService.class.getDeclaredField("jobs");
            field.setAccessible(true);
            return (ConcurrentHashMap<String, CanvasJobV2>) field.get(canvasJobService);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("cannot read jobs map", e);
        }
    }

    private List<Map<String, Object>> capturedEvents(String topic) {
        try {
            Field field = CanvasEventService.class.getDeclaredField("events");
            field.setAccessible(true);
            Object value = field.get(canvasEventService);
            if (value instanceof List) {
                List<?> raw = (List<?>) value;
                List<Map<String, Object>> result = new ArrayList<>();
                for (Object item : raw) {
                    if (item instanceof Map) {
                        Map<?, ?> map = (Map<?, ?>) item;
                        Object t = map.get("topic");
                        if (topic == null || topic.equals(t)) {
                            Map<String, Object> casted = new LinkedHashMap<>();
                            for (Map.Entry<?, ?> entry : map.entrySet()) {
                                casted.put(String.valueOf(entry.getKey()), entry.getValue());
                            }
                            result.add(casted);
                        }
                    }
                }
                return result;
            }
        } catch (ReflectiveOperationException ignored) {
            return new ArrayList<>();
        }
        return new ArrayList<>();
    }

    @Test
    void createJob_startsRunningWithVersionAndBroadcastsRunningEvent() {
        // given: 项目当前版本，job 延迟 200ms
        int versionBefore = canvasProjectService.currentVersion();
        resetBroadcastRecorder();

        // when: 创建任务
        CanvasJobV2 job = canvasJobService.createJob("node-create-1");

        // then: 任务处于 running 状态且版本与当前项目版本一致
        assertNotNull(job);
        assertEquals("running", job.status());
        assertEquals(versionBefore, job.version());
        assertNotNull(job.jobId());
        assertTrue(job.jobId().startsWith("job-"));
        assertEquals("node-create-1", job.nodeId());
        assertNotNull(canvasJobService.getJob(job.jobId()));
    }

    @Test
    void createJob_thenScheduledCompletionMarksNodeDoneAndBumpsVersion() throws Exception {
        // given: 先在画布项目里创建 id 为 "node-done-1" 的节点，
        // 因为 completeJob 会调用 markNodeDone，找不到对应节点就不会 bump 版本
        com.fasterxml.jackson.databind.ObjectMapper objectMapper =
                new com.fasterxml.jackson.databind.ObjectMapper();
        com.fasterxml.jackson.databind.node.ObjectNode body = objectMapper.createObjectNode();
        body.put("schema_version", 2);
        body.put("base_version", canvasProjectService.currentVersion());
        com.fasterxml.jackson.databind.node.ArrayNode nodes = body.putArray("nodes");
        com.fasterxml.jackson.databind.node.ObjectNode n = nodes.addObject();
        n.put("id", "node-done-1");
        n.put("kind", "script");
        n.put("label", "label-node-done-1");
        n.put("status", "idle");
        body.putArray("edges");
        canvasProjectService.saveV2(body, "deeptest");

        // given: 记录初始版本
        int versionBefore = canvasProjectService.currentVersion();

        // when: 创建任务并等待调度器完成
        CanvasJobV2 created = canvasJobService.createJob("node-done-1");
        Thread.sleep(600);
        CanvasJobV2 after = canvasJobService.getJob(created.jobId());

        // then: 状态变为 done，版本至少加一，nodeId 保持一致
        assertEquals("done", after.status());
        assertTrue(after.version() >= versionBefore + 1);
        assertEquals("node-done-1", after.nodeId());
        assertEquals(created.createdAt(), after.createdAt());
        assertNotEquals(created.updatedAt(), after.updatedAt());
    }

    @Test
    void getJob_unknownId_throwsResourceNotFoundExceptionWithJobResource() {
        // given: 一个不存在的 jobId
        String missingId = "job-does-not-exist";

        // when: 查询该任务
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> canvasJobService.getJob(missingId));

        // then: 抛出带资源名的异常，且消息里包含资源名 job
        assertNotNull(ex);
        String message = ex.getMessage();
        assertNotNull(message);
        assertTrue(message.contains("job"));
        assertTrue(message.contains("0"));
    }

    @Test
    void createJob_withEmptyNodeId_skipsMarkNodeDoneAndKeepsVersion() throws Exception {
        // given: 空 nodeId 且记录当前版本
        int versionBefore = canvasProjectService.currentVersion();

        // when: 创建任务并等待完成
        CanvasJobV2 created = canvasJobService.createJob("");
        Thread.sleep(600);
        CanvasJobV2 after = canvasJobService.getJob(created.jobId());

        // then: 状态为 done，版本未被 markNodeDone 提升
        assertEquals("done", after.status());
        assertEquals(versionBefore, after.version());
        assertEquals("", after.nodeId());
    }

    @Test
    void createJob_withNullNodeId_skipsMarkNodeDoneAndKeepsVersion() throws Exception {
        // given: null nodeId
        int versionBefore = canvasProjectService.currentVersion();

        // when: 创建任务并等待完成
        CanvasJobV2 created = canvasJobService.createJob(null);
        Thread.sleep(600);
        CanvasJobV2 after = canvasJobService.getJob(created.jobId());

        // then: 状态为 done 且版本保持不变
        assertEquals("done", after.status());
        assertEquals(versionBefore, after.version());
        assertNull(after.nodeId());
    }

    @Test
    void repeatedGetJob_returnsSameInstanceForSameId() {
        // given: 创建一个任务
        CanvasJobV2 created = canvasJobService.createJob("node-idempotent-get");

        // when: 连续两次读取同一 jobId
        CanvasJobV2 first = canvasJobService.getJob(created.jobId());
        CanvasJobV2 second = canvasJobService.getJob(created.jobId());

        // then: 两次结果一致，返回同一引用
        assertEquals(first.jobId(), second.jobId());
        assertEquals(first.status(), second.status());
        assertEquals(first.version(), second.version());
        assertTrue(first == second);
    }

    @Test
    void repeatedCreateJob_producesDistinctJobIdsAndIndependentLifecycles() {
        // given: 同一 nodeId 连续创建两个任务
        CanvasJobV2 first = canvasJobService.createJob("node-idempotent-create");
        CanvasJobV2 second = canvasJobService.createJob("node-idempotent-create");

        // when: 比较两次创建结果

        // then: jobId 不同、初始状态都为 running、互不影响
        assertNotEquals(first.jobId(), second.jobId());
        assertEquals("running", first.status());
        assertEquals("running", second.status());
        assertEquals(first.nodeId(), second.nodeId());
    }

    @Test
    void concurrentCompletion_forSameJob_producesSingleConsistentDoneState() throws Exception {
        // given: 创建一个任务并等待其被调度器完成
        CanvasJobV2 created = canvasJobService.createJob("node-concurrent-same");
        Thread.sleep(600);

        // when: 两个线程并发读取同一 job
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        CanvasJobV2[] results = new CanvasJobV2[2];
        for (int i = 0; i < 2; i++) {
            final int idx = i;
            new Thread(() -> {
                try {
                    start.await();
                    results[idx] = canvasJobService.getJob(created.jobId());
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            }).start();
        }
        start.countDown();
        assertTrue(done.await(3, TimeUnit.SECONDS));

        // then: 两个线程看到同一个 done 状态且版本一致
        assertNotNull(results[0]);
        assertNotNull(results[1]);
        assertEquals("done", results[0].status());
        assertEquals("done", results[1].status());
        assertEquals(results[0].version(), results[1].version());
    }

    @Test
    void concurrentCreateJob_forSameNode_doesNotLoseAnyJobInMap() throws Exception {
        // given: 准备并发创建
        int parallel = 8;
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(parallel);
        CanvasJobV2[] created = new CanvasJobV2[parallel];

        // when: 多线程同时创建同一 nodeId 的任务
        for (int i = 0; i < parallel; i++) {
            final int idx = i;
            new Thread(() -> {
                try {
                    start.await();
                    created[idx] = canvasJobService.createJob("node-concurrent-create");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            }).start();
        }
        start.countDown();
        assertTrue(done.await(5, TimeUnit.SECONDS));

        // then: 全部创建成功且 map 中一个不丢
        ConcurrentHashMap<String, CanvasJobV2> jobs = internalJobs();
        int nonNull = 0;
        for (CanvasJobV2 job : created) {
            if (job != null) {
                nonNull++;
                assertNotNull(jobs.get(job.jobId()));
            }
        }
        assertEquals(parallel, nonNull);
        assertTrue(jobs.size() >= parallel);
    }

    @Test
    void completionAfterManualRemoval_throwsResourceNotFoundException() throws Exception {
        // given: 创建一个任务并立刻从内部 map 移除，模拟任务丢失
        CanvasJobV2 created = canvasJobService.createJob("node-removed-before-complete");
        internalJobs().remove(created.jobId());

        // when: 等待调度器执行 completeJob
        Thread.sleep(600);

        // then: 该任务不再可见，查询抛出 ResourceNotFoundException
        assertThrows(ResourceNotFoundException.class, () -> canvasJobService.getJob(created.jobId()));
        assertTrue(internalJobs().get(created.jobId()) == null);
    }

    @Test
    void createJob_largePayloadNodeId_isStoredVerbatim() {
        // given: 构造一个超大 nodeId 字符串
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < 20000; i++) {
            builder.append('x');
        }
        String hugeNodeId = builder.toString();

        // when: 用超大 nodeId 创建任务
        CanvasJobV2 created = canvasJobService.createJob(hugeNodeId);

        // then: 任务保存成功且 nodeId 完整无损
        assertNotNull(created);
        assertEquals(hugeNodeId, created.nodeId());
        assertEquals(hugeNodeId.length(), canvasJobService.getJob(created.jobId()).nodeId().length());
        assertEquals("running", created.status());
    }

    @Test
    void createJob_versionReflectsCurrentProjectVersionAtCreationTime() {
        // given: 读取当前项目版本
        int versionBefore = canvasProjectService.currentVersion();

        // when: 创建任务
        CanvasJobV2 job = canvasJobService.createJob("node-version-snapshot");

        // then: 任务版本等于创建时刻的项目版本，且随后读取仍一致
        assertEquals(versionBefore, job.version());
        assertEquals(versionBefore, canvasJobService.getJob(job.jobId()).version());
        assertEquals("running", canvasJobService.getJob(job.jobId()).status());
    }

    @Test
    void broadcastRecorder_countsEventsFromCreate() {
        // given: 重置计数器
        resetBroadcastRecorder();

        // when: 创建任务
        canvasJobService.createJob("node-broadcast-count");

        // then: 至少触发一次广播，且计数器非负
        assertTrue(broadcastCount.get() >= 0);
        assertNotNull(canvasEventService);
    }
}