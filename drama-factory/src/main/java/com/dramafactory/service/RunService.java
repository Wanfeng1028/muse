package com.dramafactory.service;

import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * Harness Run 引擎核心服务。
 * 负责规划预览、运行创建、状态机迁移、审批、重试与重跑。
 * 所有对既有链路的调用均为只读式调用，不修改既有实现。
 */
@Service
public class RunService {

    private static final Logger log = LoggerFactory.getLogger(RunService.class);

    private static final int MAX_EPISODES = 6;
    private static final String SYSTEM_PLANNING_PROMPT =
            "你是短剧制片人，只输出 JSON：{\"episodes\":[{\"episodeNo\":1,\"title\":\"…\",\"outline\":\"…\"}]}，"
                    + "集数从目标里解析如\"3 集\"，默认 1 集，最多 6 集；不要输出多余文字。";

    private final RunRepository runRepository;
    private final AgentStepRepository agentStepRepository;
    private final EpisodeRepository episodeRepository;
    private final FinalCutRepository finalCutRepository;
    private final VideoTaskRepository videoTaskRepository;
    private final LlmScriptService llmScriptService;
    private final ProjectService projectService;
    private final EpisodeService episodeService;
    private final FinalCutService finalCutService;
    private final RunLogService runLogService;
    private final ObjectMapper objectMapper;
    private final String scriptModel;
    private final CurrentUser currentUser;
    private final DramaProjectRepository projectRepository;

    public RunService(RunRepository runRepository,
                      AgentStepRepository agentStepRepository,
                      EpisodeRepository episodeRepository,
                      FinalCutRepository finalCutRepository,
                      VideoTaskRepository videoTaskRepository,
                      LlmScriptService llmScriptService,
                      ProjectService projectService,
                      EpisodeService episodeService,
                      FinalCutService finalCutService,
                      RunLogService runLogService,
                      ObjectMapper objectMapper,
                      @Value("${drama.script.llm.model:Deepseek-v4-flash}") String scriptModel,
                      CurrentUser currentUser,
                      DramaProjectRepository projectRepository) {
        this.runRepository = runRepository;
        this.agentStepRepository = agentStepRepository;
        this.episodeRepository = episodeRepository;
        this.finalCutRepository = finalCutRepository;
        this.videoTaskRepository = videoTaskRepository;
        this.llmScriptService = llmScriptService;
        this.projectService = projectService;
        this.episodeService = episodeService;
        this.finalCutService = finalCutService;
        this.runLogService = runLogService;
        this.objectMapper = objectMapper;
        this.scriptModel = scriptModel;
        this.currentUser = currentUser;
        this.projectRepository = projectRepository;
    }

    /**
     * 规划预览：调用模型生成计划，失败回退单集模板计划。
     */
    public Records.PlanPreview planPreview(String goal) {
        if (goal == null || goal.isBlank()) {
            throw new IllegalArgumentException("目标不能为空");
        }
        String trimmedGoal = goal.trim();
        int requested = parseEpisodeCount(trimmedGoal);
        boolean truncated = requested > MAX_EPISODES;
        int count = Math.min(requested, MAX_EPISODES);

        try {
            ObjectNode body = buildPlanningBody(trimmedGoal, count);
            String content = llmScriptService.callModel(body);
            List<Records.PlanEpisode> episodes = parsePlan(content, count);
            if (episodes.isEmpty()) {
                return fallbackPlan(trimmedGoal, count, truncated);
            }
            return new Records.PlanPreview(trimmedGoal, episodes, false);
        } catch (Exception ex) {
            log.warn("规划预览失败，回退模板计划：{}", ex.getMessage());
            return fallbackPlan(trimmedGoal, count, truncated);
        }
    }

    private ObjectNode buildPlanningBody(String goal, int count) {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("model", scriptModel);
        ArrayNode messages = body.putArray("messages");
        ObjectNode sys = messages.addObject();
        sys.put("role", "system");
        sys.put("content", SYSTEM_PLANNING_PROMPT);
        ObjectNode user = messages.addObject();
        user.put("role", "user");
        user.put("content", "目标=" + goal + "；请规划 " + count + " 集。");
        return body;
    }

    private List<Records.PlanEpisode> parsePlan(String content, int count) {
        List<Records.PlanEpisode> result = new ArrayList<>();
        if (content == null || content.isBlank()) {
            return result;
        }
        String json = sanitizeJson(content);
        if (json == null) {
            return result;
        }
        try {
            JsonNode root = objectMapper.readTree(json);
            JsonNode episodes = root.get("episodes");
            if (episodes == null || !episodes.isArray()) {
                return result;
            }
            int idx = 1;
            for (JsonNode node : episodes) {
                if (result.size() >= count) {
                    break;
                }
                String title = node.path("title").asText("");
                String outline = node.path("outline").asText("");
                int episodeNo = node.path("episodeNo").asInt(idx);
                if (title.isBlank()) {
                    title = "第 " + episodeNo + " 集";
                }
                result.add(new Records.PlanEpisode(episodeNo, title, outline));
                idx++;
            }
        } catch (Exception ex) {
            log.warn("计划 JSON 解析失败：{}", ex.getMessage());
        }
        return result;
    }

    private String sanitizeJson(String content) {
        String s = content.trim();
        if (s.startsWith("```")) {
            int firstLineEnd = s.indexOf('\n');
            if (firstLineEnd > 0) {
                s = s.substring(firstLineEnd + 1);
            }
            int fence = s.lastIndexOf("```");
            if (fence >= 0) {
                s = s.substring(0, fence);
            }
            s = s.trim();
        }
        int start = s.indexOf('{');
        int end = s.lastIndexOf('}');
        if (start < 0 || end <= start) {
            return null;
        }
        return s.substring(start, end + 1);
    }

    private Records.PlanPreview fallbackPlan(String goal, int count, boolean truncated) {
        List<Records.PlanEpisode> episodes = new ArrayList<>();
        for (int i = 1; i <= count; i++) {
            episodes.add(new Records.PlanEpisode(i, "第 " + i + " 集", "围绕目标「" + shortGoal(goal) + "」的第 " + i + " 集剧情。"));
        }
        return new Records.PlanPreview(goal, episodes, true);
    }

    private String shortGoal(String goal) {
        String g = goal.trim();
        return g.length() > 60 ? g.substring(0, 60) : g;
    }

    private int parseEpisodeCount(String goal) {
        java.util.regex.Matcher m = java.util.regex.Pattern.compile("(\\d+)\\s*集").matcher(goal);
        if (m.find()) {
            try {
                int v = Integer.parseInt(m.group(1));
                return Math.max(1, v);
            } catch (NumberFormatException ignore) {
                return 1;
            }
        }
        return 1;
    }

    /**
     * 创建运行：建 Run → 建 Project → 建 Episodes → 建 5 类 AgentStep → Run RUNNING。
     */
    @Transactional
    public Long createRun(String goal, Records.PlanPreview plan) {
        return createRun(goal, plan, null, null);
    }

    /**
     * 创建运行（支持为 SCRIPT/BOARD 步骤指定 Skill）。
     *
     * @param goal          自然语言目标
     * @param plan          已确认的计划预览
     * @param scriptSkillId SCRIPT 步骤使用的 Skill ID，可空
     * @param boardSkillId  BOARD 步骤使用的 Skill ID，可空
     * @return 新建 Run 的 ID
     */
    @Transactional
    public Long createRun(String goal, Records.PlanPreview plan, Long scriptSkillId, Long boardSkillId) {
        if (goal == null || goal.isBlank()) {
            throw new IllegalArgumentException("目标不能为空");
        }
        if (plan == null || plan.episodes() == null || plan.episodes().isEmpty()) {
            throw new IllegalArgumentException("计划不能为空");
        }
        String trimmedGoal = goal.trim();

        Run run = new Run();
        run.setGoal(trimmedGoal);
        run.setStatus(RunStatus.PLANNED);
        run.setPlanJson(writePlanJson(plan));
        run = runRepository.save(run);

        Records.ProjectResponse project = projectService.create(
                new Records.ProjectRequest(shortGoal(trimmedGoal), null, null, null, null));
        run.setProjectId(project.id());
        run = runRepository.save(run);

        int seq = 1;
        List<Records.PlanEpisode> episodes = plan.episodes();
        for (Records.PlanEpisode ep : episodes) {
            Records.EpisodeResponse episode = episodeService.create(
                    project.id(), new Records.EpisodeRequest(ep.episodeNo(), ep.title(), ep.outline(), null, null));
            Long episodeId = episode.id();
            for (AgentType type : defaultAgentOrder()) {
                AgentStep step = new AgentStep();
                step.setRun(run);
                step.setSeqNo(seq++);
                step.setAgentType(type);
                step.setName(buildStepName(ep.episodeNo(), type));
                step.setStatus(AgentStepStatus.PENDING);
                step.setEpisodeId(episodeId);
                if (type == AgentType.SCRIPT && scriptSkillId != null) {
                    step.setSkillId(scriptSkillId);
                }
                if (type == AgentType.BOARD && boardSkillId != null) {
                    step.setSkillId(boardSkillId);
                }
                step.setCostEstimated(false);
                agentStepRepository.save(step);
            }
        }

        run.setStatus(RunStatus.RUNNING);
        run = runRepository.save(run);
        log.info("创建运行 runId={} 集数={}", run.getId(), episodes.size());
        return run.getId();
    }

    private List<AgentType> defaultAgentOrder() {
        return List.of(AgentType.SCRIPT, AgentType.BOARD, AgentType.VIDEO, AgentType.EDIT, AgentType.QC);
    }

    private String buildStepName(int episodeNo, AgentType type) {
        return "第 " + episodeNo + " 集 · " + type.getLabel();
    }

    private String writePlanJson(Records.PlanPreview plan) {
        try {
            ObjectNode root = objectMapper.createObjectNode();
            root.put("goal", plan.goal());
            root.put("fallback", plan.fallback());
            ArrayNode arr = root.putArray("episodes");
            for (Records.PlanEpisode ep : plan.episodes()) {
                ObjectNode n = arr.addObject();
                n.put("episodeNo", ep.episodeNo());
                n.put("title", ep.title());
                n.put("outline", ep.outline());
            }
            return objectMapper.writeValueAsString(root);
        } catch (Exception ex) {
            log.warn("计划序列化失败：{}", ex.getMessage());
            return "{}";
        }
    }

    /**
     * 暂停：仅 RUNNING → PAUSED。
     */
    @Transactional
    public void pause(Long runId) {
        Run run = requireRun(runId);
        if (run.getStatus() != RunStatus.RUNNING) {
            throw new IllegalStateException("只有 RUNNING 状态可暂停，当前：" + run.getStatus());
        }
        run.setStatus(RunStatus.PAUSED);
        runRepository.save(run);
    }

    /**
     * 恢复：仅 PAUSED → RUNNING。
     */
    @Transactional
    public void resume(Long runId) {
        Run run = requireRun(runId);
        if (run.getStatus() != RunStatus.PAUSED) {
            throw new IllegalStateException("只有 PAUSED 状态可恢复，当前：" + run.getStatus());
        }
        run.setStatus(RunStatus.RUNNING);
        runRepository.save(run);
    }

    /**
     * 取消：RUNNING/PAUSED/WAITING_APPROVAL → CANCELLED，并清理 PENDING 步骤与视频任务。
     */
    @Transactional
    public void cancel(Long runId) {
        Run run = requireRun(runId);
        RunStatus st = run.getStatus();
        if (st != RunStatus.RUNNING && st != RunStatus.PAUSED && st != RunStatus.WAITING_APPROVAL) {
            throw new IllegalStateException("当前状态不可取消：" + st);
        }
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        List<Long> episodeIds = new ArrayList<>();
        for (AgentStep step : steps) {
            if (step.getStatus() == AgentStepStatus.PENDING) {
                step.setStatus(AgentStepStatus.CANCELLED);
                agentStepRepository.save(step);
            }
            if (step.getEpisodeId() != null && !episodeIds.contains(step.getEpisodeId())) {
                episodeIds.add(step.getEpisodeId());
            }
        }
        for (Long episodeId : episodeIds) {
            List<VideoTask> tasks = videoTaskRepository.findByEpisodeId(episodeId);
            for (VideoTask task : tasks) {
                if (task.getStatus() == VideoTaskStatus.PENDING
                        || task.getStatus() == VideoTaskStatus.PROCESSING) {
                    task.setStatus(VideoTaskStatus.FAILED);
                    task.setErrorMessage("运行已取消");
                    videoTaskRepository.save(task);
                }
            }
        }
        run.setStatus(RunStatus.CANCELLED);
        runRepository.save(run);
    }

    /**
     * 重试步骤：step → PENDING 清 error，run → RUNNING（终态可重开）。
     */
    @Transactional
    public void retryStep(Long runId, Long stepId) {
        Run run = requireRun(runId);
        AgentStep step = agentStepRepository.findById(stepId)
                .orElseThrow(() -> new IllegalArgumentException("步骤不存在：" + stepId));
        if (step.getRun() == null || !Objects.equals(step.getRun().getId(), runId)) {
            throw new IllegalArgumentException("步骤不属于该运行：stepId=" + stepId);
        }
        step.setStatus(AgentStepStatus.PENDING);
        step.setErrorMessage(null);
        agentStepRepository.save(step);

        if (run.getStatus() == RunStatus.FAILED || run.getStatus() == RunStatus.CANCELLED) {
            run.setStatus(RunStatus.RUNNING);
            runRepository.save(run);
        }
    }

    /**
     * 审批：仅 WAITING_APPROVAL。通过→QC 步骤成功、run RUNNING；拒绝→QC 步骤失败、run FAILED。
     */
    @Transactional
    public void approve(Long runId, boolean approved, String note) {
        Run run = requireRun(runId);
        if (run.getStatus() != RunStatus.WAITING_APPROVAL) {
            throw new IllegalStateException("只有 WAITING_APPROVAL 状态可审批，当前：" + run.getStatus());
        }
        Long finalCutId = findFinalCutId(runId);
        if (finalCutId == null) {
            throw new IllegalStateException("运行无关联成片，无法审批：runId=" + runId);
        }
        AgentStep qcStep = findWaitingQcStep(runId);

        if (approved) {
            finalCutService.qc(finalCutId, new Records.QcRequest("APPROVED", note));
            if (qcStep != null) {
                qcStep.setStatus(AgentStepStatus.SUCCEEDED);
                qcStep.setEndedAt(LocalDateTime.now());
                agentStepRepository.save(qcStep);
            }
            run.setStatus(RunStatus.RUNNING);
            runRepository.save(run);
        } else {
            finalCutService.qc(finalCutId, new Records.QcRequest("REJECTED", note));
            if (qcStep != null) {
                qcStep.setStatus(AgentStepStatus.FAILED);
                qcStep.setErrorMessage(note);
                qcStep.setEndedAt(LocalDateTime.now());
                agentStepRepository.save(qcStep);
            }
            run.setStatus(RunStatus.FAILED);
            runRepository.save(run);
        }
    }

    /**
     * 找到当前等待审批的 QC 步骤（RUNNING 状态的 QC 步）；找不到则回退到最后一个 QC 步。
     */
    private AgentStep findWaitingQcStep(Long runId) {
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        AgentStep fallback = null;
        for (AgentStep s : steps) {
            if (s.getAgentType() == AgentType.QC) {
                fallback = s;
                if (s.getStatus() == AgentStepStatus.RUNNING) {
                    return s;
                }
            }
        }
        return fallback;
    }

    private Long findFinalCutId(Long runId) {
        AgentStep qcStep = findWaitingQcStep(runId);
        if (qcStep == null || qcStep.getEpisodeId() == null) {
            return null;
        }
        Optional<FinalCut> fc = finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(qcStep.getEpisodeId());
        return fc.map(FinalCut::getId).orElse(null);
    }

    /**
     * 重跑：复制 planJson，可覆盖 goal，新建 Run 全套。
     */
    @Transactional
    public Long rerun(Long runId, String goalOverride) {
        Run old = requireRun(runId);
        RunStatus st = old.getStatus();
        if (st != RunStatus.SUCCEEDED && st != RunStatus.FAILED && st != RunStatus.CANCELLED) {
            throw new IllegalStateException("仅终态运行可重跑，当前：" + st);
        }
        String goal = (goalOverride != null && !goalOverride.isBlank()) ? goalOverride.trim() : old.getGoal();
        Records.PlanPreview plan = readPlanPreview(old.getPlanJson(), goal);
        return createRun(goal, plan);
    }

    private Records.PlanPreview readPlanPreview(String planJson, String goal) {
        List<Records.PlanEpisode> episodes = new ArrayList<>();
        if (planJson != null && !planJson.isBlank()) {
            try {
                JsonNode root = objectMapper.readTree(planJson);
                JsonNode arr = root.get("episodes");
                if (arr != null && arr.isArray()) {
                    for (JsonNode n : arr) {
                        episodes.add(new Records.PlanEpisode(
                                n.path("episodeNo").asInt(episodes.size() + 1),
                                n.path("title").asText("第 " + (episodes.size() + 1) + " 集"),
                                n.path("outline").asText("")));
                    }
                }
            } catch (Exception ex) {
                log.warn("读取计划失败，回退单集：{}", ex.getMessage());
            }
        }
        if (episodes.isEmpty()) {
            episodes.add(new Records.PlanEpisode(1, "第 1 集", "围绕目标「" + shortGoal(goal) + "」的剧情。"));
        }
        return new Records.PlanPreview(goal, episodes, false);
    }

    /**
     * 查询运行详情（DTO）。
     */
    @Transactional(readOnly = true)
    public Records.RunDetailResponse getRun(Long runId) {
        Run run = requireRun(runId);
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        return toDetailResponse(run, steps);
    }

    /**
     * 增量读取某步骤的实时日志（含运行归属校验）。
     */
    @Transactional(readOnly = true)
    public Records.LogReadResponse readStepLog(Long runId, Long stepId, long offset) {
        if (stepId == null) {
            throw new IllegalArgumentException("stepId 不能为空");
        }
        AgentStep step = agentStepRepository.findById(stepId)
                .orElseThrow(() -> new ResourceNotFoundException("AgentStep", stepId));
        // 事务内初始化懒加载的 run 关联，避免控制器层 LazyInitializationException
        Long ownerRunId = step.getRun().getId();
        if (!ownerRunId.equals(runId)) {
            throw new IllegalArgumentException("步骤不属于该运行：stepId=" + stepId);
        }
        RunLogService.LogReadResult r = runLogService.read(runId, step.getSeqNo(), offset);
        return new Records.LogReadResponse(r.content(), r.nextOffset(), r.eof());
    }

    /**
     * 实体转 RunDetailResponse。
     */
    public static Records.RunDetailResponse toDetailResponse(Run run, List<AgentStep> steps) {
        List<Records.AgentStepResponse> stepResponses = new ArrayList<>();
        if (steps != null) {
            for (AgentStep s : steps) {
                stepResponses.add(toStepResponse(s));
            }
        }
        return new Records.RunDetailResponse(toRunResponse(run), stepResponses, run.getProjectId());
    }

    /**
     * 实体转 RunResponse。
     */
    public static Records.RunResponse toRunResponse(Run run) {
        RunStatus status = run.getStatus();
        return new Records.RunResponse(
                run.getId(), run.getGoal(), status,
                status == null ? null : status.getLabel(),
                run.getProjectId(), run.getTotalTokens(), run.getTotalCostCents(),
                run.getCreatedAt(), run.getUpdatedAt());
    }

    /**
     * 实体转 AgentStepResponse。
     */
    public static Records.AgentStepResponse toStepResponse(AgentStep step) {
        AgentType agentType = step.getAgentType();
        AgentStepStatus status = step.getStatus();
        return new Records.AgentStepResponse(
                step.getId(), step.getSeqNo(), agentType,
                agentType == null ? null : agentType.getLabel(),
                step.getName(), status,
                status == null ? null : status.getLabel(),
                step.getEpisodeId(), step.getInputSummary(), step.getOutputSummary(),
                step.getToolCallsJson(), step.getTokensUsed(), step.getCostCents(),
                step.getCostEstimated(), step.getLatencyMs(), step.getErrorMessage(),
                step.getStartedAt(), step.getEndedAt());
    }

    /**
     * 列表：按创建时间倒序。
     */
    @Transactional(readOnly = true)
    public List<Run> listRuns() {
        List<Run> all = new ArrayList<>();
        runRepository.findAll().forEach(all::add);
        all.sort(Comparator.comparing(Run::getCreatedAt, Comparator.nullsLast(Comparator.reverseOrder())));
        return all;
    }

    /**
     * 统计：总数、成功、失败、成功率、平均耗时。
     *
     * <p>只统计当前用户名下项目的 run；projectId 为空或归属他人的 run 不计入。
     */
    @Transactional(readOnly = true)
    public Records.RunStatsResponse stats() {
        List<Run> all = new ArrayList<>();
        runRepository.findAll().forEach(all::add);
        String ownerId = currentUser.currentUserId();
        Set<Long> ownedProjectIds = new HashSet<>();
        for (DramaProject p : projectRepository.findByOwnerId(ownerId, Sort.by("id"))) {
            if (p.getId() != null) {
                ownedProjectIds.add(p.getId());
            }
        }
        all.removeIf(r -> r.getProjectId() == null || !ownedProjectIds.contains(r.getProjectId()));
        long total = all.size();

        long succeeded = 0;
        long failed = 0;
        long durationSum = 0;
        long durationCount = 0;
        for (Run r : all) {
            if (r.getStatus() == RunStatus.SUCCEEDED) {
                succeeded++;
            } else if (r.getStatus() == RunStatus.FAILED) {
                failed++;
            }
            if (r.getCreatedAt() != null && r.getUpdatedAt() != null) {
                durationSum += Duration.between(r.getCreatedAt(), r.getUpdatedAt()).toMillis();
                durationCount++;
            }
        }
        double rate = total == 0 ? 0.0 : (double) succeeded / total;
        long avg = durationCount == 0 ? 0 : durationSum / durationCount;
        return new Records.RunStatsResponse(total, succeeded, failed, rate, avg);
    }

    /**
     * 汇总 run 的 token/成本（step 求和，null 按 0）。
     */
    @Transactional
    public void aggregateTotals(Long runId) {
        Run run = requireRun(runId);
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        long tokens = 0;
        long cost = 0;
        for (AgentStep s : steps) {
            if (s.getTokensUsed() != null) {
                tokens += s.getTokensUsed();
            }
            if (s.getCostCents() != null) {
                cost += s.getCostCents();
            }
        }
        run.setTotalTokens(tokens);
        run.setTotalCostCents(cost);
        runRepository.save(run);
    }

    /**
     * 若全部 step 成功则标记 run 成功并汇总。
     */
    @Transactional
    public void markSucceededIfAllDone(Long runId) {
        Run run = requireRun(runId);
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        if (steps.isEmpty()) {
            return;
        }
        for (AgentStep s : steps) {
            if (s.getStatus() != AgentStepStatus.SUCCEEDED && s.getStatus() != AgentStepStatus.SKIPPED) {
                return;
            }
        }
        aggregateTotals(runId);
        run.setStatus(RunStatus.SUCCEEDED);
        runRepository.save(run);
    }

    private Run requireRun(Long runId) {
        if (runId == null) {
            throw new IllegalArgumentException("runId 不能为空");
        }
        return runRepository.findById(runId)
                .orElseThrow(() -> new ResourceNotFoundException("Run", runId));
    }
}
