package com.dramafactory.dto.canvas;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

public record CanvasProjectV2(
        @JsonProperty("schema_version") int schemaVersion,
        int version,
        @JsonProperty("updated_by") String updatedBy,
        @JsonProperty("updated_at") String updatedAt,
        List<CanvasNodeV2> nodes,
        List<CanvasEdgeV2> edges
) {
}
