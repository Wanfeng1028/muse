package com.dramafactory.service;
import com.dramafactory.dto.canvas.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class CanvasMigrationAdapterTest {

    private final ObjectMapper om = new ObjectMapper();

    private ObjectNode legacyRoot() {
        ObjectNode root = om.createObjectNode();
        root.put("version", 1);
        root.put("revision", 6);
        root.put("updated_by", "editor");
        root.put("updated_at", "2024-01-01T00:00:00Z");

        var nodes = om.createArrayNode();

        ObjectNode n1 = om.createObjectNode();
        n1.put("id", "n1");
        n1.put("kind", "shot");
        n1.put("label", "Shot 1");
        n1.put("x", 10);
        n1.put("y", 20);
        nodes.add(n1);

        ObjectNode n2 = om.createObjectNode();
        n2.put("id", "n2");
        n2.put("kind", "shot");
        n2.put("label", "Shot 2");
        n2.put("x", 30);
        n2.put("y", 40);
        nodes.add(n2);

        ObjectNode n3 = om.createObjectNode();
        n3.put("id", "n3");
        n3.put("kind", "asset");
        n3.put("label", "Asset 3");
        n3.put("x", 50);
        n3.put("y", 60);
        nodes.add(n3);

        root.set("nodes", nodes);
        root.set("edges", om.createArrayNode());
        return root;
    }

    @Test
    void migrate_upgradesLegacyRootToV2() {
        CanvasMigrationAdapter adapter = new CanvasMigrationAdapter(om);
        JsonNode oldRoot = legacyRoot();
        CanvasProjectV2 project = adapter.migrate(oldRoot);

        assertEquals(2, project.schemaVersion());
        assertEquals(6, project.version());
        assertEquals("editor", project.updatedBy());

        List<CanvasNodeV2> nodes = project.nodes();
        assertEquals(3, nodes.size());

        for (CanvasNodeV2 n : nodes) {
            assertNull(n.shotRef(), "shot_ref 应补齐为 null, node=" + n.id());
            assertNotNull(n.params(), "params 应补齐, node=" + n.id());
            assertTrue(n.params().isEmpty(), "params 应为空对象, node=" + n.id());
            assertNotNull(n.assetRefs(), "asset_refs 应补齐, node=" + n.id());
            assertTrue(n.assetRefs().isEmpty(), "asset_refs 应为空数组, node=" + n.id());
            assertNotNull(n.updatedAt(), "updated_at 应补齐, node=" + n.id());
            assertNotNull(n.updatedBy(), "updated_by 应补齐, node=" + n.id());
        }

        assertTrue(project.edges().isEmpty());
    }

    @Test
    void migrate_defaultsEdgeTypeToDepends() {
        CanvasMigrationAdapter adapter = new CanvasMigrationAdapter(om);
        JsonNode oldRoot = legacyRoot();
        var edges = (com.fasterxml.jackson.databind.node.ArrayNode) oldRoot.get("edges");
        ObjectNode e = om.createObjectNode();
        e.put("id", "e1");
        e.put("source", "n1");
        e.put("target", "n2");
        edges.add(e);

        CanvasProjectV2 project = adapter.migrate(oldRoot);
        assertEquals(1, project.edges().size());
        CanvasEdgeV2 edge = project.edges().get(0);
        assertEquals("e1", edge.id());
        assertEquals("n1", edge.source());
        assertEquals("n2", edge.target());
        assertEquals("depends", edge.type());
    }

    @Test
    void migrate_isReadOnly_doesNotMutateInput() {
        CanvasMigrationAdapter adapter = new CanvasMigrationAdapter(om);
        JsonNode oldRoot = legacyRoot();
        String before = oldRoot.toString();

        adapter.migrate(oldRoot);
        adapter.migrate(oldRoot);

        String after = oldRoot.toString();
        assertEquals(before, after, "migrate 不应修改输入 JsonNode");
        assertFalse(oldRoot.has("schema_version"), "输入不应被写入 schema_version");
        assertEquals(1, oldRoot.get("version").asInt(), "输入 version 不应被改写");
    }
}
