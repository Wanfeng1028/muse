package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.ReviewService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 审核队列 REST 控制器。
 *
 * <p>按项目查询待办审核列表；projectId 只做透传，归属过滤在 {@link ReviewService#queue} 里按当前用户做。</p>
 */
@RestController
@RequestMapping("/api/projects/{projectId}/review")
@Tag(name = "Review", description = "剧本与分镜审核流")
public class ReviewQueueController {

    private static final Logger log = LoggerFactory.getLogger(ReviewQueueController.class);

    private final ReviewService reviewService;

    /**
     * 构造器注入。
     *
     * @param reviewService 审核流核心服务
     */
    public ReviewQueueController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    /**
     * 查询审核队列。
     *
     * @param projectId 项目 ID
     * @param kind      审核类型，SCRIPT 或 BOARD，可为空表示不限
     * @param status    审核状态，可为空表示不限
     * @return 队列条目列表
     */
    @GetMapping("/queue")
    @Operation(summary = "查询审核队列")
    public List<Records.ReviewQueueItem> queue(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                               @Parameter(description = "审核类型：SCRIPT 或 BOARD，可为空") @RequestParam(name = "kind", required = false) String kind,
                                               @Parameter(description = "审核状态，可为空") @RequestParam(name = "status", required = false) String status) {
        log.info("查询审核队列：projectId={}, kind={}, status={}", projectId, kind, status);
        return reviewService.queue(projectId, kind, status);
    }
}
