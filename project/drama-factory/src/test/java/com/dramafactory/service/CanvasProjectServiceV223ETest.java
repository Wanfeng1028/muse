package com.dramafactory.service;
import com.dramafactory.dto.canvas.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CanvasProjectServiceV223ETest {

    private final ObjectMapper om = new ObjectMapper();

    private CanvasProjectService newService(Path dir) {
        return new CanvasProjectService(dir.toString(), om, new CanvasEventService(), new CanvasMigrationAdapter(om));
    }

    private ObjectNode v2Body(int base) {
        ObjectNode p = om.createObjectNode();
        p.put("schema_version", 2);
        p.set("nodes", om.createArrayNode());
        p.set("edges", om.createArrayNode());
        p.put("base_version", base);
        return p;
    }

    @Test
    void emptyProject_hasSchemaVersion2AndVersion1(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        CanvasProjectV2 project = service.loadV2();
        assertEquals(2, project.schemaVersion());
        assertEquals(1, project.version());
    }

    @Test
    void saveWithoutBaseVersion_throwsIllegalArgument(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        ObjectNode body = om.createObjectNode();
        body.put("schema_version", 2);
        body.set("nodes", om.createArrayNode());
        body.set("edges", om.createArrayNode());
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.saveV2(body, "editor"));
        assertTrue(ex.getMessage().contains("缺少 base_version"),
                "异常消息应含 '缺少 base_version'，实际: " + ex.getMessage());
    }

    @Test
    void saveWithoutSchemaMarker_throwsIllegalArgument(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        ObjectNode body = om.createObjectNode();
        body.set("nodes", om.createArrayNode());
        body.set("edges", om.createArrayNode());
        body.put("base_version", 1);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.saveV2(body, "editor"));
        assertTrue(ex.getMessage().contains("缺少 schema_version 或 version"),
                "异常消息应含 '缺少 schema_version 或 version'，实际: " + ex.getMessage());
    }

    @Test
    void saveWithNodesNotArray_throwsIllegalArgument(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        ObjectNode body = om.createObjectNode();
        body.put("schema_version", 2);
        body.put("nodes", "not-an-array");
        body.set("edges", om.createArrayNode());
        body.put("base_version", 1);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.saveV2(body, "editor"));
        assertTrue(ex.getMessage().contains("画布项目格式不对"),
                "异常消息应含 '画布项目格式不对'，实际: " + ex.getMessage());
    }

    @Test
    void saveWithVersion2WithoutSchemaMarker_throwsIllegalArgument(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        ObjectNode body = om.createObjectNode();
        body.put("version", 2);
        body.set("nodes", om.createArrayNode());
        body.set("edges", om.createArrayNode());
        body.put("base_version", 1);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.saveV2(body, "editor"));
        assertTrue(ex.getMessage().contains("旧版 version 必须为 1"),
                "异常消息应含 '旧版 version 必须为 1'，实际: " + ex.getMessage());
    }

    @Test
    void saveSuccess_versionIncremented_persistedAsV2(@TempDir Path dir) throws Exception {
        CanvasProjectService service = newService(dir);
        CanvasProjectV2 saved = service.saveV2(v2Body(1), "editor");
        assertEquals(2, saved.version());
        assertEquals(2, saved.schemaVersion());
        assertEquals("editor", saved.updatedBy());

        String onDisk = Files.readString(dir.resolve("project.json"));
        assertTrue(onDisk.contains("\"schema_version\""), "落盘 JSON 应含 schema_version");
        assertTrue(onDisk.contains("\"schema_version\":2") || onDisk.contains("\"schema_version\" : 2"),
                "落盘 JSON schema_version 应为 2");
        assertFalse(onDisk.contains("\"base_version\""), "落盘 JSON 不应包含 base_version");
    }

    @Test
    void loadLegacyFile_normalizesInMemory_fileUnchanged(@TempDir Path dir) throws Exception {
        ObjectNode legacy = om.createObjectNode();
        legacy.put("version", 1);
        legacy.put("revision", 6);
        legacy.put("updated_by", "editor");
        legacy.set("nodes", om.createArrayNode());
        legacy.set("edges", om.createArrayNode());
        Path file = dir.resolve("project.json");
        String original = om.writeValueAsString(legacy);
        Files.writeString(file, original);

        CanvasProjectService service = newService(dir);
        CanvasProjectV2 loaded = service.loadV2();
        assertEquals(2, loaded.schemaVersion());
        assertEquals(6, loaded.version());
        assertEquals("editor", loaded.updatedBy());

        String after = Files.readString(file);
        assertEquals(original, after, "loadV2 不应改写磁盘文件");
    }

    @Test
    void mcpTools_stillThree(@TempDir Path dir) {
        CanvasProjectService service = newService(dir);
        List<Map<String, String>> tools = service.mcpTools();
        assertNotNull(tools);
        assertEquals(3, tools.size(), "mcpTools 应仍返回 3 个");
    }
}
