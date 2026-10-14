package com.dramafactory.service;

import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.dto.Records;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.env.Environment;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.File;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

/**
 * Harness Run 执行引擎。
 * <p>
 * 通过定时任务驱动 Run 中的 AgentStep 逐步执行；每一步只做“编排 + 包上去”，
 * 底层能力全部委托给已有的 ScriptService / ScriptSplitterService / VideoTaskService /
 * FinalCutService，不修改任何已有服务实现。
 * <p>
 * 设计要点：
 * <ul>
 *     <li>tick 方法 synchronized，避免同一 JVM 内并发重复调度；</li>
 *     <li>单个 step 执行 try/catch 兜底，异常不杀死调度线程；</li>
 *     <li>VIDEO 步骤需要跨 tick 等待 video_task 完成，因此本 tick 不结束该 step。</li>
 * </ul>
 */
@Service
public class RunExecutor {

    private static final Logger log = LoggerFactory.getLogger(RunExecutor.class);

    /** 审批门配置项：是否启用 QC 人工审批。 */
    private static final String PROP_QC_MANUAL_APPROVAL = "harness.qc.manual-approval";

    private static final int ERROR_MESSAGE_MAX_LEN = 500;

    private final RunRepository runRepository;
    private final AgentStepRepository agentStepRepository;
    private final VideoTaskRepository videoTaskRepository;
    private final ScriptService scriptService;
    private final ScriptSplitterService scriptSplitterService;
    private final VideoTaskService videoTaskService;
    private final FinalCutService finalCutService;
    private final RunLogService runLogService;
    private final Environment environment;
    private final ObjectMapper objectMapper;

    public RunExecutor(RunRepository runRepository,
                       AgentStepRepository agentStepRepository,
                       VideoTaskRepository videoTaskRepository,
                       ScriptService scriptService,
                       ScriptSplitterService scriptSplitterService,
                       VideoTaskService videoTaskService,
                       FinalCutService finalCutService,
                       RunLogService runLogService,
                       Environment environment,
                       ObjectMapper objectMapper) {
        this.runRepository = runRepository;
        this.agentStepRepository = agentStepRepository;
        this.videoTaskRepository = videoTaskRepository;
        this.scriptService = scriptService;
        this.scriptSplitterService = scriptSplitterService;
        this.videoTaskService = videoTaskService;
        this.finalCutService = finalCutService;
        this.runLogService = runLogService;
        this.environment = environment;
        this.objectMapper = objectMapper;
    }

    /**
     * 每 5 秒调度一次，推进所有处于 RUNNING 状态的 Run。
     */
    @Scheduled(fixedDelay = 5000)
    public synchronized void tick() {
        List<Run> runningRuns;
        try {
            runningRuns = runRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING);
        } catch (Exception e) {
            log.warn("查询 RUNNING 状态 Run 失败: {}", e.getMessage());
            return;
        }
        if (runningRuns.isEmpty()) {
            return;
        }
        for (Run run : runningRuns) {
            try {
                advanceRun(run);
            } catch (Exception e) {
                log.warn("推进 Run[id={}] 失败: {}", run.getId(), e.getMessage(), e);
            }
        }
    }

    /**
     * 推进单个 Run：找到第一个 PENDING step 执行。
     */
    /**
     * 注意：本方法故意不加 @Transactional（自调用不经过 Spring 代理，加了也不生效）。
     * 执行器按操作提交：每一步状态变更立即落库，保证前端轮询实时可见；单步失败不影响已提交状态。
     */
    protected void advanceRun(Run run) {
        // 重新加载，避免脏数据
        Run fresh = runRepository.findById(run.getId()).orElse(null);
        if (fresh == null || fresh.getStatus() != RunStatus.RUNNING) {
            return;
        }

        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(fresh.getId());
        if (steps.isEmpty()) {
            fresh.setStatus(RunStatus.SUCCEEDED);
            runRepository.save(fresh);
            return;
        }

        AgentStep current = null;
        for (AgentStep s : steps) {
            if (s.getStatus() == AgentStepStatus.PENDING) {
                current = s;
                break;
            }
        }

        // 没有 PENDING，但存在 RUNNING（例如 VIDEO 等待中）——本轮不推进，交给跨 tick 检查
        if (current == null) {
            // 如果所有 step 都终态 SUCCEEDED/SKIPPED，则汇总并结束 run
            boolean allTerminalSuccess = steps.stream().allMatch(s ->
                    s.getStatus() == AgentStepStatus.SUCCEEDED || s.getStatus() == AgentStepStatus.SKIPPED);
            if (allTerminalSuccess) {
                finalizeRun(fresh, steps);
            } else {
                // 检查是否存在处于 RUNNING 的 VIDEO step，需要跨 tick 轮询
                for (AgentStep s : steps) {
                    if (s.getStatus() == AgentStepStatus.RUNNING && s.getAgentType() == AgentType.VIDEO) {
                        checkVideoStep(fresh, s);
                        break;
                    }
                    if (s.getStatus() == AgentStepStatus.RUNNING && s.getAgentType() == AgentType.QC) {
                        // QC 处于 RUNNING 但需要 WAITING_APPROVAL 时已置为 WAITING_APPROVAL，这里兜底
                        break;
                    }
                }
            }
            return;
        }

        // QC 审批门：如果该 step 需要人工审批，step 保持 RUNNING（等人工），run 置 WAITING_APPROVAL，本 tick 不再推进
        if (current.getAgentType() == AgentType.QC && isQcManualApproval()) {
            current.setStatus(AgentStepStatus.RUNNING);
            current.setStartedAt(LocalDateTime.now());
            agentStepRepository.save(current);
            fresh.setStatus(RunStatus.WAITING_APPROVAL);
            runRepository.save(fresh);
            runLogService.append(fresh.getId(), current.getSeqNo(), "等待人工审批");
            return;
        }

        // 开始执行该 step
        LocalDateTime start = LocalDateTime.now();
        current.setStatus(AgentStepStatus.RUNNING);
        current.setStartedAt(start);
        current.setEndedAt(null);
        current.setErrorMessage(null);
        agentStepRepository.save(current);
        runLogService.append(fresh.getId(), current.getSeqNo(),
                "开始执行 step[" + current.getSeqNo() + "] " + current.getAgentType());

        try {
            executeStep(fresh, current);
        } catch (Exception ex) {
            // 单步兜底：标记失败，run 置 FAILED
            String msg = truncate(safeMessage(ex), ERROR_MESSAGE_MAX_LEN);
            current.setStatus(AgentStepStatus.FAILED);
            current.setErrorMessage(msg);
            current.setEndedAt(LocalDateTime.now());
            agentStepRepository.save(current);
            runLogService.append(fresh.getId(), current.getSeqNo(), "step 执行失败: " + msg);
            fresh.setStatus(RunStatus.FAILED);
            fresh.setErrorMessage(msg);
            runRepository.save(fresh);
        }
    }

    /**
     * 根据 agentType 执行对应逻辑。
     */
    private void executeStep(Run run, AgentStep step) {
        AgentType type = step.getAgentType();
        if (type == null) {
            throw new IllegalStateException("step 缺少 agentType, stepId=" + step.getId());
        }
        switch (type) {
            case SCRIPT -> runScriptStep(run, step);
            case BOARD -> runBoardStep(run, step);
            case VIDEO -> runVideoStep(run, step);
            case EDIT -> runEditStep(run, step);
            case QC -> runQcStep(run, step);
            default -> throw new IllegalStateException("未知的 agentType: " + type);
        }
    }

    /** SCRIPT：调用 ScriptService.generate(episodeId, "ai")。 */
    private void runScriptStep(Run run, AgentStep step) {
        Long episodeId = requireEpisodeId(step);
        LocalDateTime start = LocalDateTime.now();

        Records.GenerateScriptResponse resp = scriptService.generate(episodeId, "ai");
        if (resp == null) {
            throw new IllegalStateException("ScriptService.generate 返回为空, episodeId=" + episodeId);
        }

        long ms = Duration.between(start, LocalDateTime.now()).toMillis();
        step.setOutputSummary(resp.scriptText());
        step.setLatencyMs(ms);
        step.setStatus(AgentStepStatus.SUCCEEDED);
        step.setEndedAt(LocalDateTime.now());
        step.setPromptTokens(resp.promptTokens());
        step.setCompletionTokens(resp.completionTokens());
        step.setCachedTokens(0L);
        step.setTokensUsed(resp.promptTokens() + resp.completionTokens());
        step.setCostCents(null);
        step.setCostEstimated(false);
        agentStepRepository.save(step);

        // toolCalls
        ObjectNode input = objectMapper.createObjectNode();
        input.put("episodeId", episodeId);
        input.put("mode", "ai");
        ObjectNode output = objectMapper.createObjectNode();
        output.put("sceneCount", resp.sceneCount());
        output.put("source", resp.source());
        output.put("model", resp.model());
        recordToolCall(step, "ScriptService.generate", input, output, ms);

        runLogService.append(run.getId(), step.getSeqNo(),
                "SCRIPT 完成: sceneCount=" + resp.sceneCount() + ", latencyMs=" + ms);
    }

    /** BOARD：读取上一步（同集 SCRIPT）的 outputSummary，调用 splitFromScript。 */
    private void runBoardStep(Run run, AgentStep step) {
        Long episodeId = requireEpisodeId(step);

        AgentStep scriptStep = findPreviousStepOfType(run.getId(), step.getSeqNo(), AgentType.SCRIPT);
        if (scriptStep == null) {
            throw new IllegalStateException("BOARD 找不到前置 SCRIPT step, runId=" + run.getId()
                    + ", seqNo=" + step.getSeqNo());
        }
        String scriptText = scriptStep.getOutputSummary();
        if (scriptText == null || scriptText.isBlank()) {
            throw new IllegalStateException("BOARD 前置 SCRIPT step 输出为空, scriptStepId=" + scriptStep.getId());
        }

        LocalDateTime start = LocalDateTime.now();
        List<Records.ShotResponse> shots = scriptSplitterService.splitFromScript(episodeId, scriptText);
        if (shots == null) {
            throw new IllegalStateException("ScriptSplitterService.splitFromScript 返回为空, episodeId=" + episodeId);
        }
        long ms = Duration.between(start, LocalDateTime.now()).toMillis();

        StringBuilder sb = new StringBuilder();
        sb.append("shotCount=").append(shots.size());
        sb.append(", shotNos=");
        sb.append(shots.stream()
                .map(s -> String.valueOf(s.shotNo()))
                .collect(Collectors.joining(",")));

        step.setOutputSummary(sb.toString());
        step.setLatencyMs(ms);
        step.setStatus(AgentStepStatus.SUCCEEDED);
        step.setEndedAt(LocalDateTime.now());
        step.setPromptTokens(0L);
        step.setCompletionTokens(0L);
        step.setCachedTokens(0L);
        step.setTokensUsed(0L);
        step.setCostCents(null);
        step.setCostEstimated(false);
        agentStepRepository.save(step);

        ObjectNode input = objectMapper.createObjectNode();
        input.put("episodeId", episodeId);
        input.put("scriptLength", scriptText.length());
        ObjectNode output = objectMapper.createObjectNode();
        output.put("shotCount", shots.size());
        recordToolCall(step, "ScriptSplitterService.splitFromScript", input, output, ms);

        runLogService.append(run.getId(), step.getSeqNo(),
                "BOARD 完成: " + shots.size() + " 个分镜");
    }

    /** VIDEO：提交所有任务，本 tick 不结束 step，保持 RUNNING 等待后续 tick 轮询。 */
    private void runVideoStep(Run run, AgentStep step) {
        Long episodeId = requireEpisodeId(step);
        LocalDateTime start = LocalDateTime.now();

        List<Records.VideoTaskResponse> tasks = videoTaskService.submitAllForEpisode(episodeId);
        if (tasks == null) {
            throw new IllegalStateException("VideoTaskService.submitAllForEpisode 返回为空, episodeId=" + episodeId);
        }
        long ms = Duration.between(start, LocalDateTime.now()).toMillis();

        // 保持 RUNNING，不设置 endedAt
        step.setStatus(AgentStepStatus.RUNNING);
        agentStepRepository.save(step);

        ObjectNode input = objectMapper.createObjectNode();
        input.put("episodeId", episodeId);
        ObjectNode output = objectMapper.createObjectNode();
        output.put("submitted", tasks.size());
        recordToolCall(step, "VideoTaskService.submitAllForEpisode", input, output, ms);

        runLogService.append(run.getId(), step.getSeqNo(),
                "已提交 " + tasks.size() + " 个任务，等待生成…");
    }

    /** 跨 tick 检查 VIDEO step：全 DONE → SUCCEEDED；有 FAILED → FAILED。 */
    private void checkVideoStep(Run run, AgentStep step) {
        Long episodeId = requireEpisodeId(step);
        List<VideoTask> tasks = videoTaskRepository.findByEpisodeId(episodeId);
        if (tasks == null || tasks.isEmpty()) {
            throw new IllegalStateException("VIDEO step 关联集无 video_task, episodeId=" + episodeId);
        }

        // 存在失败任务 → step FAILED
        Optional<VideoTask> firstFailed = tasks.stream()
                .filter(t -> t.getStatus() == VideoTaskStatus.FAILED)
                .findFirst();
        if (firstFailed.isPresent()) {
            VideoTask f = firstFailed.get();
            String msg = f.getErrorMessage() == null ? "video task failed" : f.getErrorMessage();
            msg = truncate(msg, ERROR_MESSAGE_MAX_LEN);
            step.setStatus(AgentStepStatus.FAILED);
            step.setErrorMessage(msg);
            step.setEndedAt(LocalDateTime.now());
            agentStepRepository.save(step);
            runLogService.append(run.getId(), step.getSeqNo(), "VIDEO 失败: " + msg);
            run.setStatus(RunStatus.FAILED);
            run.setErrorMessage(msg);
            runRepository.save(run);
            return;
        }

        // 是否全部 DONE
        boolean allDone = tasks.stream().allMatch(t -> t.getStatus() == VideoTaskStatus.DONE);
        if (!allDone) {
            // 还在生成中，本 tick 不结束
            runLogService.append(run.getId(), step.getSeqNo(), "等待生成中…");
            return;
        }

        // 全部完成，汇总
        long totalMs = 0L;
        long totalCost = 0L;
        boolean anyUnknownCost = false;
        List<String> lines = new ArrayList<>();
        for (VideoTask t : tasks) {
            long taskMs = 0L;
            if (t.getCreatedAt() != null && t.getUpdatedAt() != null) {
                taskMs = Duration.between(t.getCreatedAt(), t.getUpdatedAt()).toMillis();
                totalMs += taskMs;
            }
            String provider = t.getProvider();
            Long costCents = null;
            if ("mock".equalsIgnoreCase(provider)) {
                costCents = 0L;
                totalCost += 0L;
            } else {
                anyUnknownCost = true;
            }
            lines.add("task=" + t.getId() + ", ms=" + taskMs + ", provider=" + provider + ", costCents=" + costCents);
        }

        StringBuilder sb = new StringBuilder();
        sb.append("tasks=").append(tasks.size());
        sb.append(", totalMs=").append(totalMs);
        sb.append(", totalCostCents=").append(anyUnknownCost ? "null" : totalCost);
        sb.append(" | ");
        sb.append(String.join("; ", lines));

        step.setOutputSummary(sb.toString());
        step.setLatencyMs(totalMs);
        step.setPromptTokens(0L);
        step.setCompletionTokens(0L);
        step.setCachedTokens(0L);
        step.setTokensUsed(0L);
        if (anyUnknownCost) {
            step.setCostCents(null);
        } else {
            step.setCostCents(totalCost);
        }
        step.setCostEstimated(anyUnknownCost);
        step.setStatus(AgentStepStatus.SUCCEEDED);
        step.setEndedAt(LocalDateTime.now());
        agentStepRepository.save(step);

        runLogService.append(run.getId(), step.getSeqNo(),
                "VIDEO 完成: " + tasks.size() + " 个任务, totalMs=" + totalMs);
    }

    /** EDIT：调用 buildFinalCut(episodeId)。 */
    private void runEditStep(Run run, AgentStep step) {
        Long episodeId = requireEpisodeId(step);
        LocalDateTime start = LocalDateTime.now();

        Records.FinalCutResponse resp = finalCutService.buildFinalCut(episodeId);
        if (resp == null) {
            throw new IllegalStateException("FinalCutService.buildFinalCut 返回为空, episodeId=" + episodeId);
        }
        long ms = Duration.between(start, LocalDateTime.now()).toMillis();

        StringBuilder sb = new StringBuilder();
        sb.append("finalCutId=").append(resp.id());
        sb.append(", status=").append(resp.status());
        if (resp.filePath() != null) {
            sb.append(", filePath=").append(resp.filePath());
        }

        step.setOutputSummary(sb.toString());
        step.setLatencyMs(ms);
        step.setStatus(AgentStepStatus.SUCCEEDED);
        step.setEndedAt(LocalDateTime.now());
        step.setPromptTokens(0L);
        step.setCompletionTokens(0L);
        step.setCachedTokens(0L);
        step.setTokensUsed(0L);
        step.setCostCents(null);
        step.setCostEstimated(false);
        agentStepRepository.save(step);

        ObjectNode input = objectMapper.createObjectNode();
        input.put("episodeId", episodeId);
        ObjectNode output = objectMapper.createObjectNode();
        output.put("finalCutId", resp.id());
        output.put("status", resp.status() == null ? null : resp.status().toString());
        recordToolCall(step, "FinalCutService.buildFinalCut", input, output, ms);

        runLogService.append(run.getId(), step.getSeqNo(),
                "EDIT 完成: finalCutId=" + resp.id() + ", status=" + resp.status());
    }

    /** QC：审批门。manual-approval=true 时已在上层拦截，这里只处理自动检查。 */
    private void runQcStep(Run run, AgentStep step) {
        Long episodeId = requireEpisodeId(step);

        // 读取本集最新的 finalCut（通过 EDIT step 的 outputSummary 记录 finalCutId 不可靠，直接用 buildFinalCut 结果）
        // 这里复用 FinalCutService 的已有查询能力：直接重新构建一次不可行（会重复），
        // 因此从 EDIT step 的 outputSummary 中解析 filePath。
        AgentStep editStep = findPreviousStepOfType(run.getId(), step.getSeqNo(), AgentType.EDIT);
        if (editStep == null) {
            throw new IllegalStateException("QC 找不到前置 EDIT step, runId=" + run.getId()
                    + ", seqNo=" + step.getSeqNo());
        }
        String editOutput = editStep.getOutputSummary();
        if (editOutput == null || editOutput.isBlank()) {
            throw new IllegalStateException("QC 前置 EDIT step 输出为空, editStepId=" + editStep.getId());
        }

        String filePath = extractFilePath(editOutput);
        if (filePath == null || filePath.isBlank()) {
            // 没有文件路径，视为未通过
            step.setStatus(AgentStepStatus.FAILED);
            step.setErrorMessage("QC 自动检查失败: 未找到成片文件路径, editStepId=" + editStep.getId());
            step.setEndedAt(LocalDateTime.now());
            agentStepRepository.save(step);
            runLogService.append(run.getId(), step.getSeqNo(), "QC 失败: 缺少 filePath");
            run.setStatus(RunStatus.FAILED);
            run.setErrorMessage(step.getErrorMessage());
            runRepository.save(run);
            return;
        }

        File f = new File(filePath);
        boolean ok = f.exists() && f.isFile() && f.length() > 0;
        if (ok) {
            step.setStatus(AgentStepStatus.SUCCEEDED);
            step.setOutputSummary("qc=APPROVED, filePath=" + filePath + ", size=" + f.length());
            step.setEndedAt(LocalDateTime.now());
            step.setPromptTokens(0L);
            step.setCompletionTokens(0L);
            step.setCachedTokens(0L);
            step.setTokensUsed(0L);
            step.setCostCents(null);
            step.setCostEstimated(false);
            agentStepRepository.save(step);
            runLogService.append(run.getId(), step.getSeqNo(), "QC 通过: filePath=" + filePath);
        } else {
            step.setStatus(AgentStepStatus.FAILED);
            step.setErrorMessage("QC 自动检查失败: 文件不存在或为空, filePath=" + filePath);
            step.setEndedAt(LocalDateTime.now());
            agentStepRepository.save(step);
            runLogService.append(run.getId(), step.getSeqNo(), "QC 失败: 文件不存在或为空");
            run.setStatus(RunStatus.FAILED);
            run.setErrorMessage(step.getErrorMessage());
            runRepository.save(run);
        }
    }

    /**
     * 汇总所有 step 的 token / cost，把 run 置为 SUCCEEDED。
     */
    private void finalizeRun(Run run, List<AgentStep> steps) {
        long totalTokens = 0L;
        long totalCost = 0L;
        boolean anyUnknown = false;
        for (AgentStep s : steps) {
            if (s.getTokensUsed() != null) {
                totalTokens += s.getTokensUsed();
            }
            if (s.getCostCents() != null) {
                totalCost += s.getCostCents();
            } else if (s.getAgentType() == AgentType.VIDEO && Boolean.TRUE.equals(s.getCostEstimated())) {
                anyUnknown = true;
            }
        }
        run.setTotalTokens(totalTokens);
        run.setTotalCostCents(anyUnknown ? null : totalCost);
        run.setStatus(RunStatus.SUCCEEDED);
        run.setErrorMessage(null);
        runRepository.save(run);
        runLogService.append(run.getId(), 0, "Run 全部完成");
    }

    /** 判断是否启用 QC 人工审批，默认 true。 */
    private boolean isQcManualApproval() {
        String v = environment.getProperty(PROP_QC_MANUAL_APPROVAL);
        if (v == null || v.isBlank()) {
            return true;
        }
        return Boolean.parseBoolean(v.trim());
    }

    /** 读取 episodeId，空则抛出明确异常。 */
    private Long requireEpisodeId(AgentStep step) {
        if (step.getEpisodeId() == null) {
            throw new IllegalStateException("step 缺少 episodeId, stepId=" + step.getId());
        }
        return step.getEpisodeId();
    }

    /** 查找同 run 内、seqNo 小于给定值、指定 agentType 的最近一个 step。 */
    private AgentStep findPreviousStepOfType(Long runId, Integer seqNo, AgentType type) {
        if (runId == null || seqNo == null || type == null) {
            return null;
        }
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        AgentStep found = null;
        for (AgentStep s : steps) {
            if (s.getAgentType() == type && s.getSeqNo() != null && s.getSeqNo() < seqNo) {
                found = s;
            }
        }
        return found;
    }

    /** 从 EDIT 输出串中解析 filePath=... 的值。 */
    private String extractFilePath(String editOutput) {
        String marker = "filePath=";
        int idx = editOutput.indexOf(marker);
        if (idx < 0) {
            return null;
        }
        int start = idx + marker.length();
        int end = editOutput.indexOf(',', start);
        if (end < 0) {
            end = editOutput.length();
        }
        return editOutput.substring(start, end).trim();
    }

    /** 记录 toolCalls JSON 数组。 */
    private void recordToolCall(AgentStep step, String tool, ObjectNode input, ObjectNode output, long ms) {
        try {
            ArrayNode arr = objectMapper.createArrayNode();
            // 如果已有内容，尝试解析
            String existing = step.getToolCallsJson();
            if (existing != null && !existing.isBlank()) {
                try {
                    var node = objectMapper.readTree(existing);
                    if (node.isArray()) {
                        arr = (ArrayNode) node;
                    }
                } catch (Exception ignore) {
                    // 旧内容损坏，忽略，重建
                }
            }
            ObjectNode call = objectMapper.createObjectNode();
            call.put("tool", tool);
            call.set("input", input);
            call.set("output", output);
            call.put("latencyMs", ms);
            arr.add(call);
            step.setToolCallsJson(objectMapper.writeValueAsString(arr));
            agentStepRepository.save(step);
        } catch (Exception e) {
            log.warn("记录 toolCall 失败, stepId={}: {}", step.getId(), e.getMessage());
        }
    }

    /** 截断字符串到指定长度。 */
    private String truncate(String s, int max) {
        if (s == null) {
            return null;
        }
        if (s.length() <= max) {
            return s;
        }
        return s.substring(0, max);
    }

    /** 取安全的异常信息。 */
    private String safeMessage(Throwable t) {
        if (t == null) {
            return "unknown error";
        }
        String m = t.getMessage();
        if (m == null || m.isBlank()) {
            return t.getClass().getSimpleName();
        }
        return m;
    }
}
