package com.dramafactory.service;

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

@Service
public class CanvasProjectService {

    private final String canvasDir;
    private final ObjectMapper objectMapper;

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
            return objectMapper.readTree(bytes);
        } catch (IOException e) {
            throw new IllegalArgumentException("画布项目文件损坏，请检查 data/canvas/project.json");
        }
    }

    public JsonNode save(JsonNode project) {
        if (project == null || !project.isObject()) {
            throw new IllegalArgumentException("画布项目格式不对：需要 version/nodes/edges");
        }
        JsonNode versionNode = project.get("version");
        if (versionNode == null || !versionNode.isInt() || versionNode.asInt() != 1) {
            throw new IllegalArgumentException("画布项目格式不对：需要 version/nodes/edges");
        }
        JsonNode nodesNode = project.get("nodes");
        JsonNode edgesNode = project.get("edges");
        if (nodesNode == null || !nodesNode.isArray() || edgesNode == null || !edgesNode.isArray()) {
            throw new IllegalArgumentException("画布项目格式不对：需要 version/nodes/edges");
        }

        Path dir = Paths.get(canvasDir);
        Path target = dir.resolve("project.json");
        Path tmp = dir.resolve("project.json.tmp");
        try {
            Files.createDirectories(dir);
            byte[] payload = objectMapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(project);
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
        return project;
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
        saveTool.put("description", "把整份画布项目 JSON 覆盖保存到磁盘，要求 version 为 1，nodes 和 edges 都是数组。");
        saveTool.put("inputSchema", "{\"type\":\"object\",\"properties\":{\"project\":{\"type\":\"object\",\"properties\":{\"version\":{\"type\":\"integer\",\"const\":1},\"nodes\":{\"type\":\"array\"},\"edges\":{\"type\":\"array\"}},\"required\":[\"version\",\"nodes\",\"edges\"]}},\"required\":[\"project\"],\"additionalProperties\":false}");
        tools.add(saveTool);

        return tools;
    }

    private JsonNode emptyProject() {
        ObjectNode root = objectMapper.createObjectNode();
        root.put("version", 1);
        ArrayNode nodes = objectMapper.createArrayNode();
        ArrayNode edges = objectMapper.createArrayNode();
        root.set("nodes", nodes);
        root.set("edges", edges);
        return root;
    }
}
