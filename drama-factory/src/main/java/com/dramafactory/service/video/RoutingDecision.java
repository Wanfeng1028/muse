package com.dramafactory.service.video;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 一次视频通道路由决策的不可变记录。
 *
 * @param shotId          分镜 ID，允许为 null
 * @param rankedCandidates 按加权分从高到低排序的通道名
 * @param scores          通道名 → 加权分
 * @param selected        最终选中的通道名
 * @param reason          决策原因说明
 * @param decidedAt       决策时间
 */
public record RoutingDecision(Long shotId,
                              List<String> rankedCandidates,
                              Map<String, Double> scores,
                              String selected,
                              String reason,
                              LocalDateTime decidedAt) {

    public RoutingDecision {
        rankedCandidates = rankedCandidates == null ? List.of() : List.copyOf(rankedCandidates);
        scores = scores == null ? Map.of() : Map.copyOf(scores);
    }
}
