package com.dramafactory.service;

import com.dramafactory.dto.canvas.CanvasEdgeV2;
import com.dramafactory.dto.canvas.CanvasNodeV2;
import com.dramafactory.dto.canvas.CanvasProjectV2;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;

@Service
public class CanvasMigrationAdapter {

    private final ObjectMapper objectMapper;

    public CanvasMigrationAdapter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public CanvasProjectV2 migrate(JsonNode oldRoot) {
        int version = 1;
        if (oldRoot != null && oldRoot.has("revision") && oldRoot.get("revision").isInt()) {
            version = oldRoot.get("revision").asInt();
        }
        String updatedBy = "editor";
        if (oldRoot != null && oldRoot.has("updated_by") && oldRoot.get("updated_by").isTextual()) {
            updatedBy = oldRoot.get("updated_by").asText();
        }
        String now = OffsetDateTime.now().toString();

        List<CanvasNodeV2> nodes = new ArrayList<>();
        if (oldRoot != null && oldRoot.has("nodes") && oldRoot.get("nodes").isArray()) {
            for (JsonNode n : oldRoot.get("nodes")) {
                String id = textOrNull(n, "id");
                String kind = textOrDefault(n, "kind", "script");
                String label = textOrDefault(n, "label", "");
                double x = n.has("x") && n.get("x").isNumber() ? n.get("x").asDouble() : 0d;
                double y = n.has("y") && n.get("y").isNumber() ? n.get("y").asDouble() : 0d;
                String status = textOrDefault(n, "status", "idle");
                nodes.add(new CanvasNodeV2(
                        id,
                        kind,
                        label,
                        x,
                        y,
                        null,
                        new LinkedHashMap<>(),
                        status,
                        new ArrayList<>(),
                        now,
                        updatedBy
                ));
            }
        }

        List<CanvasEdgeV2> edges = new ArrayList<>();
        if (oldRoot != null && oldRoot.has("edges") && oldRoot.get("edges").isArray()) {
            for (JsonNode e : oldRoot.get("edges")) {
                String id = textOrNull(e, "id");
                String source = textOrNull(e, "source");
                String target = textOrNull(e, "target");
                String type = textOrNull(e, "type");
                if (type == null || (!"depends".equals(type) && !"ref".equals(type))) {
                    type = "depends";
                }
                edges.add(new CanvasEdgeV2(id, source, target, type));
            }
        }

        return new CanvasProjectV2(2, version, updatedBy, now, nodes, edges);
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
