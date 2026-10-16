package com.dramafactory.dto.canvas;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

public record CanvasPatchRequest(
        @JsonProperty("base_version") Integer baseVersion,
        List<CanvasPatchOp> ops
) {
    public record CanvasPatchOp(
            String op,
            @JsonProperty("node_id") String nodeId,
            Map<String, Object> fields
    ) {
    }
}
