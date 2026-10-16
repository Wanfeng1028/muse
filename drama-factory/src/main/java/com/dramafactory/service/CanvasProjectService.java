package com.dramafactory.service;

import com.dramafactory.dto.canvas.CanvasEdgeV2;
import com.dramafactory.dto.canvas.CanvasNodeV2;
import com.dramafactory.dto.canvas.CanvasPatchRequest;
import com.dramafactory.dto.canvas.CanvasProposalV2;
import com.dramafactory.dto.canvas.CanvasProjectV2;
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
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;

// 存储切换触发条件（写死）：后端离开 localhost，或出现第二个写入者（第二个浏览器 tab / 第二个 agent / 第二个用户）——任一发生，先把文件存储换掉（换 SQLite/远端）再继续加功能。POC 阶段单文件 + synchronized 足够。
@Service
public class CanvasProjectService {

    private final String canvasDir;
    private final ObjectMapper objectMapper;
    private final CanvasEventService canvasEventService;
    private final CanvasMigrationAdapter canvasMigrationAdapter;
    private final Object writeLock = new Object();
    private final CopyOnWriteArrayList<CanvasProposalV2> proposals = new CopyOnWriteArrayList<>();

    public CanvasProjectService(@Value("${drama.canvas:./data/canvas}") String canvasDir,
                                ObjectMapper objectMapper,
                                CanvasEventService canvasEventService,
                                CanvasMigrationAdapter canvasMigrationAdapter) {
        this.canvasDir = canvasDir;
        this.objectMapper = objectMapper;
        this.canvasEventService = canvasEventService;
        this.canvasMigrationAdapter = canvasMigrationAdapter;
    }

    public CanvasProjectV2 loadV2() {
        Path projectFile = Paths.get(canvasDir, "project.json");
        if (!Files.exists(projectFile)) {
            return emptyV2();
        }
        try {
            byte[] bytes = Files.readAllBytes(projectFile);
            JsonNode root = objectMapper.readTree(bytes);
            if (root == null || !root.isObject()) {
                throw new IllegalArgumentException("画布项目文件损坏，请检查 data/canvas/project.json");
            }
            if (root.has("schema_version") && root.get("schema_version").asInt() == 2) {
                return objectMapper.treeToValue(root, CanvasProjectV2.class);
            }
            return canvasMigrationAdapter.migrate(root);
        } catch (IOException e) {
            throw new IllegalArgumentException("画布项目文件损坏，请检查 data/canvas/project.json");
        }
    }

    public int currentVersion() {
        return loadV2().version();
    }

    public CanvasProjectV2 saveV2(JsonNode body, String updatedBy) {
        if (body == null || !body.isObject()) {
            throw new IllegalArgumentException("画布项目格式不对：需要 base_version/nodes/edges");
        }
        JsonNode baseVersionNode = body.get("base_version");
        if (baseVersionNode == null || !baseVersionNode.isInt()) {
            throw new IllegalArgumentException("缺少 base_version：保存前请先 GET /api/canvas/project 读取最新 version");
        }
        int baseVersion = baseVersionNode.asInt();

        boolean hasSchemaVersion = body.has("schema_version");
        boolean hasVersion = body.has("version");
        if (hasSchemaVersion) {
            if (body.get("schema_version").asInt() != 2) {
                throw new IllegalArgumentException("schema_version 必须为 2");
            }
        } else if (hasVersion) {
            if (body.get("version").asInt() != 1) {
                throw new IllegalArgumentException("旧版 version 必须为 1");
            }
        } else {
            throw new IllegalArgumentException("缺少 schema_version 或 version 标记");
        }

        JsonNode nodesNode = body.get("nodes");
        JsonNode edgesNode = body.get("edges");
        if (nodesNode == null || !nodesNode.isArray() || edgesNode == null || !edgesNode.isArray()) {
            throw new IllegalArgumentException("画布项目格式不对：需要 base_version/nodes/edges");
        }

        synchronized (writeLock) {
            CanvasProjectV2 current = loadV2();
            if (baseVersion != current.version()) {
                throw new CanvasConflictException(current.version(), current.updatedBy());
            }

            String now = OffsetDateTime.now().toString();
            List<CanvasNodeV2> nodes = new ArrayList<>();
            for (JsonNode n : nodesNode) {
                String kind = textOrDefault(n, "kind", "script");
                if (!isValidKind(kind)) {
                    throw new IllegalArgumentException("非法 kind：" + kind);
                }
                String status = textOrDefault(n, "status", "idle");
                if (!isValidStatus(status)) {
                    throw new IllegalArgumentException("非法 status：" + status);
                }
                List<String> assetRefs = new ArrayList<>();
                if (n.has("asset_refs") && n.get("asset_refs").isArray()) {
                    for (JsonNode a : n.get("asset_refs")) {
                        assetRefs.add(a.asText());
                    }
                }
                Map<String, Object> params = new LinkedHashMap<>();
                if (n.has("params") && n.get("params").isObject()) {
                    params = objectMapper.convertValue(n.get("params"), new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {
                    });
                }
                nodes.add(new CanvasNodeV2(
                        textOrNull(n, "id"),
                        kind,
                        textOrDefault(n, "label", ""),
                        n.has("x") && n.get("x").isNumber() ? n.get("x").asDouble() : 0d,
                        n.has("y") && n.get("y").isNumber() ? n.get("y").asDouble() : 0d,
                        textOrNull(n, "shot_ref"),
                        params,
                        status,
                        assetRefs,
                        now,
                        updatedBy
                ));
            }

            List<CanvasEdgeV2> edges = new ArrayList<>();
            for (JsonNode e : edgesNode) {
                String type = textOrDefault(e, "type", "depends");
                if (!"depends".equals(type) && !"ref".equals(type)) {
                    throw new IllegalArgumentException("非法 edge.type：" + type);
                }
                edges.add(new CanvasEdgeV2(
                        textOrNull(e, "id"),
                        textOrNull(e, "source"),
                        textOrNull(e, "target"),
                        type
                ));
            }
            if (hasCycle(edges)) {
                throw new IllegalArgumentException("depends 边成环");
            }

            CanvasProjectV2 next = new CanvasProjectV2(2, current.version() + 1, updatedBy, now, nodes, edges);
            persist(next);

            Map<String, Object> changed = new LinkedHashMap<>();
            changed.put("version", next.version());
            changed.put("updated_by", updatedBy);
            changed.put("kind", "save");
            canvasEventService.broadcast("canvas.changed", changed);
            return next;
        }
    }

    public CanvasProjectV2 applyPatch(CanvasPatchRequest req, String ifMatchHeader, String updatedBy) {
        if (req == null || req.ops() == null) {
            throw new IllegalArgumentException("请求体需要 base_version 和 ops");
        }
        Integer baseVersion = req.baseVersion();
        if (ifMatchHeader != null && !ifMatchHeader.isBlank()) {
            baseVersion = parseIfMatch(ifMatchHeader);
        }
        if (baseVersion == null) {
            throw new IllegalArgumentException("缺少 base_version（或 If-Match 头）");
        }

        for (CanvasPatchRequest.CanvasPatchOp op : req.ops()) {
            if (!"update_node".equals(op.op())) {
                throw new IllegalArgumentException("非法 op：" + op.op());
            }
            Map<String, Object> fields = op.fields();
            if (fields == null) {
                throw new IllegalArgumentException("update_node 缺少 fields");
            }
            for (String key : fields.keySet()) {
                if (!"status".equals(key) && !"asset_refs".equals(key)) {
                    throw new IllegalArgumentException("非法字段：" + key);
                }
            }
            if (fields.containsKey("status")) {
                Object status = fields.get("status");
                if (!(status instanceof String) || !isValidStatus((String) status)) {
                    throw new IllegalArgumentException("非法 status：" + status);
                }
            }
            if (fields.containsKey("asset_refs")) {
                Object assetRefs = fields.get("asset_refs");
                if (!(assetRefs instanceof List)) {
                    throw new IllegalArgumentException("asset_refs 必须是数组");
                }
            }
        }

        synchronized (writeLock) {
            CanvasProjectV2 current = loadV2();
            if (baseVersion != current.version()) {
                throw new CanvasConflictException(current.version(), current.updatedBy());
            }

            String now = OffsetDateTime.now().toString();
            Map<String, CanvasNodeV2> byId = new HashMap<>();
            for (CanvasNodeV2 n : current.nodes()) {
                byId.put(n.id(), n);
            }

            for (CanvasPatchRequest.CanvasPatchOp op : req.ops()) {
                String nodeId = op.nodeId();
                if (!byId.containsKey(nodeId)) {
                    throw new com.dramafactory.exception.ResourceNotFoundException("node", 0L);
                }
                CanvasNodeV2 n = byId.get(nodeId);
                String status = n.status();
                List<String> assetRefs = n.assetRefs();
                Map<String, Object> fields = op.fields();
                if (fields.containsKey("status")) {
                    status = (String) fields.get("status");
                }
                if (fields.containsKey("asset_refs")) {
                    assetRefs = new ArrayList<>();
                    for (Object a : (List<?>) fields.get("asset_refs")) {
                        assetRefs.add(String.valueOf(a));
                    }
                }
                byId.put(nodeId, new CanvasNodeV2(
                        n.id(), n.kind(), n.label(), n.x(), n.y(), n.shotRef(), n.params(),
                        status, assetRefs, now, updatedBy
                ));
            }

            List<CanvasNodeV2> newNodes = new ArrayList<>();
            for (CanvasNodeV2 n : current.nodes()) {
                newNodes.add(byId.get(n.id()));
            }

            CanvasProjectV2 next = new CanvasProjectV2(2, current.version() + 1, updatedBy, now, newNodes, current.edges());
            persist(next);

            Map<String, Object> changed = new LinkedHashMap<>();
            changed.put("version", next.version());
            changed.put("updated_by", updatedBy);
            changed.put("kind", "patch");
            canvasEventService.broadcast("canvas.changed", changed);
            return next;
        }
    }

    public int markNodeDone(String nodeId, String updatedBy) {
        synchronized (writeLock) {
            CanvasProjectV2 current = loadV2();
            String now = OffsetDateTime.now().toString();
            boolean found = false;
            List<CanvasNodeV2> newNodes = new ArrayList<>();
            for (CanvasNodeV2 n : current.nodes()) {
                if (n.id().equals(nodeId)) {
                    found = true;
                    newNodes.add(new CanvasNodeV2(
                            n.id(), n.kind(), n.label(), n.x(), n.y(), n.shotRef(), n.params(),
                            "done", n.assetRefs(), now, updatedBy
                    ));
                } else {
                    newNodes.add(n);
                }
            }
            if (!found) {
                return current.version();
            }
            CanvasProjectV2 next = new CanvasProjectV2(2, current.version() + 1, updatedBy, now, newNodes, current.edges());
            persist(next);
            return next.version();
        }
    }

    public CanvasProposalV2 createProposal(JsonNode body) {
        int baseVersion = 1;
        if (body != null && body.has("base_version") && body.get("base_version").isInt()) {
            baseVersion = body.get("base_version").asInt();
        }
        List<CanvasPatchRequest.CanvasPatchOp> ops = new ArrayList<>();
        if (body != null && body.has("ops") && body.get("ops").isArray()) {
            for (JsonNode op : body.get("ops")) {
                String opName = textOrDefault(op, "op", null);
                String nodeId = textOrNull(op, "node_id");
                Map<String, Object> fields = new LinkedHashMap<>();
                if (op.has("fields") && op.get("fields").isObject()) {
                    fields = objectMapper.convertValue(op.get("fields"), new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {
                    });
                }
                ops.add(new CanvasPatchRequest.CanvasPatchOp(opName, nodeId, fields));
            }
        }
        String id = "p-" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        String now = OffsetDateTime.now().toString();
        CanvasProposalV2 proposal = new CanvasProposalV2(
                id,
                baseVersion,
                ops,
                "pending",
                now,
                "agent",
                "切片 1 仅预留：proposal 审批流（approve/reject/409 回显）随切片 2 落地"
        );
        proposals.add(proposal);
        return proposal;
    }

    public List<CanvasProposalV2> listProposals() {
        return new ArrayList<>(proposals);
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
        saveTool.put("description", "把整份画布项目 JSON 覆盖保存到磁盘，请求体必须带 base_version（GET 到的 version），版本过期返回 409。");
        saveTool.put("inputSchema", "{\"type\":\"object\",\"properties\":{\"project\":{\"type\":\"object\",\"properties\":{\"schema_version\":{\"type\":\"integer\",\"const\":2},\"nodes\":{\"type\":\"array\"},\"edges\":{\"type\":\"array\"}},\"required\":[\"schema_version\",\"nodes\",\"edges\"]}},\"required\":[\"project\"],\"additionalProperties\":false}");
        tools.add(saveTool);
        Map<String, String> applyPatchTool = new LinkedHashMap<>();
        applyPatchTool.put("name", "canvas.apply_patch");
        applyPatchTool.put("description", "对画布项目做增量修改，请求体必须带 base_version 与 ops，版本过期返回 409。");
        applyPatchTool.put("inputSchema", "{\"type\":\"object\",\"properties\":{\"base_version\":{\"type\":\"integer\",\"description\":\"GET 项目时拿到的 version\"},\"ops\":{\"type\":\"array\",\"description\":\"update_node 操作数组\"}},\"required\":[\"base_version\",\"ops\"],\"additionalProperties\":false}");
        tools.add(applyPatchTool);
        return tools;
    }

    private void persist(CanvasProjectV2 project) {
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
                Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException e) {
            throw new RuntimeException("画布项目写入失败：" + e.getMessage(), e);
        }
    }

    private CanvasProjectV2 emptyV2() {
        String now = OffsetDateTime.now().toString();
        return new CanvasProjectV2(2, 1, "editor", now, new ArrayList<>(), new ArrayList<>());
    }

    private int parseIfMatch(String header) {
        String v = header.trim();
        if (v.startsWith("W/")) {
            v = v.substring(2);
        }
        if (v.startsWith("\"") && v.endsWith("\"") && v.length() >= 2) {
            v = v.substring(1, v.length() - 1);
        }
        try {
            return Integer.parseInt(v);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("非法 If-Match：" + header);
        }
    }

    private boolean hasCycle(List<CanvasEdgeV2> edges) {
        Map<String, List<String>> adj = new HashMap<>();
        Set<String> nodes = new HashSet<>();
        for (CanvasEdgeV2 e : edges) {
            if (!"depends".equals(e.type())) {
                continue;
            }
            if (e.source() == null || e.target() == null) {
                continue;
            }
            nodes.add(e.source());
            nodes.add(e.target());
            adj.computeIfAbsent(e.source(), k -> new ArrayList<>()).add(e.target());
        }
        Map<String, Integer> color = new HashMap<>();
        for (String n : nodes) {
            if (dfs(n, adj, color)) {
                return true;
            }
        }
        return false;
    }

    private boolean dfs(String node, Map<String, List<String>> adj, Map<String, Integer> color) {
        Integer c = color.get(node);
        if (c != null) {
            return c == 1;
        }
        color.put(node, 1);
        List<String> next = adj.get(node);
        if (next != null) {
            for (String t : next) {
                if (dfs(t, adj, color)) {
                    return true;
                }
            }
        }
        color.put(node, 2);
        return false;
    }

    private boolean isValidKind(String kind) {
        return "script".equals(kind) || "storyboard".equals(kind) || "video".equals(kind)
                || "edit".equals(kind) || "qc".equals(kind);
    }

    private boolean isValidStatus(String status) {
        return "idle".equals(status) || "running".equals(status) || "done".equals(status) || "failed".equals(status);
    }

    private String textOrNull(JsonNode node, String field) {
        if (node != null && node.has(field) && node.get(field).isTextual()) {
            return node.get(field).asText();
        }
        return null;
    }

    private String textOrDefault(JsonNode node, String field, String fallback) {
        String v = textOrNull(node, field);
        return v == null ? fallback : v;
    }
}
