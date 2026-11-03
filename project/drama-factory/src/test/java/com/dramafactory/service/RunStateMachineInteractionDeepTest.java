package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RunStateMachineInteractionDeepTest {

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
    private DramaProjectRepository projectRepository;
    private CurrentUser currentUser;

    private RunService runService;
    private RunExecutor runExecutor;

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
        projectRepository = mock(DramaProjectRepository.class);
        currentUser = mock(CurrentUser.class);

        runService = new RunService(runRepository, agentStepRepository, episodeRepository,
                finalCutRepository, videoTaskRepository, llmScriptService, projectService,
                episodeService, finalCutService, runLogService, new ObjectMapper(), "Deepseek-v4-flash",
                currentUser, projectRepository);

        ScriptService scriptService = mock(ScriptService.class);
        ScriptSplitterService scriptSplitterService = mock(ScriptSplitterService.class);
        VideoTaskService videoTaskService = mock(VideoTaskService.class);
        org.springframework.core.env.Environment environment = mock(org.springframework.core.env.Environment.class);
        SkillService skillService = mock(SkillService.class);
        ReviewService reviewService = mock(ReviewService.class);

        runExecutor = new RunExecutor(runRepository, agentStepRepository, videoTaskRepository,
                scriptService, scriptSplitterService, videoTaskService, finalCutService,
                runLogService, environment, new ObjectMapper(), skillService, reviewService);
    }

    private Run run(Long id, RunStatus status) {
        Run run = new Run();
        run.setId(id);
        run.setGoal("goal-" + id);
        run.setStatus(status);
        return run;
    }

    private AgentStep step(Long id, Long episodeId, AgentStepStatus status) {
        AgentStep step = new AgentStep();
        step.setId(id);
        step.setStatus(status);
        step.setEpisodeId(episodeId);
        return step;
    }

    private VideoTask videoTask(Long id, VideoTaskStatus status) {
        VideoTask task = new VideoTask();
        task.setId(id);
        task.setStatus(status);
        return task;
    }

    @Test
    void tick_skipsPausedRun() {
        when(runRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING))
                .thenReturn(Collections.emptyList());

        runExecutor.tick();

        verify(agentStepRepository, never()).findByRunIdOrderBySeqNoAsc(any());
    }

    @Test
    void tick_skipsWaitingApprovalRun() {
        when(runRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING))
                .thenReturn(Collections.emptyList());

        runExecutor.tick();

        verify(agentStepRepository, never()).findByRunIdOrderBySeqNoAsc(any());
    }

    @Test
    void tick_advancesOnlyRunningRun() {
        Run running = run(1L, RunStatus.RUNNING);
        when(runRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING))
                .thenReturn(new ArrayList<>(List.of(running)));
        when(runRepository.findById(1L)).thenReturn(Optional.of(running));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(Collections.emptyList());
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runExecutor.tick();

        ArgumentCaptor<Run> captor = ArgumentCaptor.forClass(Run.class);
        verify(runRepository).save(captor.capture());
        assertThat(captor.getValue().getStatus()).isEqualTo(RunStatus.SUCCEEDED);
    }

    @Test
    void cancel_keepsRunningStepUntouched() {
        Run running = run(1L, RunStatus.RUNNING);
        when(runRepository.findById(1L)).thenReturn(Optional.of(running));

        AgentStep runningStep = step(10L, 100L, AgentStepStatus.RUNNING);
        AgentStep pendingStep = step(11L, 100L, AgentStepStatus.PENDING);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L))
                .thenReturn(new ArrayList<>(List.of(runningStep, pendingStep)));
        when(videoTaskRepository.findByEpisodeId(100L)).thenReturn(Collections.emptyList());
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.cancel(1L);

        assertThat(runningStep.getStatus()).isEqualTo(AgentStepStatus.RUNNING);
        assertThat(pendingStep.getStatus()).isEqualTo(AgentStepStatus.CANCELLED);
        assertThat(running.getStatus()).isEqualTo(RunStatus.CANCELLED);
    }

    @Test
    void cancel_onSucceededRun_throwsAndLeavesUnchanged() {
        Run succeeded = run(1L, RunStatus.SUCCEEDED);
        when(runRepository.findById(1L)).thenReturn(Optional.of(succeeded));

        assertThatThrownBy(() -> runService.cancel(1L))
                .isInstanceOf(IllegalStateException.class);

        assertThat(succeeded.getStatus()).isEqualTo(RunStatus.SUCCEEDED);
        verify(agentStepRepository, never()).findByRunIdOrderBySeqNoAsc(any());
    }

    @Test
    void cancel_cleansAllPendingVideoTasksAcrossEpisodes() {
        Run running = run(1L, RunStatus.RUNNING);
        when(runRepository.findById(1L)).thenReturn(Optional.of(running));

        AgentStep stepA = step(10L, 100L, AgentStepStatus.PENDING);
        AgentStep stepB = step(11L, 200L, AgentStepStatus.PENDING);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L))
                .thenReturn(new ArrayList<>(List.of(stepA, stepB)));

        VideoTask pendingTask = videoTask(1000L, VideoTaskStatus.PENDING);
        VideoTask processingTask = videoTask(1001L, VideoTaskStatus.PROCESSING);
        when(videoTaskRepository.findByEpisodeId(100L))
                .thenReturn(new ArrayList<>(List.of(pendingTask, processingTask)));

        VideoTask doneTask = videoTask(2000L, VideoTaskStatus.DONE);
        when(videoTaskRepository.findByEpisodeId(200L))
                .thenReturn(new ArrayList<>(List.of(doneTask)));

        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.cancel(1L);

        assertThat(pendingTask.getStatus()).isEqualTo(VideoTaskStatus.FAILED);
        assertThat(pendingTask.getErrorMessage()).isEqualTo("运行已取消");
        assertThat(processingTask.getStatus()).isEqualTo(VideoTaskStatus.FAILED);
        assertThat(processingTask.getErrorMessage()).isEqualTo("运行已取消");
        assertThat(doneTask.getStatus()).isEqualTo(VideoTaskStatus.DONE);
    }

    @Test
    void retryStep_onWaitingApproval_keepsWaitingApproval() {
        Run run = run(1L, RunStatus.WAITING_APPROVAL);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep step = step(10L, 100L, AgentStepStatus.FAILED);
        step.setRun(run);
        step.setErrorMessage("boom");
        when(agentStepRepository.findById(10L)).thenReturn(Optional.of(step));
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.retryStep(1L, 10L);

        assertThat(step.getStatus()).isEqualTo(AgentStepStatus.PENDING);
        assertThat(step.getErrorMessage()).isNull();
        assertThat(run.getStatus()).isEqualTo(RunStatus.WAITING_APPROVAL);
    }

    @Test
    void retryStep_onSucceededRun_keepsSucceeded() {
        Run run = run(1L, RunStatus.SUCCEEDED);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep step = step(10L, 100L, AgentStepStatus.FAILED);
        step.setRun(run);
        step.setErrorMessage("boom");
        when(agentStepRepository.findById(10L)).thenReturn(Optional.of(step));
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.retryStep(1L, 10L);

        assertThat(step.getStatus()).isEqualTo(AgentStepStatus.PENDING);
        assertThat(run.getStatus()).isEqualTo(RunStatus.SUCCEEDED);
    }

    @Test
    void retryStep_onRunningRun_keepsRunning() {
        Run run = run(1L, RunStatus.RUNNING);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep step = step(10L, 100L, AgentStepStatus.FAILED);
        step.setRun(run);
        step.setErrorMessage("boom");
        when(agentStepRepository.findById(10L)).thenReturn(Optional.of(step));
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runService.retryStep(1L, 10L);

        assertThat(step.getStatus()).isEqualTo(AgentStepStatus.PENDING);
        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
    }

    @Test
    void pause_onWaitingApproval_throws() {
        Run run = run(1L, RunStatus.WAITING_APPROVAL);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        assertThatThrownBy(() -> runService.pause(1L))
                .isInstanceOf(IllegalStateException.class);

        assertThat(run.getStatus()).isEqualTo(RunStatus.WAITING_APPROVAL);
    }

    @Test
    void resume_onCancelled_throws() {
        Run run = run(1L, RunStatus.CANCELLED);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        assertThatThrownBy(() -> runService.resume(1L))
                .isInstanceOf(IllegalStateException.class);

        assertThat(run.getStatus()).isEqualTo(RunStatus.CANCELLED);
    }

    @Test
    void pause_missingRun_throwsResourceNotFound() {
        when(runRepository.findById(99L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> runService.pause(99L))
                .isInstanceOf(ResourceNotFoundException.class);
    }
}