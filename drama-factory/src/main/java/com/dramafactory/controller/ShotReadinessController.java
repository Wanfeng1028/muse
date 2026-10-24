package com.dramafactory.controller;

import com.dramafactory.service.ShotReadinessService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 分镜准备度控制器
 */
@RestController
@RequestMapping("/api/episodes/{episodeId}")
@Tag(name = "分镜准备度")
public class ShotReadinessController {

    private final ShotReadinessService shotReadinessService;

    public ShotReadinessController(ShotReadinessService shotReadinessService) {
        this.shotReadinessService = shotReadinessService;
    }

    /**
     * 单个分镜视频生成准备度
     */
    @GetMapping("/shots/{shotId}/readiness")
    @Operation(summary = "单个分镜视频生成准备度")
    public ShotReadinessService.ShotReadinessReport getShotReadiness(@PathVariable Long episodeId, @PathVariable Long shotId) {
        return shotReadinessService.getForShot(episodeId, shotId);
    }

    /**
     * 整集分镜视频生成准备度
     */
    @GetMapping("/shots-readiness")
    @Operation(summary = "整集分镜视频生成准备度")
    public List<ShotReadinessService.ShotReadinessReport> getEpisodeReadiness(@PathVariable Long episodeId) {
        return shotReadinessService.assessEpisode(episodeId);
    }
}
