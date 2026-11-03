package com.dramafactory.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.assertj.core.api.Assertions.*;
import java.util.Optional;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.dramafactory.config.CurrentUser;
import com.dramafactory.exception.ResourceNotFoundException;
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

class RunServiceIllegalTransitionMatrixDeepTest {

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

    private Run runWith(RunStatus s, long id) {
        Run run = new Run();
        run.setId(id);
        run.setGoal("g");
        run.setStatus(s);
        when(runRepository.findById(id)).thenReturn(Optional.of(run));
        return run;
    }

    @Test
    void pauseRejectsEveryNonRunningStatus() {
        RunStatus[] statuses = {RunStatus.DRAFT, RunStatus.PLANNED, RunStatus.PAUSED,
                RunStatus.WAITING_APPROVAL, RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED};
        for (RunStatus s : statuses) {
            Run run = runWith(s, 1L);
            assertThatThrownBy(() -> runService.pause(1L))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining(s.name());
            assertThat(run.getStatus()).isEqualTo(s);
        }
        verify(runRepository, never()).save(any(Run.class));
    }

    @Test
    void resumeRejectsEveryNonPausedStatus() {
        RunStatus[] statuses = {RunStatus.DRAFT, RunStatus.PLANNED, RunStatus.RUNNING,
                RunStatus.WAITING_APPROVAL, RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED};
        for (RunStatus s : statuses) {
            Run run = runWith(s, 2L);
            assertThatThrownBy(() -> runService.resume(2L))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining(s.name());
            assertThat(run.getStatus()).isEqualTo(s);
        }
    }

    @Test
    void cancelRejectsDraftPlannedAndTerminal() {
        RunStatus[] statuses = {RunStatus.DRAFT, RunStatus.PLANNED, RunStatus.SUCCEEDED,
                RunStatus.FAILED, RunStatus.CANCELLED};
        for (RunStatus s : statuses) {
            Run run = runWith(s, 3L);
            assertThatThrownBy(() -> runService.cancel(3L))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageStartingWith("当前状态不可取消");
            assertThat(run.getStatus()).isEqualTo(s);
        }
    }

    @Test
    void approveRejectsEveryNonWaitingStatus() {
        RunStatus[] statuses = {RunStatus.DRAFT, RunStatus.PLANNED, RunStatus.RUNNING, RunStatus.PAUSED,
                RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED};
        for (RunStatus s : statuses) {
            Run run = runWith(s, 4L);
            assertThatThrownBy(() -> runService.approve(4L, true, "x"))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageStartingWith("只有 WAITING_APPROVAL 状态可审批");
            assertThat(run.getStatus()).isEqualTo(s);
        }
        verify(finalCutService, never()).qc(anyLong(), any());
    }

    @Test
    void rerunRejectsEveryNonTerminalStatus() {
        RunStatus[] statuses = {RunStatus.DRAFT, RunStatus.PLANNED, RunStatus.RUNNING,
                RunStatus.PAUSED, RunStatus.WAITING_APPROVAL};
        for (RunStatus s : statuses) {
            Run run = runWith(s, 5L);
            assertThatThrownBy(() -> runService.rerun(5L, null))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageStartingWith("仅终态运行可重跑");
            assertThat(run.getStatus()).isEqualTo(s);
        }
    }

    @Test
    void pauseResumeFullCycle() {
        Run run = runWith(RunStatus.RUNNING, 100L);
        runService.pause(100L);
        assertThat(run.getStatus()).isEqualTo(RunStatus.PAUSED);
        runService.resume(100L);
        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
        runService.pause(100L);
        assertThat(run.getStatus()).isEqualTo(RunStatus.PAUSED);
    }

    @Test
    void nullRunIdRejectedEverywhere() {
        assertThatThrownBy(() -> runService.pause(null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("runId 不能为空");
        assertThatThrownBy(() -> runService.resume(null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("runId 不能为空");
        assertThatThrownBy(() -> runService.cancel(null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("runId 不能为空");
        assertThatThrownBy(() -> runService.approve(null, true, "x"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("runId 不能为空");
        assertThatThrownBy(() -> runService.rerun(null, null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("runId 不能为空");
    }

    @Test
    void missingRunThrowsResourceNotFound() {
        when(runRepository.findById(404L)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> runService.pause(404L)).isInstanceOf(ResourceNotFoundException.class);
        assertThatThrownBy(() -> runService.resume(404L)).isInstanceOf(ResourceNotFoundException.class);
        assertThatThrownBy(() -> runService.cancel(404L)).isInstanceOf(ResourceNotFoundException.class);
    }
}