package com.dramafactory.dto.canvas;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

public record CanvasProposalV2(
        String id,
        @JsonProperty("base_version") int baseVersion,
        List<CanvasPatchRequest.CanvasPatchOp> ops,
        String status,
        @JsonProperty("created_at") String createdAt,
        @JsonProperty("created_by") String createdBy,
        String message
) {
}
