package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.service.ReviewService;
import com.dramafactory.service.ScriptSplitterService;
import com.dramafactory.service.ShotContinuityChecker;
import com.dramafactory.service.SlideshowRiskScorer;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 剧本与分镜审核流 REST 控制器。
 *
 * <p>负责提交审核、一审/二审通过或驳回、分镜通过或驳回，以及审核详情与历史查询。
 * 本控制器只做 HTTP 适配与 path 归属校验，状态机逻辑在 {@link ReviewService}。</p>
 */
@RestController
@RequestMapping("/api/projects/{projectId}/episodes/{episodeId}/review")
@Tag(name = "Review", description = "剧本与分镜审核流")
public class ReviewController {

    private static final Logger log = LoggerFactory.getLogger(ReviewController.class);

    private final ReviewService reviewService;
    private final EpisodeRepository episodeRepository;
    private final ScriptSplitterService scriptSplitterService;
    private final ShotRepository shotRepository;
    private final SlideshowRiskScorer slideshowRiskScorer;

    /**
     * 构造器注入。
     *
     * @param reviewService       审核流核心服务
     * @param episodeRepository   剧集仓储，仅用于校验 path 归属
     * @param scriptSplitterService 分镜拆分服务（含连续性检查入口）
     * @param shotRepository      分镜仓储
     * @param slideshowRiskScorer 幻灯片风险评分器
     */
    public ReviewController(ReviewService reviewService, EpisodeRepository episodeRepository,
                            ScriptSplitterService scriptSplitterService,
                            ShotRepository shotRepository, SlideshowRiskScorer slideshowRiskScorer) {
        this.reviewService = reviewService;
        this.episodeRepository = episodeRepository;
        this.scriptSplitterService = scriptSplitterService;
        this.shotRepository = shotRepository;
        this.slideshowRiskScorer = slideshowRiskScorer;
    }

    /**
     * 提交审核（SCRIPT 或 BOARD 同一接口）。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @param request   提交请求，含 kind 与 version
     * @return 审核结果
     */
    @PostMapping("/submit")
    @Operation(summary = "提交审核")
    public Records.ReviewResult submit(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                       @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                       @Valid @RequestBody SubmitRequest request) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        log.info("提交审核：episodeId={}, kind={}, actor 由服务层判定", episodeId, request.kind());
        return reviewService.submit(episodeId, request.kind(), request.version());
    }

    /**
     * 一审通过。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @param request   审核动作请求，含 version 与 comment
     * @return 审核结果
     */
    @PostMapping("/script/l1/approve")
    @Operation(summary = "剧本一审通过")
    public Records.ReviewResult l1Approve(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                          @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                          @Valid @RequestBody ReviewActionRequest request) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        log.info("剧本一审通过：episodeId={}, kind=SCRIPT, actor 由服务层判定", episodeId);
        return reviewService.l1Approve(episodeId, request.version(), request.comment());
    }

    /**
     * 一审驳回。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @param request   审核动作请求，含 version 与 comment
     * @return 审核结果
     */
    @PostMapping("/script/l1/reject")
    @Operation(summary = "剧本一审驳回")
    public Records.ReviewResult l1Reject(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                         @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                         @Valid @RequestBody ReviewActionRequest request) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        log.info("剧本一审驳回：episodeId={}, kind=SCRIPT, actor 由服务层判定", episodeId);
        return reviewService.l1Reject(episodeId, request.version(), request.comment());
    }

    /**
     * 二审通过。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @param request   审核动作请求，含 version 与 comment
     * @return 审核结果
     */
    @PostMapping("/script/l2/approve")
    @Operation(summary = "剧本二审通过")
    public Records.ReviewResult l2Approve(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                          @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                          @Valid @RequestBody ReviewActionRequest request) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        log.info("剧本二审通过：episodeId={}, kind=SCRIPT, actor 由服务层判定", episodeId);
        return reviewService.l2Approve(episodeId, request.version(), request.comment());
    }

    /**
     * 二审驳回。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @param request   审核动作请求，含 version 与 comment
     * @return 审核结果
     */
    @PostMapping("/script/l2/reject")
    @Operation(summary = "剧本二审驳回")
    public Records.ReviewResult l2Reject(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                         @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                         @Valid @RequestBody ReviewActionRequest request) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        log.info("剧本二审驳回：episodeId={}, kind=SCRIPT, actor 由服务层判定", episodeId);
        return reviewService.l2Reject(episodeId, request.version(), request.comment());
    }

    /**
     * 分镜通过。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @param request   审核动作请求，含 version 与 comment
     * @return 审核结果
     */
    @PostMapping("/board/approve")
    @Operation(summary = "分镜通过")
    public Records.ReviewResult boardApprove(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                             @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                             @Valid @RequestBody ReviewActionRequest request) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        log.info("分镜通过：episodeId={}, kind=BOARD, actor 由服务层判定", episodeId);
        return reviewService.boardApprove(episodeId, request.version(), request.comment());
    }

    /**
     * 分镜驳回。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @param request   审核动作请求，含 version 与 comment
     * @return 审核结果
     */
    @PostMapping("/board/reject")
    @Operation(summary = "分镜驳回")
    public Records.ReviewResult boardReject(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                            @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                            @Valid @RequestBody ReviewActionRequest request) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        log.info("分镜驳回：episodeId={}, kind=BOARD, actor 由服务层判定", episodeId);
        return reviewService.boardReject(episodeId, request.version(), request.comment());
    }

    /**
     * 查询审核详情。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @param kind      审核类型，SCRIPT 或 BOARD
     * @return 审核详情
     */
    @GetMapping("")
    @Operation(summary = "查询审核详情")
    public Records.ReviewDetailResponse getReview(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                                  @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                                  @Parameter(description = "审核类型：SCRIPT 或 BOARD") @RequestParam("kind") String kind) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        return reviewService.getReview(episodeId, kind);
    }

    /**
     * 查询审核历史（按时间升序，分页）。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @param kind      审核类型，SCRIPT 或 BOARD
     * @param page      页码，从 0 开始，负数返回 400
     * @param size      每页条数，1 到 200 之间，越界返回 400
     * @return 历史记录列表
     */
    @GetMapping("/history")
    @Operation(summary = "查询审核历史")
    public List<Records.ReviewHistoryResponse> getHistory(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                                          @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                                          @Parameter(description = "审核类型：SCRIPT 或 BOARD") @RequestParam("kind") String kind,
                                                          @Parameter(description = "页码，从 0 开始") @RequestParam(name = "page", defaultValue = "0") int page,
                                                          @Parameter(description = "每页条数") @RequestParam(name = "size", defaultValue = "20") int size) {
        if (page < 0) {
            throw new IllegalArgumentException("page 参数非法");
        }
        if (size < 1 || size > 200) {
            throw new IllegalArgumentException("size 参数非法");
        }
        assertEpisodeBelongsToProject(projectId, episodeId);
        return reviewService.getHistory(episodeId, kind, page, size);
    }

    /**
     * 分镜连续性检查报告（只读，不影响审核状态机）。
     * 校验器异常时降级返回空报告，不许抛错影响审核页加载。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     * @return 连续性报告 DTO
     */
    @GetMapping("/continuity")
    @Operation(summary = "分镜连续性检查报告")
    public ContinuityReportDto continuity(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                          @Parameter(description = "剧集主键") @PathVariable Long episodeId) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        ShotContinuityChecker.ContinuityReport report;
        try {
            report = scriptSplitterService.checkContinuity(episodeId);
        } catch (Exception e) {
            log.warn("连续性检查失败，降级返回空报告：episodeId={}", episodeId, e);
            return new ContinuityReportDto(0, false, List.of());
        }
        List<ContinuityIssueDto> issues = new ArrayList<>();
        if (report.issues() != null) {
            for (ShotContinuityChecker.ContinuityIssue i : report.issues()) {
                issues.add(new ContinuityIssueDto(i.shotNo(), i.shotId(), i.rule(),
                        i.severity().name(), i.severity().getLabel(), i.message(), i.suggestion()));
            }
        }
        return new ContinuityReportDto(report.shotsChecked(), report.hasWarnings(), issues);
    }

    /**
     * 校验 path 里的 projectId 与 episode 归属一致；不一致按资源不存在处理。
     * 归属他人的检查交给 ReviewService 的 requireOwner（ForbiddenException，映射为 403）。
     *
     * @param projectId 项目 ID
     * @param episodeId 剧集 ID
     */
    private void assertEpisodeBelongsToProject(Long projectId, Long episodeId) {
        Episode episode = episodeRepository.findById(episodeId)
                .orElseThrow(() -> new ResourceNotFoundException("Episode", episodeId));
        if (episode.getProject() == null || !episode.getProject().getId().equals(projectId)) {
            throw new ResourceNotFoundException("Episode", episodeId);
        }
    }

    /**
     * 提交审核请求。
     *
     * @param kind    审核类型，SCRIPT 或 BOARD
     * @param version 请求方读到的版本号
     */
    public record SubmitRequest(@NotBlank(message = "kind 不能为空") String kind,
                                @NotNull(message = "version 不能为空") Integer version) {
    }

    /**
     * 审核动作请求。
     *
     * @param version 请求方读到的版本号
     * @param comment 审核意见，可为空
     */
    public record ReviewActionRequest(@NotNull(message = "version 不能为空") Integer version,
                                      String comment) {
    }

    /**
     * 连续性问题 DTO。
     *
     * @param shotNo        镜号
     * @param shotId        分镜 ID
     * @param rule          规则名
     * @param severity      严重级别：WARN/INFO
     * @param severityLabel 严重级别中文标签
     * @param message       问题描述
     * @param suggestion    修改建议
     */
    public record ContinuityIssueDto(int shotNo, Long shotId, String rule, String severity,
                                     String severityLabel, String message, String suggestion) {
    }

    /**
     * 连续性报告 DTO。
     *
     * @param shotsChecked 已检查的分镜数
     * @param hasWarnings  是否包含警告级别问题
     * @param issues       问题列表
     */
    public record ContinuityReportDto(int shotsChecked, boolean hasWarnings,
                                       List<ContinuityIssueDto> issues) {
    }

    /**
     * 幻灯片风险评分（计划层）。
     *
     * @param projectId      项目主键
     * @param episodeId      剧集主键
     * @param rendererFamily 渲染器家族（可选，用于电影感声明校验）
     * @param renderRuntime  渲染运行时（可选，随报告回传记录）
     * @return 幻灯片风险评分报告
     */
    @GetMapping("/slideshow-risk")
    @Operation(summary = "幻灯片风险评分（计划层）")
    public SlideshowRiskDto slideshowRisk(@Parameter(description = "项目主键") @PathVariable Long projectId,
                                          @Parameter(description = "剧集主键") @PathVariable Long episodeId,
                                          @RequestParam(required = false) String rendererFamily,
                                          @RequestParam(required = false) String renderRuntime) {
        assertEpisodeBelongsToProject(projectId, episodeId);
        try {
            List<Shot> shots = shotRepository.findByEpisodeIdOrderByShotNoAsc(episodeId);
            SlideshowRiskScorer.SlideshowRiskReport report = slideshowRiskScorer.scoreShots(shots, rendererFamily);
            Map<String, DimensionScoreDto> dims = new LinkedHashMap<>();
            report.dimensions().forEach((k, v) -> dims.put(k, new DimensionScoreDto(v.score(), v.reason())));
            return new SlideshowRiskDto(report.average(), report.verdict(), report.verdictLabel(),
                    report.scenesChecked(), dims, renderRuntime);
        } catch (Exception e) {
            log.warn("幻灯片风险评分失败，降级返回不通过报告：episodeId={}", episodeId, e);
            return new SlideshowRiskDto(5.0, "fail", "不通过", 0, Map.of(), renderRuntime);
        }
    }

    /**
     * 幻灯片风险评分报告 DTO。
     *
     * @param average       六维平均分（0-5，越低越好）
     * @param verdict       结论：strong/acceptable/revise/fail
     * @param verdictLabel  结论中文标签
     * @param scenesChecked 已评分的分镜数
     * @param dimensions    各维度评分（键为维度名）
     * @param renderRuntime 渲染运行时（请求回传）
     */
    public record SlideshowRiskDto(double average, String verdict, String verdictLabel,
                                   int scenesChecked, Map<String, DimensionScoreDto> dimensions,
                                   String renderRuntime) {
    }

    /**
     * 单维度评分 DTO。
     *
     * @param score  分数（0-5，越低越好）
     * @param reason 评分理由
     */
    public record DimensionScoreDto(double score, String reason) {
    }
}
