package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.PipelineService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 制作流水线看板控制器。
 * 提供单个项目的流水线视图以及全部项目的看板列表。
 */
@RestController
@RequestMapping("/api")
@Tag(name = "Pipeline", description = "制作流水线看板与生产统计接口")
public class PipelineController {

    private final PipelineService pipelineService;

    /**
     * 构造器注入 PipelineService。
     *
     * @param pipelineService 流水线服务
     */
    public PipelineController(PipelineService pipelineService) {
        this.pipelineService = pipelineService;
    }

    /**
     * 获取指定项目的流水线视图。
     *
     * @param projectId 项目 ID
     * @return 该项目的流水线视图
     */
    @GetMapping("/projects/{projectId}/pipeline")
    @Operation(summary = "查询项目流水线视图")
    public Records.PipelineProjectView getProjectPipeline(@Parameter(description = "项目 ID") @PathVariable Long projectId) {

        return pipelineService.getProjectPipeline(projectId);
    }

    /**
     * 获取全部项目的流水线看板列表。
     *
     * @return 所有项目的流水线视图列表
     */
    @GetMapping("/pipelines")
    @Operation(summary = "查询全部项目流水线看板")
    public List<Records.PipelineProjectView> getAllPipelines() {
        return pipelineService.listAllPipelines();
    }

    /**
     * 获取指定项目的生产统计：分镜完成率、任务成功率、累计渲染时长。
     *
     * @param projectId 项目 ID
     * @return 生产统计视图
     */
    @GetMapping("/projects/{projectId}/stats")
    @Operation(summary = "查询项目生产统计")
    public Records.ProductionStatsResponse getProductionStats(@Parameter(description = "项目 ID") @PathVariable Long projectId) {

        return pipelineService.getProductionStats(projectId);
    }
}
