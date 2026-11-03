package com.dramafactory.dto.canvas;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

public record CanvasNodeV2(
        String id,
        String kind,
        String label,
        double x,
        double y,
        @JsonProperty("shot_ref") String shotRef,
        Map<String, Object> params,
        String status,
        @JsonProperty("asset_refs") List<String> assetRefs,
        @JsonProperty("updated_at") String updatedAt,
        @JsonProperty("updated_by") String updatedBy
) {
}
