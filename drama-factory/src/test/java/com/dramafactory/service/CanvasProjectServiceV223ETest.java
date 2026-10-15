package com.dramafactory.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 诚实跳过清单：
 * 1. save() 中 catch (IOException atomicFailed) 的 ATOMIC_MOVE 失败回退分支 ——
 *    是否支持原子移动取决于底层文件系统实现，普通测试环境无法确定性触发该 IOException，
 *    不做硬凑测试。
 */
class CanvasProjectServiceV223ETest {

    private final ObjectMapper om = new ObjectMapper();

    private CanvasProjectService newService(Path dir) {
        return new CanvasProjectService(dir.toString(), om);
    }

    private ObjectNode validProject() {
        ObjectNode p = om.createObjectNode();
        p.put("version", 1);
        p.set("nodes", om.createArrayNode());
        p.set("edges", om.createArrayNode());
        return p;
    }

    // ① L34 臂：Files.exists 为 false -> emptyProject()
    @Test
    void loadWhenFileMissingReturnsEmptyProject(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        JsonNode result = service.load();
        assertEquals(1, result.get("version").asInt());
        assertTrue(result.get("nodes").isArray());
        assertTrue(result.get("edges").isArray());
        assertEquals(0, result.get("nodes").size());
        assertEquals(0, result.get("edges").size());
    }

    // ② L34 臂：Files.exists 为 true -> readTree
    @Test
    void loadAfterSaveRoundTrips(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        ObjectNode project = validProject();
        project.withArray("nodes").addObject().put("id", "n1");
        service.save(project);
        JsonNode loaded = service.load();
        assertEquals(1, loaded.get("version").asInt());
        assertEquals(1, loaded.get("nodes").size());
        assertEquals("n1", loaded.get("nodes").get(0).get("id").asText());
        assertTrue(loaded.get("edges").isArray());
    }

    // ③ L46 臂：project == null
    @Test
    void saveNullThrows(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.save(null));
        assertTrue(ex.getMessage().contains("画布项目格式不对"));
    }

    // ④ L46 臂：project 非 object
    @Test
    void saveNonObjectThrows(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        ArrayNode array = om.createArrayNode();
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.save(array));
        assertTrue(ex.getMessage().contains("画布项目格式不对"));
    }

    // ⑤ L50 臂：缺 version 字段
    @Test
    void saveMissingVersionThrows(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        ObjectNode p = om.createObjectNode();
        p.set("nodes", om.createArrayNode());
        p.set("edges", om.createArrayNode());
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.save(p));
        assertTrue(ex.getMessage().contains("画布项目格式不对"));
    }

    // ⑥ L50 臂：version 为文本 "1"（isInt false）
    @Test
    void saveTextVersionThrows(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        ObjectNode p = validProject();
        p.put("version", "1");
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.save(p));
        assertTrue(ex.getMessage().contains("画布项目格式不对"));
    }

    // ⑦ L50 臂：version 为 2（asInt != 1）
    @Test
    void saveWrongVersionThrows(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        ObjectNode p = validProject();
        p.put("version", 2);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.save(p));
        assertTrue(ex.getMessage().contains("画布项目格式不对"));
    }

    // ⑧ L55 臂：version=1 但缺 nodes
    @Test
    void saveMissingNodesThrows(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        ObjectNode p = om.createObjectNode();
        p.put("version", 1);
        p.set("edges", om.createArrayNode());
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.save(p));
        assertTrue(ex.getMessage().contains("画布项目格式不对"));
    }

    // ⑨ L55 臂：nodes 为文本（非数组）
    @Test
    void saveTextNodesThrows(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        ObjectNode p = validProject();
        p.put("nodes", "not-an-array");
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.save(p));
        assertTrue(ex.getMessage().contains("画布项目格式不对"));
    }

    // ⑩ L55 臂：nodes=[] 但缺 edges
    @Test
    void saveMissingEdgesThrows(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        ObjectNode p = om.createObjectNode();
        p.put("version", 1);
        p.set("nodes", om.createArrayNode());
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.save(p));
        assertTrue(ex.getMessage().contains("画布项目格式不对"));
    }

    // ⑪ L55 臂：edges 为数字（非数组）
    @Test
    void saveNumericEdgesThrows(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        ObjectNode p = validProject();
        p.put("edges", 5);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.save(p));
        assertTrue(ex.getMessage().contains("画布项目格式不对"));
    }

    // ⑫ save 成功路径：返回原对象，磁盘落盘
    @Test
    void saveWritesProjectToDisk(@TempDir Path tempDir) throws Exception {
        CanvasProjectService service = newService(tempDir);
        ObjectNode project = validProject();
        project.withArray("nodes").addObject().put("id", "n1");
        JsonNode returned = service.save(project);
        assertSame(project, returned);
        Path target = Paths.get(tempDir.toString(), "project.json");
        assertTrue(Files.exists(target));
        assertFalse(Files.exists(Paths.get(tempDir.toString(), "project.json.tmp")));
        JsonNode fromDisk = om.readTree(Files.readAllBytes(target));
        assertEquals(1, fromDisk.get("version").asInt());
        assertEquals("n1", fromDisk.get("nodes").get(0).get("id").asText());
    }

    // ⑬ mcpTools() 返回两个工具
    @Test
    void mcpToolsReturnsTwoTools(@TempDir Path tempDir) {
        CanvasProjectService service = newService(tempDir);
        assertEquals(2, service.mcpTools().size());
        assertEquals("canvas.get_project", service.mcpTools().get(0).get("name"));
        assertEquals("canvas.save_project", service.mcpTools().get(1).get("name"));
    }

    // 额外：load() 损坏文件分支
    @Test
    void loadCorruptedFileThrows(@TempDir Path tempDir) throws Exception {
        Path target = Paths.get(tempDir.toString(), "project.json");
        Files.write(target, "{broken".getBytes());
        CanvasProjectService service = newService(tempDir);
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.load());
        assertTrue(ex.getMessage().contains("损坏"));
    }
}
