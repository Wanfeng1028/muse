package com.dramafactory.dto.canvas;

import com.fasterxml.jackson.annotation.JsonProperty;

public record CanvasJobV2(
        @JsonProperty("job_id") String jobId,
        @JsonProperty("node_id") String nodeId,
        String status,
        int version,
        @JsonProperty("created_at") String createdAt,
        @JsonProperty("updated_at") String updatedAt
) {
}
