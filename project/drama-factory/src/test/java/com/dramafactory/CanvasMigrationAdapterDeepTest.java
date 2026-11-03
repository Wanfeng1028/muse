package com.dramafactory;

import com.dramafactory.dto.canvas.CanvasEdgeV2;
import com.dramafactory.dto.canvas.CanvasNodeV2;
import com.dramafactory.dto.canvas.CanvasProjectV2;
import com.dramafactory.service.CanvasMigrationAdapter;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class CanvasMigrationAdapterDeepTest {

    @Autowired
    private CanvasMigrationAdapter adapter;

    @Autowired
    private ObjectMapper objectMapper;

    private JsonNode read(String json) throws Exception {
        return objectMapper.readTree(json);
    }

    @Test
    @DisplayName("空 Run 输入：oldRoot 为 null 时输出空节点空边且版本回退到 1")
    void migrate_nullRoot_returnsEmptyProjectWithVersionOne() {
        // given: 传入 null 作为旧 Run 的根节点
        JsonNode oldRoot = null;

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: 结果非空、schemaVersion 为 2、revision 为 1、节点与边都为空
        assertAll(
                () -> assertNotNull(project),
                () -> assertEquals(2, project.schemaVersion()),
                () -> assertEquals(1, project.version()),
                () -> assertEquals("editor", project.updatedBy()),
                () -> assertNotNull(project.nodes()),
                () -> assertTrue(project.nodes().isEmpty()),
                () -> assertNotNull(project.edges()),
                () -> assertTrue(project.edges().isEmpty())
        );
    }

    @Test
    @DisplayName("空对象 Run：没有 nodes/edges/revision 字段时使用默认值")
    void migrate_emptyObject_usesDefaults() throws Exception {
        // given: 一个空的 JSON 对象
        JsonNode oldRoot = read("{}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: revision 为 1，updatedBy 为 editor，节点边为空
        assertAll(
                () -> assertEquals(1, project.version()),
                () -> assertEquals("editor", project.updatedBy()),
                () -> assertTrue(project.nodes().isEmpty()),
                () -> assertTrue(project.edges().isEmpty())
        );
    }

    @Test
    @DisplayName("revision 与 updated_by 正常透传")
    void migrate_readsRevisionAndUpdatedBy() throws Exception {
        // given: 旧 Run 带有 revision 与 updated_by
        JsonNode oldRoot = read("{\"revision\":7,\"updated_by\":\"晚风\"}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: revision 与 updatedBy 原样透传
        assertAll(
                () -> assertEquals(7, project.version()),
                () -> assertEquals("晚风", project.updatedBy())
        );
    }

    @Test
    @DisplayName("revision 非整数时回退到 1，updated_by 非文本时回退到 editor")
    void migrate_invalidRevisionAndUpdatedBy_fallbacks() throws Exception {
        // given: revision 是字符串，updated_by 是数字
        JsonNode oldRoot = read("{\"revision\":\"abc\",\"updated_by\":123}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: 两者都使用默认值
        assertAll(
                () -> assertEquals(1, project.version()),
                () -> assertEquals("editor", project.updatedBy())
        );
    }

    @Test
    @DisplayName("节点字段完整映射：id/kind/label/x/y/status 全部落到 V2 节点")
    void migrate_mapsAllNodeFields() throws Exception {
        // given: 一个字段齐全的节点
        JsonNode oldRoot = read("{\"nodes\":[{\"id\":\"n1\",\"kind\":\"script\",\"label\":\"开场\",\"x\":12.5,\"y\":30.25,\"status\":\"running\"}]}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: 节点数量为 1 且各字段正确
        CanvasNodeV2 node = project.nodes().get(0);
        assertAll(
                () -> assertEquals(1, project.nodes().size()),
                () -> assertEquals("n1", node.id()),
                () -> assertEquals("script", node.kind()),
                () -> assertEquals("开场", node.label()),
                () -> assertEquals(12.5, node.x()),
                () -> assertEquals(30.25, node.y()),
                () -> assertEquals("running", node.status())
        );
    }

    @Test
    @DisplayName("节点缺省字段：kind 默认 script，label 默认空串，status 默认 idle，x/y 默认 0")
    void migrate_nodeDefaults() throws Exception {
        // given: 只有一个 id 的节点
        JsonNode oldRoot = read("{\"nodes\":[{\"id\":\"n2\"}]}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: 缺省字段使用默认值
        CanvasNodeV2 node = project.nodes().get(0);
        assertAll(
                () -> assertEquals("n2", node.id()),
                () -> assertEquals("script", node.kind()),
                () -> assertEquals("", node.label()),
                () -> assertEquals(0d, node.x()),
                () -> assertEquals(0d, node.y()),
                () -> assertEquals("idle", node.status())
        );
    }

    @Test
    @DisplayName("节点缺 id：id 为 null，其它字段仍按默认值填充")
    void migrate_nodeWithoutId_idIsNull() throws Exception {
        // given: 没有 id 字段的节点
        JsonNode oldRoot = read("{\"nodes\":[{\"label\":\"无主节点\"}]}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: id 为 null，label 正确
        CanvasNodeV2 node = project.nodes().get(0);
        assertAll(
                () -> assertNull(node.id()),
                () -> assertEquals("无主节点", node.label()),
                () -> assertEquals("script", node.kind())
        );
    }

    @Test
    @DisplayName("x/y 非数字时回退到 0")
    void migrate_nodeNonNumericXY_fallbackToZero() throws Exception {
        // given: x 是字符串，y 是布尔
        JsonNode oldRoot = read("{\"nodes\":[{\"id\":\"n3\",\"x\":\"abc\",\"y\":true}]}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: x 与 y 都是 0
        CanvasNodeV2 node = project.nodes().get(0);
        assertAll(
                () -> assertEquals(0d, node.x()),
                () -> assertEquals(0d, node.y())
        );
    }

    @Test
    @DisplayName("边字段完整映射：id/source/target/type 全部落到 V2 边")
    void migrate_mapsAllEdgeFields() throws Exception {
        // given: 一个 type 为 ref 的边
        JsonNode oldRoot = read("{\"edges\":[{\"id\":\"e1\",\"source\":\"n1\",\"target\":\"n2\",\"type\":\"ref\"}]}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: 边数量为 1 且字段正确
        CanvasEdgeV2 edge = project.edges().get(0);
        assertAll(
                () -> assertEquals(1, project.edges().size()),
                () -> assertEquals("e1", edge.id()),
                () -> assertEquals("n1", edge.source()),
                () -> assertEquals("n2", edge.target()),
                () -> assertEquals("ref", edge.type())
        );
    }

    @Test
    @DisplayName("非法边 type 回退到 depends，null type 也回退到 depends")
    void migrate_invalidEdgeType_fallbackToDepends() throws Exception {
        // given: 两条边，一条 type 非法，一条 type 缺失
        JsonNode oldRoot = read("{\"edges\":[{\"id\":\"e1\",\"source\":\"a\",\"target\":\"b\",\"type\":\"unknown\"},{\"id\":\"e2\",\"source\":\"b\",\"target\":\"c\"}]}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: 两条边的 type 都是 depends
        assertAll(
                () -> assertEquals(2, project.edges().size()),
                () -> assertEquals("depends", project.edges().get(0).type()),
                () -> assertEquals("depends", project.edges().get(1).type())
        );
    }

    @Test
    @DisplayName("边 type 为 depends 时保持 depends 不变")
    void migrate_validEdgeTypeDepends_kept() throws Exception {
        // given: 一条 type 为 depends 的边
        JsonNode oldRoot = read("{\"edges\":[{\"id\":\"e1\",\"source\":\"a\",\"target\":\"b\",\"type\":\"depends\"}]}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: type 仍是 depends
        assertAll(
                () -> assertEquals(1, project.edges().size()),
                () -> assertEquals("depends", project.edges().get(0).type())
        );
    }

    @Test
    @DisplayName("nodes 非数组时忽略，不抛异常")
    void migrate_nodesNotArray_ignored() throws Exception {
        // given: nodes 是字符串
        JsonNode oldRoot = read("{\"nodes\":\"not-an-array\"}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: 节点列表为空
        assertAll(
                () -> assertNotNull(project.nodes()),
                () -> assertTrue(project.nodes().isEmpty())
        );
    }

    @Test
    @DisplayName("edges 非数组时忽略，不抛异常")
    void migrate_edgesNotArray_ignored() throws Exception {
        // given: edges 是数字
        JsonNode oldRoot = read("{\"edges\":42}");

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: 边列表为空
        assertAll(
                () -> assertNotNull(project.edges()),
                () -> assertTrue(project.edges().isEmpty())
        );
    }

    @Test
    @DisplayName("幂等性：同一输入连续迁移两次结果一致（revision/updatedBy/节点/边）")
    void migrate_sameInputTwice_isIdempotent() throws Exception {
        // given: 一份包含节点与边的输入
        JsonNode oldRoot = read("{\"revision\":3,\"updated_by\":\"editor\",\"nodes\":[{\"id\":\"n1\",\"kind\":\"script\",\"label\":\"a\",\"x\":1,\"y\":2,\"status\":\"idle\"}],\"edges\":[{\"id\":\"e1\",\"source\":\"n1\",\"target\":\"n1\",\"type\":\"depends\"}]}");

        // when: 连续迁移两次
        CanvasProjectV2 first = adapter.migrate(oldRoot);
        CanvasProjectV2 second = adapter.migrate(oldRoot);

        // then: 关键字段完全一致
        assertAll(
                () -> assertEquals(first.schemaVersion(), second.schemaVersion()),
                () -> assertEquals(first.version(), second.version()),
                () -> assertEquals(first.updatedBy(), second.updatedBy()),
                () -> assertEquals(first.nodes().size(), second.nodes().size()),
                () -> assertEquals(first.edges().size(), second.edges().size()),
                () -> assertEquals(first.nodes().get(0).id(), second.nodes().get(0).id()),
                () -> assertEquals(first.edges().get(0).id(), second.edges().get(0).id())
        );
    }

    @Test
    @DisplayName("超大 payload：1000 个节点与 1000 条边全部迁移成功")
    void migrate_largePayload_allMigrated() throws Exception {
        // given: 构造 1000 个节点与 1000 条边
        StringBuilder sb = new StringBuilder();
        sb.append("{\"revision\":9,\"updated_by\":\"editor\",\"nodes\":[");
        for (int i = 0; i < 1000; i++) {
            if (i > 0) {
                sb.append(",");
            }
            sb.append("{\"id\":\"n").append(i).append("\",\"kind\":\"script\",\"label\":\"L").append(i).append("\",\"x\":").append(i).append(",\"y\":").append(i).append(",\"status\":\"idle\"}");
        }
        sb.append("],\"edges\":[");
        for (int i = 0; i < 1000; i++) {
            if (i > 0) {
                sb.append(",");
            }
            sb.append("{\"id\":\"e").append(i).append("\",\"source\":\"n").append(i).append("\",\"target\":\"n").append((i + 1) % 1000).append("\",\"type\":\"depends\"}");
        }
        sb.append("]}");
        JsonNode oldRoot = read(sb.toString());

        // when: 执行迁移
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        // then: 节点与边数量都等于 1000，首尾节点 id 正确
        assertAll(
                () -> assertEquals(1000, project.nodes().size()),
                () -> assertEquals(1000, project.edges().size()),
                () -> assertEquals("n0", project.nodes().get(0).id()),
                () -> assertEquals("n999", project.nodes().get(999).id()),
                () -> assertEquals("e0", project.edges().get(0).id()),
                () -> assertEquals("e999", project.edges().get(999).id())
        );
    }

    @Test
    @DisplayName("并发：两线程同时迁移同一输入，各自结果与单线程结果一致，数据不坏")
    void migrate_concurrentSameInput_resultsConsistent() throws Exception {
        // given: 一份固定输入，两线程用同一个 adapter 同时迁移
        final JsonNode oldRoot = read("{\"revision\":5,\"updated_by\":\"editor\",\"nodes\":[{\"id\":\"n1\",\"kind\":\"script\",\"label\":\"a\",\"x\":1,\"y\":2,\"status\":\"idle\"}],\"edges\":[{\"id\":\"e1\",\"source\":\"n1\",\"target\":\"n1\",\"type\":\"ref\"}]}");
        final CanvasProjectV2 baseline = adapter.migrate(oldRoot);
        final CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        Callable<CanvasProjectV2> task = () -> {
            start.await();
            return adapter.migrate(oldRoot);
        };

        // when: 同时启动两个线程
        Future<CanvasProjectV2> f1 = pool.submit(task);
        Future<CanvasProjectV2> f2 = pool.submit(task);
        start.countDown();
        CanvasProjectV2 r1 = f1.get(10, TimeUnit.SECONDS);
        CanvasProjectV2 r2 = f2.get(10, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then: 两份结果与基线一致，节点边字段都正确
        assertAll(
                () -> assertEquals(baseline.version(), r1.version()),
                () -> assertEquals(baseline.version(), r2.version()),
                () -> assertEquals(baseline.updatedBy(), r1.updatedBy()),
                () -> assertEquals(baseline.updatedBy(), r2.updatedBy()),
                () -> assertEquals(1, r1.nodes().size()),
                () -> assertEquals(1, r2.nodes().size()),
                () -> assertEquals("n1", r1.nodes().get(0).id()),
                () -> assertEquals("n1", r2.nodes().get(0).id()),
                () -> assertEquals("ref", r1.edges().get(0).type()),
                () -> assertEquals("ref", r2.edges().get(0).type())
        );
    }
}