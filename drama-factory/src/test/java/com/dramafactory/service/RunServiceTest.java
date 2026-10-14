package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.dto.Records;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.VideoTask;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Sort;
import org.mockito.ArgumentCaptor;

import java.util.Collections;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.ProjectStatus;



/**
 * RunService 单元测试（Mockito，不启动 Spring 容器）。
 */
class RunServiceTest {

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
        runRepository = mock(RunRepository.class);
        agentStepRepository = mock(AgentStepRepository.class);
        episodeRepository = mock(EpisodeRepository.class);
        finalCutRepository = mock(FinalCutRepository.class);
        videoTaskRepository = mock(VideoTaskRepository.class);
        llmScriptService = mock(LlmScriptService.class);
        projectService = mock(ProjectService.class);
        episodeService = mock(EpisodeService.class);
        finalCutService = mock(FinalCutService.class);
        runLogService = mock(RunLogService.class);
        currentUser = mock(CurrentUser.class);
        projectRepository = mock(DramaProjectRepository.class);
        runService = new RunService(runRepository, agentStepRepository, episodeRepository,
                finalCutRepository, videoTaskRepository, llmScriptService, projectService,
                episodeService, finalCutService, runLogService, new ObjectMapper(), "Deepseek-v4-flash",
                currentUser, projectRepository);
    }

    private Run runningRun(long id) {
        Run run = new Run();
        run.setId(id);
        run.setGoal("做一部 2 集短剧");
        run.setStatus(RunStatus.RUNNING);
        return run;
    }

    @Test
    void planPreviewShouldRejectBlankGoal() {
        assertThatThrownBy(() -> runService.planPreview("   "))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void planPreviewShouldFallbackWhenLlmFails() {
        when(llmScriptService.callModel(any())).thenThrow(new RuntimeException("no network"));

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧，题材都市情感");

        assertThat(preview.fallback()).isTrue();
        assertThat(preview.episodes()).hasSize(2);
        assertThat(preview.episodes().get(0).title()).isEqualTo("第 1 集");
    }

    @Test
    void planPreviewShouldTruncateToSixEpisodes() {
        when(llmScriptService.callModel(any())).thenThrow(new RuntimeException("no network"));

        Records.PlanPreview preview = runService.planPreview("做一部 8 集短剧");

        assertThat(preview.episodes()).hasSize(6);
    }

    @Test
    void planPreviewShouldParseModelJson() {
        String json = "{\"episodes\":[{\"episodeNo\":1,\"title\":\"重逢\",\"outline\":\"地铁重逢\"},"
                + "{\"episodeNo\":2,\"title\":\"告白\",\"outline\":\"天台告白\"}]}";
        when(llmScriptService.callModel(any())).thenReturn("```json\n" + json + "\n```");

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧");

        assertThat(preview.fallback()).isFalse();
        assertThat(preview.episodes()).hasSize(2);
        assertThat(preview.episodes().get(0).title()).isEqualTo("重逢");
    }

    @Test
    void pauseShouldRejectNonRunning() {
        Run run = runningRun(1L);
        run.setStatus(RunStatus.SUCCEEDED);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        assertThatThrownBy(() -> runService.pause(1L))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void pauseShouldSetPaused() {
        Run run = runningRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.pause(1L);

        ArgumentCaptor<Run> captor = ArgumentCaptor.forClass(Run.class);
        verify(runRepository).save(captor.capture());
        assertThat(captor.getValue().getStatus()).isEqualTo(RunStatus.PAUSED);
    }

    @Test
    void cancelShouldMarkPendingStepsCancelledAndFailVideoTasks() {
        Run run = runningRun(2L);
        when(runRepository.findById(2L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        AgentStep pending = new AgentStep();
        pending.setId(21L);
        pending.setStatus(AgentStepStatus.PENDING);
        pending.setEpisodeId(100L);
        AgentStep done = new AgentStep();
        done.setId(22L);
        done.setStatus(AgentStepStatus.SUCCEEDED);
        done.setEpisodeId(100L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(2L))
                .thenReturn(List.of(pending, done));

        VideoTask task = new VideoTask();
        task.setId(301L);
        task.setStatus(com.dramafactory.model.VideoTaskStatus.PROCESSING);
        when(videoTaskRepository.findByEpisodeId(100L)).thenReturn(List.of(task));
        when(videoTaskRepository.save(any(VideoTask.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.cancel(2L);

        assertThat(pending.getStatus()).isEqualTo(AgentStepStatus.CANCELLED);
        assertThat(done.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(task.getStatus()).isEqualTo(com.dramafactory.model.VideoTaskStatus.FAILED);
        assertThat(task.getErrorMessage()).isEqualTo("运行已取消");
        ArgumentCaptor<Run> captor = ArgumentCaptor.forClass(Run.class);
        verify(runRepository).save(captor.capture());
        assertThat(captor.getValue().getStatus()).isEqualTo(RunStatus.CANCELLED);
    }

    @Test
    void cancelShouldRejectTerminalRun() {
        Run run = runningRun(3L);
        run.setStatus(RunStatus.SUCCEEDED);
        when(runRepository.findById(3L)).thenReturn(Optional.of(run));

        assertThatThrownBy(() -> runService.cancel(3L))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void retryStepShouldResetToPendingAndReopenFailedRun() {
        Run run = runningRun(4L);
        run.setStatus(RunStatus.FAILED);
        AgentStep step = new AgentStep();
        step.setId(40L);
        step.setRun(run);
        step.setStatus(AgentStepStatus.FAILED);
        step.setErrorMessage("boom");
        when(runRepository.findById(4L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findById(40L)).thenReturn(Optional.of(step));

        runService.retryStep(4L, 40L);

        assertThat(step.getStatus()).isEqualTo(AgentStepStatus.PENDING);
        assertThat(step.getErrorMessage()).isNull();
        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
    }

    @Test
    void retryStepShouldRejectForeignStep() {
        Run run = runningRun(5L);
        AgentStep step = new AgentStep();
        step.setId(50L);
        Run other = runningRun(6L);
        step.setRun(other);
        when(runRepository.findById(5L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findById(50L)).thenReturn(Optional.of(step));

        assertThatThrownBy(() -> runService.retryStep(5L, 50L))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void createRunShouldRejectEmptyPlan() {
        Records.PlanPreview plan = new Records.PlanPreview("goal", Collections.emptyList(), false);

        assertThatThrownBy(() -> runService.createRun("做一部短剧", plan))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rerunShouldRejectNonTerminalRun() {
        Run run = runningRun(7L);
        when(runRepository.findById(7L)).thenReturn(Optional.of(run));

        assertThatThrownBy(() -> runService.rerun(7L, null))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void readStepLogShouldRejectForeignStep() {
        Run run = runningRun(8L);
        AgentStep step = new AgentStep();
        step.setId(80L);
        step.setSeqNo(3);
        step.setRun(run);
        when(agentStepRepository.findById(80L)).thenReturn(Optional.of(step));

        assertThatThrownBy(() -> runService.readStepLog(999L, 80L, 0))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void statsShouldComputeSuccessRate() {
        // 新口径：只统计当前用户名下项目的 run
        when(currentUser.currentUserId()).thenReturn("u1");
        DramaProject owned = new DramaProject();
        owned.setId(5L);
        when(projectRepository.findByOwnerId(eq("u1"), any(Sort.class))).thenReturn(List.of(owned));

        Run ok = runningRun(11L);
        ok.setStatus(RunStatus.SUCCEEDED);
        ok.setProjectId(5L);
        Run bad = runningRun(12L);
        bad.setStatus(RunStatus.FAILED);
        bad.setProjectId(5L);
        Run others = runningRun(13L);
        others.setStatus(RunStatus.SUCCEEDED);
        others.setProjectId(9L);
        when(runRepository.findAll()).thenReturn(List.of(ok, bad, others));

        Records.RunStatsResponse stats = runService.stats();

        assertThat(stats.totalRuns()).isEqualTo(2);
        assertThat(stats.succeeded()).isEqualTo(1);
        assertThat(stats.failed()).isEqualTo(1);
        assertThat(stats.successRate()).isEqualTo(0.5);
    }

    @Test
    void toDetailResponseShouldMapLabels() {
        Run run = runningRun(13L);
        AgentStep step = new AgentStep();
        step.setId(130L);
        step.setSeqNo(1);
        step.setAgentType(AgentType.SCRIPT);
        step.setName("第 1 集 · 编剧");
        step.setStatus(AgentStepStatus.SUCCEEDED);

        Records.RunDetailResponse detail = RunService.toDetailResponse(run, List.of(step));

        assertThat(detail.run().statusLabel()).isEqualTo("执行中");
        assertThat(detail.steps()).hasSize(1);
        assertThat(detail.steps().get(0).agentLabel()).isEqualTo("编剧");
        assertThat(detail.projectId()).isNull();
    }

    @Test
    void planPreviewShouldRejectNullGoal() {
        assertThatThrownBy(() -> runService.planPreview(null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void planPreviewShouldFallbackWhenEpisodeCountOverflows() {
        when(llmScriptService.callModel(any())).thenThrow(new RuntimeException("no network"));

        Records.PlanPreview preview = runService.planPreview("做一部 99999999999999 集短剧");

        assertThat(preview.fallback()).isTrue();
        assertThat(preview.episodes()).hasSize(1);
    }

    @Test
    void planPreviewShouldFallbackWhenModelReturnsEmptyObject() {
        when(llmScriptService.callModel(any())).thenReturn("{}");

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧");

        assertThat(preview.fallback()).isTrue();
        assertThat(preview.episodes()).hasSize(2);
    }

    @Test
    void planPreviewShouldFallbackWhenModelReturnsGarbage() {
        when(llmScriptService.callModel(any())).thenReturn("not json at all");

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧");

        assertThat(preview.fallback()).isTrue();
    }

    @Test
    void planPreviewShouldTruncateModelEpisodesToRequested() {
        String json = "{\"episodes\":[{\"episodeNo\":1,\"title\":\"t1\",\"outline\":\"o1\"},"
                + "{\"episodeNo\":2,\"title\":\"t2\",\"outline\":\"o2\"},"
                + "{\"episodeNo\":3,\"title\":\"t3\",\"outline\":\"o3\"}]}";
        when(llmScriptService.callModel(any())).thenReturn(json);

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧");

        assertThat(preview.fallback()).isFalse();
        assertThat(preview.episodes()).hasSize(2);
        assertThat(preview.episodes().get(1).title()).isEqualTo("t2");
    }

    @Test
    void planPreviewShouldDefaultBlankTitle() {
        String json = "{\"episodes\":[{\"episodeNo\":1,\"title\":\"\",\"outline\":\"x\"},"
                + "{\"episodeNo\":2,\"title\":\"b\",\"outline\":\"y\"}]}";
        when(llmScriptService.callModel(any())).thenReturn(json);

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧");

        assertThat(preview.episodes()).hasSize(2);
        assertThat(preview.episodes().get(0).title()).isEqualTo("第 1 集");
    }

    @Test
    void planPreviewShouldDefaultMissingEpisodeNo() {
        String json = "{\"episodes\":[{\"title\":\"a\",\"outline\":\"x\"}]}";
        when(llmScriptService.callModel(any())).thenReturn(json);

        Records.PlanPreview preview = runService.planPreview("做一部短剧");

        assertThat(preview.episodes()).hasSize(1);
        assertThat(preview.episodes().get(0).episodeNo()).isEqualTo(1);
    }

    @Test
    void planPreviewShouldFallbackWhenFenceHasNoNewline() {
        String json = "{\"episodes\":[{\"episodeNo\":1,\"title\":\"t1\",\"outline\":\"o1\"},"
                + "{\"episodeNo\":2,\"title\":\"t2\",\"outline\":\"o2\"}]}";
        when(llmScriptService.callModel(any())).thenReturn("```" + json);

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧");

        assertThat(preview.fallback()).isTrue();
    }

    @Test
    void planPreviewShouldFallbackWhenModelReturnsBlank() {
        when(llmScriptService.callModel(any())).thenReturn("   ");

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧");

        assertThat(preview.fallback()).isTrue();
    }

    @Test
    void planPreviewShouldFallbackWhenEpisodesNotArray() {
        when(llmScriptService.callModel(any())).thenReturn("{\"episodes\":{}}");

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧");

        assertThat(preview.fallback()).isTrue();
    }

    @Test
    void planPreviewShouldTruncateLongGoalInFallbackOutline() {
        String goal = "目".repeat(70);
        when(llmScriptService.callModel(any())).thenThrow(new RuntimeException("no network"));

        Records.PlanPreview preview = runService.planPreview(goal);

        assertThat(preview.episodes()).hasSize(1);
        assertThat(preview.episodes().get(0).outline()).contains(goal.substring(0, 60));
        assertThat(preview.episodes().get(0).outline()).doesNotContain(goal);
    }

    @Test
    void planPreviewShouldTreatZeroEpisodesAsOne() {
        when(llmScriptService.callModel(any())).thenThrow(new RuntimeException("no network"));

        Records.PlanPreview preview = runService.planPreview("做一部 0 集短剧");

        assertThat(preview.episodes()).hasSize(1);
    }

    @Test
    void createRunShouldBuildFiveStepsAndMarkRunning() {
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(projectService.create(any(Records.ProjectRequest.class)))
                .thenReturn(new Records.ProjectResponse(10L, "t", null, null, null, null, 0L, 0L, null, null, null));
        when(episodeService.create(eq(10L), any(Records.EpisodeRequest.class)))
                .thenReturn(new Records.EpisodeResponse(20L, 10L, 1, "t", "o", null, null, 0L, null, null));
        Records.PlanPreview plan = new Records.PlanPreview("做一部短剧",
                List.of(new Records.PlanEpisode(1, "t", "o")), false);

        runService.createRun("做一部短剧", plan);

        ArgumentCaptor<Records.ProjectRequest> projectCaptor =
                ArgumentCaptor.forClass(Records.ProjectRequest.class);
        verify(projectService).create(projectCaptor.capture());
        assertThat(projectCaptor.getValue().title()).isEqualTo("做一部短剧");

        verify(episodeService).create(eq(10L), any(Records.EpisodeRequest.class));

        ArgumentCaptor<AgentStep> stepCaptor = ArgumentCaptor.forClass(AgentStep.class);
        verify(agentStepRepository, times(5)).save(stepCaptor.capture());
        assertThat(stepCaptor.getAllValues())
                .extracting(AgentStep::getAgentType)
                .containsExactlyInAnyOrder(AgentType.SCRIPT, AgentType.BOARD, AgentType.VIDEO, AgentType.EDIT, AgentType.QC);

        ArgumentCaptor<Run> runCaptor = ArgumentCaptor.forClass(Run.class);
        verify(runRepository, times(3)).save(runCaptor.capture());
        assertThat(runCaptor.getValue().getStatus()).isEqualTo(RunStatus.RUNNING);
    }

    @Test
    void createRunShouldRejectBlankGoal() {
        Records.PlanPreview plan = new Records.PlanPreview("g",
                List.of(new Records.PlanEpisode(1, "t", "o")), false);

        assertThatThrownBy(() -> runService.createRun("  ", plan))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void createRunShouldRejectNullPlan() {
        assertThatThrownBy(() -> runService.createRun("做一部短剧", null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void pauseShouldThrowWhenRunMissing() {
        when(runRepository.findById(99L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> runService.pause(99L))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void resumeShouldSetRunning() {
        Run run = runningRun(1L);
        run.setStatus(RunStatus.PAUSED);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.resume(1L);

        ArgumentCaptor<Run> captor = ArgumentCaptor.forClass(Run.class);
        verify(runRepository).save(captor.capture());
        assertThat(captor.getValue().getStatus()).isEqualTo(RunStatus.RUNNING);
    }

    @Test
    void resumeShouldRejectNonPaused() {
        Run run = runningRun(1L);
        run.setStatus(RunStatus.RUNNING);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        assertThatThrownBy(() -> runService.resume(1L))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void markSucceededShouldReturnEarlyWhenNoSteps() {
        Run run = runningRun(20L);
        when(runRepository.findById(20L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(20L)).thenReturn(Collections.emptyList());

        runService.markSucceededIfAllDone(20L);

        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
        verify(runRepository, never()).save(any(Run.class));
    }

    @Test
    void markSucceededShouldReturnEarlyWhenStepRunning() {
        Run run = runningRun(21L);
        when(runRepository.findById(21L)).thenReturn(Optional.of(run));
        AgentStep ok = new AgentStep();
        ok.setStatus(AgentStepStatus.SUCCEEDED);
        AgentStep running = new AgentStep();
        running.setStatus(AgentStepStatus.RUNNING);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(21L)).thenReturn(List.of(ok, running));

        runService.markSucceededIfAllDone(21L);

        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
        verify(runRepository, never()).save(any(Run.class));
    }

    @Test
    void markSucceededShouldAggregateTotalsAndMarkSucceeded() {
        Run run = runningRun(22L);
        when(runRepository.findById(22L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        AgentStep a = new AgentStep();
        a.setStatus(AgentStepStatus.SUCCEEDED);
        a.setTokensUsed(100L);
        a.setCostCents(5L);
        AgentStep b = new AgentStep();
        b.setStatus(AgentStepStatus.SKIPPED);
        b.setTokensUsed(null);
        b.setCostCents(null);
        AgentStep c = new AgentStep();
        c.setStatus(AgentStepStatus.SUCCEEDED);
        c.setTokensUsed(50L);
        c.setCostCents(null);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(22L)).thenReturn(List.of(a, b, c));

        runService.markSucceededIfAllDone(22L);

        assertThat(run.getTotalTokens()).isEqualTo(150L);
        assertThat(run.getTotalCostCents()).isEqualTo(5L);
        assertThat(run.getStatus()).isEqualTo(RunStatus.SUCCEEDED);
        verify(runRepository, times(2)).save(any(Run.class));
    }

    @Test
    void cancelShouldAcceptWaitingApproval() {
        Run run = runningRun(23L);
        run.setStatus(RunStatus.WAITING_APPROVAL);
        when(runRepository.findById(23L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(23L)).thenReturn(Collections.emptyList());

        runService.cancel(23L);

        ArgumentCaptor<Run> captor = ArgumentCaptor.forClass(Run.class);
        verify(runRepository).save(captor.capture());
        assertThat(captor.getValue().getStatus()).isEqualTo(RunStatus.CANCELLED);
    }

    @Test
    void cancelShouldTolerateNullEpisodeId() {
        Run run = runningRun(24L);
        when(runRepository.findById(24L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        AgentStep step = new AgentStep();
        step.setId(240L);
        step.setStatus(AgentStepStatus.PENDING);
        step.setEpisodeId(null);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(24L)).thenReturn(List.of(step));
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.cancel(24L);

        assertThat(step.getStatus()).isEqualTo(AgentStepStatus.CANCELLED);
        verify(videoTaskRepository, never()).findByEpisodeId(any());
    }

    @Test
    void cancelShouldNotFailSucceededVideoTask() {
        Run run = runningRun(25L);
        when(runRepository.findById(25L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        AgentStep step = new AgentStep();
        step.setId(250L);
        step.setStatus(AgentStepStatus.SUCCEEDED);
        step.setEpisodeId(500L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(25L)).thenReturn(List.of(step));
        VideoTask done = new VideoTask();
        done.setId(501L);
        done.setStatus(com.dramafactory.model.VideoTaskStatus.DONE);
        when(videoTaskRepository.findByEpisodeId(500L)).thenReturn(List.of(done));

        runService.cancel(25L);

        assertThat(done.getStatus()).isEqualTo(com.dramafactory.model.VideoTaskStatus.DONE);
        verify(videoTaskRepository, never()).save(any(VideoTask.class));
    }

    @Test
    void rerunShouldUseOldGoalWhenOverrideNull() {
        Run run = runningRun(30L);
        run.setStatus(RunStatus.SUCCEEDED);
        run.setPlanJson("{\"goal\":\"旧目标\",\"fallback\":false,\"episodes\":[{\"episodeNo\":1,\"title\":\"t\",\"outline\":\"o\"}]}");
        when(runRepository.findById(30L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(projectService.create(any(Records.ProjectRequest.class)))
                .thenReturn(new Records.ProjectResponse(10L, "t", null, null, null, null, 0L, 0L, null, null, null));
        when(episodeService.create(eq(10L), any(Records.EpisodeRequest.class)))
                .thenReturn(new Records.EpisodeResponse(20L, 10L, 1, "t", "o", null, null, 0L, null, null));

        runService.rerun(30L, null);

        ArgumentCaptor<Run> runCaptor = ArgumentCaptor.forClass(Run.class);
        verify(runRepository, times(3)).save(runCaptor.capture());
        assertThat(runCaptor.getAllValues().get(0).getGoal()).isEqualTo("做一部 2 集短剧");
    }

    @Test
    void rerunShouldUseOldGoalWhenOverrideBlank() {
        Run run = runningRun(31L);
        run.setStatus(RunStatus.SUCCEEDED);
        run.setPlanJson("{\"goal\":\"旧目标\",\"fallback\":false,\"episodes\":[{\"episodeNo\":1,\"title\":\"t\",\"outline\":\"o\"}]}");
        when(runRepository.findById(31L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(projectService.create(any(Records.ProjectRequest.class)))
                .thenReturn(new Records.ProjectResponse(10L, "t", null, null, null, null, 0L, 0L, null, null, null));
        when(episodeService.create(eq(10L), any(Records.EpisodeRequest.class)))
                .thenReturn(new Records.EpisodeResponse(20L, 10L, 1, "t", "o", null, null, 0L, null, null));

        runService.rerun(31L, "   ");

        ArgumentCaptor<Run> runCaptor = ArgumentCaptor.forClass(Run.class);
        verify(runRepository, times(3)).save(runCaptor.capture());
        assertThat(runCaptor.getAllValues().get(0).getGoal()).isEqualTo("做一部 2 集短剧");
    }

    @Test
    void rerunShouldParsePlanJsonForFailedRun() {
        Run run = runningRun(32L);
        run.setStatus(RunStatus.FAILED);
        run.setPlanJson("{\"goal\":\"旧目标\",\"fallback\":false,\"episodes\":["
                + "{\"episodeNo\":1,\"title\":\"a\",\"outline\":\"x\"},"
                + "{\"episodeNo\":2,\"title\":\"b\",\"outline\":\"y\"}]}");
        when(runRepository.findById(32L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(projectService.create(any(Records.ProjectRequest.class)))
                .thenReturn(new Records.ProjectResponse(10L, "t", null, null, null, null, 0L, 0L, null, null, null));
        when(episodeService.create(eq(10L), any(Records.EpisodeRequest.class)))
                .thenReturn(new Records.EpisodeResponse(20L, 10L, 1, "t", "o", null, null, 0L, null, null));

        runService.rerun(32L, "新目标");

        verify(episodeService, times(2)).create(eq(10L), any(Records.EpisodeRequest.class));
        verify(agentStepRepository, times(10)).save(any(AgentStep.class));
    }

    @Test
    void rerunShouldFallbackSingleEpisodeWhenPlanJsonNull() {
        Run run = runningRun(33L);
        run.setStatus(RunStatus.SUCCEEDED);
        run.setPlanJson(null);
        when(runRepository.findById(33L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(projectService.create(any(Records.ProjectRequest.class)))
                .thenReturn(new Records.ProjectResponse(10L, "t", null, null, null, null, 0L, 0L, null, null, null));
        when(episodeService.create(eq(10L), any(Records.EpisodeRequest.class)))
                .thenReturn(new Records.EpisodeResponse(20L, 10L, 1, "t", "o", null, null, 0L, null, null));

        runService.rerun(33L, null);

        verify(episodeService, times(1)).create(eq(10L), any(Records.EpisodeRequest.class));
    }

    @Test
    void rerunShouldFallbackSingleEpisodeWhenPlanJsonInvalid() {
        Run run = runningRun(34L);
        run.setStatus(RunStatus.SUCCEEDED);
        run.setPlanJson("not json at all");
        when(runRepository.findById(34L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(projectService.create(any(Records.ProjectRequest.class)))
                .thenReturn(new Records.ProjectResponse(10L, "t", null, null, null, null, 0L, 0L, null, null, null));
        when(episodeService.create(eq(10L), any(Records.EpisodeRequest.class)))
                .thenReturn(new Records.EpisodeResponse(20L, 10L, 1, "t", "o", null, null, 0L, null, null));

        runService.rerun(34L, null);

        verify(episodeService, times(1)).create(eq(10L), any(Records.EpisodeRequest.class));
    }

    @Test
    void approveShouldPassWhenRunningQcStepExists() {
        Run run = runningRun(40L);
        run.setStatus(RunStatus.WAITING_APPROVAL);
        when(runRepository.findById(40L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        AgentStep qc = new AgentStep();
        qc.setId(400L);
        qc.setAgentType(AgentType.QC);
        qc.setStatus(AgentStepStatus.RUNNING);
        qc.setEpisodeId(50L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(40L)).thenReturn(List.of(qc));
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));

        com.dramafactory.model.FinalCut fc = new com.dramafactory.model.FinalCut();
        fc.setId(700L);
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(50L)).thenReturn(Optional.of(fc));

        runService.approve(40L, true, "ok");

        verify(finalCutService).qc(eq(700L), any(Records.QcRequest.class));
        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
    }

    @Test
    void approveShouldFailWhenOnlyPendingQcStep() {
        Run run = runningRun(41L);
        run.setStatus(RunStatus.WAITING_APPROVAL);
        when(runRepository.findById(41L)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        AgentStep qc = new AgentStep();
        qc.setId(410L);
        qc.setAgentType(AgentType.QC);
        qc.setStatus(AgentStepStatus.PENDING);
        qc.setEpisodeId(51L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(41L)).thenReturn(List.of(qc));
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));

        com.dramafactory.model.FinalCut fc = new com.dramafactory.model.FinalCut();
        fc.setId(701L);
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(51L)).thenReturn(Optional.of(fc));

        runService.approve(41L, false, "不行");

        verify(finalCutService).qc(eq(701L), any(Records.QcRequest.class));
        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(qc.getErrorMessage()).isEqualTo("不行");
        assertThat(run.getStatus()).isEqualTo(RunStatus.FAILED);
    }

    @Test
    void approveShouldThrowWhenNoQcStep() {
        Run run = runningRun(42L);
        run.setStatus(RunStatus.WAITING_APPROVAL);
        when(runRepository.findById(42L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(42L)).thenReturn(Collections.emptyList());

        assertThatThrownBy(() -> runService.approve(42L, true, "ok"))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void retryStepShouldResetButKeepSucceededRunStatus() {
        Run run = runningRun(43L);
        run.setStatus(RunStatus.SUCCEEDED);
        AgentStep step = new AgentStep();
        step.setId(430L);
        step.setRun(run);
        step.setStatus(AgentStepStatus.SUCCEEDED);
        when(runRepository.findById(43L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findById(430L)).thenReturn(Optional.of(step));
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.retryStep(43L, 430L);

        assertThat(step.getStatus()).isEqualTo(AgentStepStatus.PENDING);
        assertThat(run.getStatus()).isEqualTo(RunStatus.SUCCEEDED);
        verify(runRepository, never()).save(any(Run.class));
    }

    @Test
    void requireRunShouldRejectNullId() {
        assertThatThrownBy(() -> runService.pause(null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void toRunResponseShouldHandleNullStatus() {
        Run run = new Run();
        run.setId(50L);
        run.setGoal("g");
        run.setStatus(null);

        Records.RunResponse resp = RunService.toRunResponse(run);

        assertThat(resp.status()).isNull();
        assertThat(resp.statusLabel()).isNull();
    }

    @Test
    void toStepResponseShouldHandleNullLabels() {
        AgentStep step = new AgentStep();
        step.setId(60L);
        step.setSeqNo(1);
        step.setAgentType(null);
        step.setStatus(null);

        Records.AgentStepResponse resp = RunService.toStepResponse(step);

        assertThat(resp.agentLabel()).isNull();
        assertThat(resp.statusLabel()).isNull();
    }

    @Test
    void toDetailResponseShouldHandleNullSteps() {
        Run run = runningRun(51L);

        Records.RunDetailResponse detail = RunService.toDetailResponse(run, null);

        assertThat(detail.steps()).isEmpty();
    }

    @Test
    void statsShouldReturnZeroWhenNoOwnedProjects() {
        when(currentUser.currentUserId()).thenReturn("u1");
        when(projectRepository.findByOwnerId(eq("u1"), any(Sort.class))).thenReturn(Collections.emptyList());
        when(runRepository.findAll()).thenReturn(Collections.emptyList());

        Records.RunStatsResponse stats = runService.stats();

        assertThat(stats.totalRuns()).isEqualTo(0);
        assertThat(stats.successRate()).isEqualTo(0.0);
    }

    @Test
    void planPreviewShouldFallbackWhenBracesInverted() {
        when(llmScriptService.callModel(any())).thenReturn("}{");

        Records.PlanPreview preview = runService.planPreview("做一部 2 集短剧");

        assertThat(preview.fallback()).isTrue();
        assertThat(preview.episodes()).hasSize(2);
    }
}
