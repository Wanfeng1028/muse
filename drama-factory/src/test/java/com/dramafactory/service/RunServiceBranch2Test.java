package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 覆盖说明（源码行号 → 测试方法）：
 * - createRun 4 参版开头 goal 校验分支 → createRun_nullGoal_throws
 * - createRun 4 参版开头 plan 校验分支 → createRun_nullEpisodes_throws
 * - cancel 中 videoTask 状态 FAILED 处理（PENDING/PROCESSING 命中，DONE 跳过）→ cancel_failsProcessingVideoTask
 * - retryStep 中 step.getRun()==null 分支 → retryStep_nullStepRun_throws
 * - findWaitingQcStep 中 s.getAgentType()==AgentType.QC 为 false 的臂 → approve_nonQcSteps_throwsNoFinalCut
 * - planPreview 中 parsePlan(content) 为空/异常走 fallbackPlan → planPreview_nullContent_fallsBack
 * - sanitizeJson 中以 ``` 开头但找不到结尾围栏分支 → planPreview_unclosedFence_fallsBack
 * - rerun + readPlanPreview：planJson 为 blank 时走单集回退 → rerun_blankPlanJson_fallsBackToSingleEpisode
 * - readPlanPreview：episodes 字段缺失时走单集回退 → rerun_episodesMissing_fallsBack
 * - readPlanPreview：episodes 字段不是数组时走单集回退 → rerun_episodesNotArray_fallsBack
 * - readStepLog 开头 stepId==null 校验分支 → readStepLog_nullStepId_throws
 * - stats 中 removeIf 过滤 projectId==null 的 run → stats_skipsNullProjectIdRun
 * - stats 中 ownedProjectIds 过滤 id==null 的项目 → stats_skipsNullIdProject
 * - stats 中 durationCount 累加（createdAt/updatedAt 均非 null）→ stats_countsDurationWhenTimestampsPresent
 * - DramaProject.prePersist ownerId 非空臂 → dramaProject_prePersist_keepsExistingOwner
 * - VideoTask.prePersist attempts 非空臂 → videoTask_prePersist_keepsExistingAttempts
 * - FinalCut.onCreate qcStatus 非空臂 → finalCut_onCreate_keepsExistingQcStatus
 *
 * 诚实跳过清单：
 * - approve 里 `if (qcStep != null)` 的 null 臂（两处）：findFinalCutId 与 approve 调的是同一个 findWaitingQcStep，
 *   生产上两次调用返回一致；findFinalCutId 非 null 则 qcStep 必非 null，此臂生产不可达。
 */
class RunServiceBranch2Test {

    private RunRepository runRepository;
    private AgentStepRepository agentStepRepository;
    private EpisodeRepository episodeRepository;
    private FinalCutRepository finalCutRepository;
    private VideoTaskRepository videoTaskRepository;
    private LlmScriptService llmScriptService;
    private ProjectService projectService;
    private EpisodeService episodeService;
    private FinalCutService finalCutService;
    private RunLogService runLogService;
    private CurrentUser currentUser;
    private DramaProjectRepository projectRepository;

    private RunService runService;

    @BeforeEach
    void setUp() {
        runRepository = Mockito.mock(RunRepository.class);
        agentStepRepository = Mockito.mock(AgentStepRepository.class);
        episodeRepository = Mockito.mock(EpisodeRepository.class);
        finalCutRepository = Mockito.mock(FinalCutRepository.class);
        videoTaskRepository = Mockito.mock(VideoTaskRepository.class);
        llmScriptService = Mockito.mock(LlmScriptService.class);
        projectService = Mockito.mock(ProjectService.class);
        episodeService = Mockito.mock(EpisodeService.class);
        finalCutService = Mockito.mock(FinalCutService.class);
        runLogService = Mockito.mock(RunLogService.class);
        currentUser = Mockito.mock(CurrentUser.class);
        projectRepository = Mockito.mock(DramaProjectRepository.class);

        runService = new RunService(
                runRepository,
                agentStepRepository,
                episodeRepository,
                finalCutRepository,
                videoTaskRepository,
                llmScriptService,
                projectService,
                episodeService,
                finalCutService,
                runLogService,
                new ObjectMapper(),
                "Deepseek-v4-flash",
                currentUser,
                projectRepository);
    }

    private Run runningRun(Long id) {
        Run run = new Run();
        run.setId(id);
        run.setGoal("做一部 2 集短剧");
        run.setStatus(RunStatus.RUNNING);
        return run;
    }

    @Test
    void createRun_nullGoal_throws() {
        Records.PlanPreview plan = new Records.PlanPreview(
                "g", List.of(new Records.PlanEpisode(1, "t", "o")), false);
        assertThatThrownBy(() -> runService.createRun(null, plan, null, null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("目标不能为空");
    }

    @Test
    void createRun_nullEpisodes_throws() {
        Records.PlanPreview plan = new Records.PlanPreview("g", null, false);
        assertThatThrownBy(() -> runService.createRun("g", plan, null, null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("计划不能为空");
    }

    @Test
    void cancel_failsProcessingVideoTask() {
        Run run = runningRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep step = new AgentStep();
        step.setId(11L);
        step.setStatus(AgentStepStatus.PENDING);
        step.setEpisodeId(7L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(step));

        VideoTask pendingTask = new VideoTask();
        pendingTask.setId(100L);
        pendingTask.setStatus(VideoTaskStatus.PENDING);
        VideoTask processingTask = new VideoTask();
        processingTask.setId(101L);
        processingTask.setStatus(VideoTaskStatus.PROCESSING);
        VideoTask doneTask = new VideoTask();
        doneTask.setId(102L);
        doneTask.setStatus(VideoTaskStatus.DONE);
        when(videoTaskRepository.findByEpisodeId(7L))
                .thenReturn(List.of(pendingTask, processingTask, doneTask));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.cancel(1L);

        assertThat(pendingTask.getStatus()).isEqualTo(VideoTaskStatus.FAILED);
        assertThat(pendingTask.getErrorMessage()).isEqualTo("运行已取消");
        assertThat(processingTask.getStatus()).isEqualTo(VideoTaskStatus.FAILED);
        assertThat(processingTask.getErrorMessage()).isEqualTo("运行已取消");
        assertThat(doneTask.getStatus()).isEqualTo(VideoTaskStatus.DONE);
        verify(videoTaskRepository, times(2)).save(any(VideoTask.class));
        assertThat(run.getStatus()).isEqualTo(RunStatus.CANCELLED);
    }

    @Test
    void retryStep_nullStepRun_throws() {
        Run run = runningRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep step = new AgentStep();
        step.setId(5L);
        when(agentStepRepository.findById(5L)).thenReturn(Optional.of(step));

        assertThatThrownBy(() -> runService.retryStep(1L, 5L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("步骤不属于该运行");
    }

    @Test
    void approve_nonQcSteps_throwsNoFinalCut() {
        Run run = new Run();
        run.setId(1L);
        run.setStatus(RunStatus.WAITING_APPROVAL);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep scriptStep = new AgentStep();
        scriptStep.setId(9L);
        scriptStep.setAgentType(AgentType.SCRIPT);
        scriptStep.setStatus(AgentStepStatus.RUNNING);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(scriptStep));

        assertThatThrownBy(() -> runService.approve(1L, true, "ok"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("运行无关联成片");
    }

    @Test
    void planPreview_nullContent_fallsBack() {
        when(llmScriptService.callModel(any())).thenReturn(null);

        Records.PlanPreview p = runService.planPreview("做一部短剧");

        assertThat(p.fallback()).isTrue();
        assertThat(p.episodes()).isNotEmpty();
    }

    @Test
    void planPreview_unclosedFence_fallsBack() {
        String content = "```json\n{\"episodes\": []}";
        when(llmScriptService.callModel(any())).thenReturn(content);

        Records.PlanPreview p = runService.planPreview("做一部短剧");

        assertThat(p.fallback()).isTrue();
    }

    @Test
    void rerun_blankPlanJson_fallsBackToSingleEpisode() {
        Run old = new Run();
        old.setId(33L);
        old.setGoal("旧目标");
        old.setStatus(RunStatus.SUCCEEDED);
        old.setPlanJson(" ");
        when(runRepository.findById(33L)).thenReturn(Optional.of(old));

        Records.ProjectResponse projectResponse =
                new Records.ProjectResponse(10L, "t", null, null, null, null, 0L, 0L, null, null, null);
        when(projectService.create(any(Records.ProjectRequest.class))).thenReturn(projectResponse);
        Records.EpisodeResponse episodeResponse =
                new Records.EpisodeResponse(20L, 10L, 1, "t", "o", null, null, 0L, null, null);
        when(episodeService.create(eq(10L), any(Records.EpisodeRequest.class))).thenReturn(episodeResponse);
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.rerun(33L, null);

        verify(episodeService, times(1)).create(eq(10L), any(Records.EpisodeRequest.class));
    }

    @Test
    void rerun_episodesMissing_fallsBack() {
        Run old = new Run();
        old.setId(33L);
        old.setGoal("旧目标");
        old.setStatus(RunStatus.SUCCEEDED);
        old.setPlanJson("{\"x\": 1}");
        when(runRepository.findById(33L)).thenReturn(Optional.of(old));

        Records.ProjectResponse projectResponse =
                new Records.ProjectResponse(10L, "t", null, null, null, null, 0L, 0L, null, null, null);
        when(projectService.create(any(Records.ProjectRequest.class))).thenReturn(projectResponse);
        Records.EpisodeResponse episodeResponse =
                new Records.EpisodeResponse(20L, 10L, 1, "t", "o", null, null, 0L, null, null);
        when(episodeService.create(eq(10L), any(Records.EpisodeRequest.class))).thenReturn(episodeResponse);
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.rerun(33L, null);

        verify(episodeService, times(1)).create(eq(10L), any(Records.EpisodeRequest.class));
    }

    @Test
    void rerun_episodesNotArray_fallsBack() {
        Run old = new Run();
        old.setId(33L);
        old.setGoal("旧目标");
        old.setStatus(RunStatus.SUCCEEDED);
        old.setPlanJson("{\"episodes\": {}}");
        when(runRepository.findById(33L)).thenReturn(Optional.of(old));

        Records.ProjectResponse projectResponse =
                new Records.ProjectResponse(10L, "t", null, null, null, null, 0L, 0L, null, null, null);
        when(projectService.create(any(Records.ProjectRequest.class))).thenReturn(projectResponse);
        Records.EpisodeResponse episodeResponse =
                new Records.EpisodeResponse(20L, 10L, 1, "t", "o", null, null, 0L, null, null);
        when(episodeService.create(eq(10L), any(Records.EpisodeRequest.class))).thenReturn(episodeResponse);
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.rerun(33L, null);

        verify(episodeService, times(1)).create(eq(10L), any(Records.EpisodeRequest.class));
    }

    @Test
    void readStepLog_nullStepId_throws() {
        assertThatThrownBy(() -> runService.readStepLog(1L, null, 0))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("stepId 不能为空");
    }

    @Test
    void stats_skipsNullProjectIdRun() {
        when(currentUser.currentUserId()).thenReturn("u1");

        DramaProject project = new DramaProject();
        project.setId(5L);
        project.setOwnerId("u1");
        when(projectRepository.findByOwnerId(eq("u1"), any(Sort.class)))
                .thenReturn(List.of(project));

        Run nullProjectRun = new Run();
        nullProjectRun.setId(1L);
        nullProjectRun.setStatus(RunStatus.SUCCEEDED);
        nullProjectRun.setProjectId(null);
        Run ownedRun = new Run();
        ownedRun.setId(2L);
        ownedRun.setStatus(RunStatus.SUCCEEDED);
        ownedRun.setProjectId(5L);
        when(runRepository.findAll()).thenReturn(List.of(nullProjectRun, ownedRun));

        Records.RunStatsResponse stats = runService.stats();

        assertThat(stats.totalRuns()).isEqualTo(1L);
    }

    @Test
    void stats_skipsNullIdProject() {
        when(currentUser.currentUserId()).thenReturn("u1");

        when(projectRepository.findByOwnerId(eq("u1"), any(Sort.class)))
                .thenReturn(List.of(new DramaProject()));

        Run run = new Run();
        run.setId(2L);
        run.setStatus(RunStatus.SUCCEEDED);
        run.setProjectId(5L);
        when(runRepository.findAll()).thenReturn(List.of(run));

        Records.RunStatsResponse stats = runService.stats();

        assertThat(stats.totalRuns()).isEqualTo(0L);
    }

    @Test
    void stats_countsDurationWhenTimestampsPresent() {
        when(currentUser.currentUserId()).thenReturn("u1");

        DramaProject project = new DramaProject();
        project.setId(5L);
        project.setOwnerId("u1");
        when(projectRepository.findByOwnerId(eq("u1"), any(Sort.class)))
                .thenReturn(List.of(project));

        Run run = new Run();
        run.setId(2L);
        run.setStatus(RunStatus.SUCCEEDED);
        run.setProjectId(5L);
        run.setCreatedAt(LocalDateTime.of(2026, 1, 1, 0, 0, 0));
        run.setUpdatedAt(LocalDateTime.of(2026, 1, 1, 0, 0, 10));
        when(runRepository.findAll()).thenReturn(List.of(run));

        Records.RunStatsResponse stats = runService.stats();

        assertThat(stats.avgDurationMs()).isEqualTo(10000L);
    }

    @Test
    void dramaProject_prePersist_keepsExistingOwner() {
        DramaProject p = new DramaProject();
        p.setOwnerId("u1");

        p.prePersist();

        assertThat(p.getOwnerId()).isEqualTo("u1");
    }

    @Test
    void videoTask_prePersist_keepsExistingAttempts() {
        VideoTask t = new VideoTask();
        t.setAttempts(3);

        t.prePersist();

        assertThat(t.getAttempts()).isEqualTo(3);
    }

    @Test
    void finalCut_onCreate_keepsExistingQcStatus() {
        FinalCut fc = new FinalCut();
        fc.setQcStatus("APPROVED");

        fc.onCreate();

        assertThat(fc.getQcStatus()).isEqualTo("APPROVED");
    }
}
