package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.EpisodeService;
import com.dramafactory.service.FinalCutService;
import com.dramafactory.service.LlmScriptService;
import com.dramafactory.service.ProjectService;
import com.dramafactory.service.RunLogService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RunServiceRetryDownstreamDeepTest {

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

    private Run newRun(Long id, RunStatus status) {
        Run run = new Run();
        run.setId(id);
        run.setStatus(status);
        return run;
    }

    private AgentStep newStep(Long id, AgentStepStatus status, String errorMessage, Run run) {
        AgentStep step = new AgentStep();
        step.setId(id);
        step.setStatus(status);
        step.setErrorMessage(errorMessage);
        step.setRun(run);
        return step;
    }

    private void stubRunStep(Run run, AgentStep step) {
        when(runRepository.findById(run.getId())).thenReturn(Optional.of(run));
        when(agentStepRepository.findById(step.getId())).thenReturn(Optional.of(step));
    }

    private void stubRunStepWithSave(Run run, AgentStep step) {
        stubRunStep(run, step);
        when(runRepository.save(run)).thenAnswer(invocation -> invocation.getArgument(0));
    }

    @Test
    void retryOnCancelledRunReopensToRunning() {
        Run run = newRun(1L, RunStatus.CANCELLED);
        AgentStep step = newStep(11L, AgentStepStatus.FAILED, "boom", run);
        stubRunStepWithSave(run, step);

        runService.retryStep(1L, 11L);

        assertThat(step.getStatus()).isEqualTo(AgentStepStatus.PENDING);
        assertThat(step.getErrorMessage()).isNull();
        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
    }

    @Test
    void retryOnFailedRunReopensToRunning() {
        Run run = newRun(2L, RunStatus.FAILED);
        AgentStep step = newStep(12L, AgentStepStatus.FAILED, "boom", run);
        stubRunStepWithSave(run, step);

        runService.retryStep(2L, 12L);

        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
        assertThat(step.getStatus()).isEqualTo(AgentStepStatus.PENDING);
    }

    @Test
    void retryResetsOnlyTargetStepAndLeavesDownstreamUntouched() {
        Run run = newRun(3L, RunStatus.RUNNING);
        AgentStep s1 = newStep(31L, AgentStepStatus.SUCCEEDED, null, run);
        AgentStep s2 = newStep(32L, AgentStepStatus.FAILED, "e", run);
        AgentStep s3 = newStep(33L, AgentStepStatus.SUCCEEDED, null, run);
        stubRunStep(run, s2);

        runService.retryStep(3L, 32L);

        assertThat(s2.getStatus()).isEqualTo(AgentStepStatus.PENDING);
        assertThat(s2.getErrorMessage()).isNull();
        assertThat(s1.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(s3.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        verify(agentStepRepository, times(1)).save(any(AgentStep.class));
        verify(runRepository, never()).save(any(Run.class));
    }

    @Test
    void retryMissingStepThrows() {
        Run run = newRun(3L, RunStatus.RUNNING);
        when(runRepository.findById(3L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findById(99L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> runService.retryStep(3L, 99L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("步骤不存在：99");
    }

    @Test
    void retryStepWithNullRunThrows() {
        Run run = newRun(5L, RunStatus.RUNNING);
        AgentStep step = new AgentStep();
        step.setId(55L);
        step.setStatus(AgentStepStatus.FAILED);
        when(runRepository.findById(5L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findById(55L)).thenReturn(Optional.of(step));

        assertThatThrownBy(() -> runService.retryStep(5L, 55L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("步骤不属于该运行：stepId=55");
    }

    @Test
    void retryNullRunIdThrows() {
        assertThatThrownBy(() -> runService.retryStep(null, 1L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("runId 不能为空");
    }

    @Test
    void retryNullStepIdStillRequiresStepLookup() {
        Run run = newRun(7L, RunStatus.FAILED);
        when(runRepository.findById(7L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findById((Long) null)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> runService.retryStep(7L, null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("步骤不存在：null");
    }
}