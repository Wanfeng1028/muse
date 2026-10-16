package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.RunService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Harness Run 引擎 REST 控制器。
 *
 * <p>负责 Run 的规划预览、创建、查询、状态控制、步骤重试、审批、重跑、统计与步骤日志。
 * 本控制器只做 HTTP 适配，所有状态机逻辑在 {@link RunService}。</p>
 */
@RestController
@RequestMapping("/api/runs")
@Tag(name = "Runs", description = "运行引擎的创建、控制与查询")
public class RunController {

    private static final Logger log = LoggerFactory.getLogger(RunController.class);

    private final RunService runService;

    /**
     * 构造器注入。
     *
     * @param runService Run 核心服务
     */
    public RunController(RunService runService) {
        this.runService = runService;
    }

    /**
     * 规划预览：根据自然语言目标生成执行计划，不落库。
     *
     * @param request 预览请求，goal 不可空白
     * @return 计划预览
     */
    @PostMapping("/preview")
    @Operation(summary = "预览运行计划")
    public Records.PlanPreview preview(@Valid @RequestBody PreviewRequest request) {
        log.info("预览 Run 计划，goal 长度={}", request.goal().length());
        return runService.planPreview(request.goal());
    }

    /**
     * 创建并启动一次 Run。
     *
     * @param request 创建请求，goal 与 plan 均不可空
     * @return 201 与新建 runId
     */
    @PostMapping("")
    @Operation(summary = "创建并启动运行")
    public ResponseEntity<Map<String, Long>> create(@Valid @RequestBody CreateRunRequest request) {
        log.info("创建 Run，goal 长度={}，集数={}", request.goal().length(), request.plan().episodes().size());
        Long runId = runService.createRun(request.goal(), request.plan(),
                request.scriptSkillId(), request.boardSkillId());
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("runId", runId));
    }

    /**
     * 列出全部 Run（创建时间倒序）。
     *
     * @return Run 响应列表
     */
    @GetMapping("")
    @Operation(summary = "列出全部运行")
    public List<Records.RunResponse> list() {
        List<Records.RunResponse> result = new ArrayList<>();
        for (var run : runService.listRuns()) {
            result.add(RunService.toRunResponse(run));
        }
        return result;
    }

    /**
     * 查询 Run 详情（含 Agent 步骤时间线）。
     *
     * @param id Run 主键
     * @return Run 详情
     */
    @GetMapping("/{id}")
    @Operation(summary = "按 ID 查询运行详情")
    public Records.RunDetailResponse detail(@Parameter(description = "Run 主键") @PathVariable Long id) {

        return runService.getRun(id);
    }

    /**
     * 暂停 Run（仅 RUNNING 可暂停）。
     *
     * @param id Run 主键
     * @return 更新后的 Run 详情
     */
    @PostMapping("/{id}/pause")
    @Operation(summary = "暂停运行")
    public Records.RunDetailResponse pause(@Parameter(description = "Run 主键") @PathVariable Long id) {

        runService.pause(id);
        return runService.getRun(id);
    }

    /**
     * 恢复 Run（仅 PAUSED 可恢复）。
     *
     * @param id Run 主键
     * @return 更新后的 Run 详情
     */
    @PostMapping("/{id}/resume")
    @Operation(summary = "恢复运行")
    public Records.RunDetailResponse resume(@Parameter(description = "Run 主键") @PathVariable Long id) {

        runService.resume(id);
        return runService.getRun(id);
    }

    /**
     * 取消 Run。
     *
     * @param id Run 主键
     * @return 更新后的 Run 详情
     */
    @PostMapping("/{id}/cancel")
    @Operation(summary = "取消运行")
    public Records.RunDetailResponse cancel(@Parameter(description = "Run 主键") @PathVariable Long id) {

        runService.cancel(id);
        return runService.getRun(id);
    }

    /**
     * 重试某个步骤（终态 Run 可重开）。
     *
     * @param id     Run 主键
     * @param stepId 步骤主键
     * @return 更新后的 Run 详情
     */
    @PostMapping("/{id}/steps/{stepId}/retry")
    @Operation(summary = "重试某个步骤")
    public Records.RunDetailResponse retry(@Parameter(description = "Run 主键") @PathVariable Long id,
                                           @Parameter(description = "步骤主键") @PathVariable Long stepId) {

        runService.retryStep(id, stepId);
        return runService.getRun(id);
    }

    /**
     * 审批（仅 WAITING_APPROVAL）。通过则继续执行，拒绝则 Run 失败。
     *
     * @param id      Run 主键
     * @param request 审批请求
     * @return 更新后的 Run 详情
     */
    @PostMapping("/{id}/approve")
    @Operation(summary = "审批运行")
    public Records.RunDetailResponse approve(@Parameter(description = "Run 主键") @PathVariable Long id,
                                             @RequestBody(required = false) ApproveRequest request) {

        boolean approved = request != null && Boolean.TRUE.equals(request.approved());
        String note = request == null ? null : request.note();
        runService.approve(id, approved, note);
        return runService.getRun(id);
    }

    /**
     * 基于某次运行改参数重跑（仅终态可重跑，goal 可覆盖）。
     *
     * @param id      Run 主键
     * @param request 重跑请求
     * @return 201 与新 runId
     */
    @PostMapping("/{id}/rerun")
    @Operation(summary = "基于某次运行重跑")
    public ResponseEntity<Map<String, Long>> rerun(@Parameter(description = "Run 主键") @PathVariable Long id,
                                                   @RequestBody(required = false) Records.RerunRequest request) {

        String goal = request == null ? null : request.goal();
        Long newId = runService.rerun(id, goal);
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("runId", newId));
    }

    /**
     * Run 统计：总数 / 成功 / 失败 / 成功率 / 平均耗时。
     *
     * @return 统计响应
     */
    @GetMapping("/stats")
    @Operation(summary = "查询当前用户的运行统计")
    public Records.RunStatsResponse stats() {

        return runService.stats();
    }

    /**
     * 增量读取某步骤的实时日志。
     *
     * @param id     Run 主键
     * @param stepId 步骤主键
     * @param offset 起始字节偏移（负数按 0 处理）
     * @return 日志内容与下次偏移
     */
    @GetMapping("/{id}/steps/{stepId}/logs")
    @Operation(summary = "增量读取步骤日志")
    public Records.LogReadResponse logs(@Parameter(description = "Run 主键") @PathVariable Long id,
                                        @Parameter(description = "步骤主键") @PathVariable Long stepId,

                                        @Parameter(description = "起始字节偏移，负数按 0 处理") @RequestParam(name = "offset", defaultValue = "0") long offset) {
        return runService.readStepLog(id, stepId, offset);
    }

    /**
     * 规划预览请求。
     *
     * @param goal 自然语言目标
     */
    public record PreviewRequest(@NotBlank(message = "goal 不能为空") String goal) {
    }

    /**
     * 创建 Run 请求。
     *
     * @param goal 自然语言目标
     * @param plan 已确认的计划预览
     * @param scriptSkillId 可选，SCRIPT 步骤使用的 Skill ID
     * @param boardSkillId 可选，BOARD 步骤使用的 Skill ID
     */
    public record CreateRunRequest(@NotBlank(message = "goal 不能为空") String goal,
                                   @NotNull(message = "plan 不能为空") Records.PlanPreview plan,
                                   Long scriptSkillId,
                                   Long boardSkillId) {
    }

    /**
     * 审批请求。
     *
     * @param approved 是否通过（空按拒绝处理）
     * @param note     备注 / 打回原因
     */
    public record ApproveRequest(Boolean approved, String note) {
    }
}
