package com.dramafactory.service;

import com.dramafactory.exception.CanvasConflictException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

// 存储切换触发条件（写死）：后端离开 localhost，或出现第二个写入者（第二个浏览器 tab / 第二个 agent / 第二个用户）——任一发生，先把文件存储换掉（换 SQLite/远端）再继续加功能。POC 阶段单文件 + synchronized 足够。
@Service
public class CanvasProjectService {

    private final String canvasDir;
    private final ObjectMapper objectMapper;
    private final Object writeLock = new Object();

    public CanvasProjectService(@Value("${drama.canvas:./data/canvas}") String canvasDir,
                                ObjectMapper objectMapper) {
        this.canvasDir = canvasDir;
        this.objectMapper = objectMapper;
    }

    public JsonNode load() {
        Path projectFile = Paths.get(canvasDir, "project.json");
        if (!Files.exists(projectFile)) {
            return emptyProject();
        }
        try {
            byte[] bytes = Files.readAllBytes(projectFile);
            JsonNode root = objectMapper.readTree(bytes);
            if (root != null && root.isObject()) {
                ObjectNode objectRoot = (ObjectNode) root;
                if (!objectRoot.has("revision")) {
                    objectRoot.put("revision", 1);
                }
                if (!objectRoot.has("updated_by")) {
                    objectRoot.put("updated_by", "editor");
                }
            }
            return root;
        } catch (IOException e) {
            throw new IllegalArgumentException("画布项目文件损坏，请检查 data/canvas/project.json");
        }
    }

    public JsonNode save(JsonNode project) {
        return save(project, "editor");
    }

    public JsonNode save(JsonNode body, String updatedBy) {
        if (body == null || !body.isObject()) {
            throw new IllegalArgumentException("画布项目格式不对：需要 version/nodes/edges");
        }
        JsonNode baseVersionNode = body.get("base_version");
        if (baseVersionNode == null || !baseVersionNode.isInt()) {
            throw new IllegalArgumentException("缺少 base_version：保存前请先 GET /api/canvas/project 读取最新 revision");
        }
        int baseVersion = baseVersionNode.asInt();

        JsonNode versionNode = body.get("version");
        if (versionNode == null || !versionNode.isInt() || versionNode.asInt() != 1) {
            throw new IllegalArgumentException("画布项目格式不对：需要 version/nodes/edges");
        }
        JsonNode nodesNode = body.get("nodes");
        JsonNode edgesNode = body.get("edges");
        if (nodesNode == null || !nodesNode.isArray() || edgesNode == null || !edgesNode.isArray()) {
            throw new IllegalArgumentException("画布项目格式不对：需要 version/nodes/edges");
        }

        synchronized (writeLock) {
            JsonNode current = load();
            int currentRevision = 1;
            if (current != null && current.has("revision") && current.get("revision").isInt()) {
                currentRevision = current.get("revision").asInt();
            }
            String currentUpdatedBy = "editor";
            if (current != null && current.has("updated_by") && current.get("updated_by").isTextual()) {
                currentUpdatedBy = current.get("updated_by").asText();
            }

            if (baseVersion != currentRevision) {
                throw new CanvasConflictException(currentRevision, currentUpdatedBy);
            }

            ObjectNode persisted = objectMapper.createObjectNode();
            persisted.put("version", 1);
            persisted.put("revision", currentRevision + 1);
            persisted.put("updated_by", updatedBy);
            persisted.set("nodes", nodesNode);
            persisted.set("edges", edgesNode);

            Path dir = Paths.get(canvasDir);
            Path target = dir.resolve("project.json");
            Path tmp = dir.resolve("project.json.tmp");
            try {
                Files.createDirectories(dir);
                byte[] payload = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(persisted);
                Files.write(tmp, payload);
                try {
                    Files.move(tmp, target,
                            StandardCopyOption.REPLACE_EXISTING,
                            StandardCopyOption.ATOMIC_MOVE);
                } catch (IOException atomicFailed) {
                    // 有些文件系统不支持原子移动，退回到普通替换，保证写入不半截
                    Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING);
                }
            } catch (IOException e) {
                throw new RuntimeException("画布项目写入失败：" + e.getMessage(), e);
            }
            return persisted;
        }
    }

    public List<Map<String, String>> mcpTools() {
        List<Map<String, String>> tools = new ArrayList<>();

        Map<String, String> getTool = new LinkedHashMap<>();
        getTool.put("name", "canvas.get_project");
        getTool.put("description", "读取当前编排画布的项目 JSON，返回版本号、节点列表和连线列表。");
        getTool.put("inputSchema", "{\"type\":\"object\",\"properties\":{},\"additionalProperties\":false}");
        tools.add(getTool);

        Map<String, String> saveTool = new LinkedHashMap<>();
        saveTool.put("name", "canvas.save_project");
        saveTool.put("description", "把整份画布项目 JSON 覆盖保存到磁盘，要求 version 为 1，nodes 和 edges 都是数组；请求体必须带 base_version（GET 到的 revision），版本过期返回 409。");
        saveTool.put("inputSchema", "{\"type\":\"object\",\"properties\":{\"project\":{\"type\":\"object\",\"properties\":{\"version\":{\"type\":\"integer\",\"const\":1},\"nodes\":{\"type\":\"array\"},\"edges\":{\"type\":\"array\"}},\"required\":[\"version\",\"nodes\",\"edges\"]}},\"required\":[\"project\"],\"additionalProperties\":false}");
        tools.add(saveTool);

        Map<String, String> applyPatchTool = new LinkedHashMap<>();
        applyPatchTool.put("name", "canvas.apply_patch");
        applyPatchTool.put("description", "对画布项目做增量修改（RFC 6902 JSON Patch），请求体必须带 base_version，版本过期返回 409。POC 阶段仅定接口，真实执行随网关 POC 落地。");
        applyPatchTool.put("inputSchema", "{\"type\":\"object\",\"properties\":{\"base_version\":{\"type\":\"integer\",\"description\":\"GET 项目时拿到的 revision\"},\"patch\":{\"type\":\"array\",\"description\":\"RFC 6902 JSON Patch 操作数组\"}},\"required\":[\"base_version\",\"patch\"],\"additionalProperties\":false}");
        tools.add(applyPatchTool);

        return tools;
    }

    private JsonNode emptyProject() {
        ObjectNode root = objectMapper.createObjectNode();
        root.put("version", 1);
        root.put("revision", 1);
        root.put("updated_by", "editor");
        ArrayNode nodes = objectMapper.createArrayNode();
        ArrayNode edges = objectMapper.createArrayNode();
        root.set("nodes", nodes);
        root.set("edges", edges);
        return root;
    }
}
