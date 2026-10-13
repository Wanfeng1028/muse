package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.PipelineService;
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
    public Records.PipelineProjectView getProjectPipeline(@PathVariable Long projectId) {
        return pipelineService.getProjectPipeline(projectId);
    }

    /**
     * 获取全部项目的流水线看板列表。
     *
     * @return 所有项目的流水线视图列表
     */
    @GetMapping("/pipelines")
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
    public Records.ProductionStatsResponse getProductionStats(@PathVariable Long projectId) {
        return pipelineService.getProductionStats(projectId);
    }
}
