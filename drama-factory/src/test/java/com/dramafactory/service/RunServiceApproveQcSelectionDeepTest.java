package com.dramafactory.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.assertj.core.api.Assertions.*;
import org.mockito.ArgumentCaptor;
import java.util.List;
import java.util.Optional;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.dramafactory.dto.Records;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.FinalCut;
import com.dramafactory.config.CurrentUser;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.service.LlmScriptService;
import com.dramafactory.service.ProjectService;
import com.dramafactory.service.EpisodeService;
import com.dramafactory.service.FinalCutService;
import com.dramafactory.service.RunLogService;

class RunServiceApproveQcSelectionDeepTest {

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

    private Run waitingRun(long runId) {
        Run run = new Run();
        run.setId(runId);
        run.setGoal("g");
        run.setStatus(RunStatus.WAITING_APPROVAL);
        when(runRepository.findById(runId)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(finalCutService.qc(anyLong(), any())).thenReturn(null);
        return run;
    }

    private AgentStep qcStep(long stepId, AgentStepStatus st, long episodeId, Run run) {
        AgentStep s = new AgentStep();
        s.setId(stepId);
        s.setAgentType(AgentType.QC);
        s.setStatus(st);
        s.setEpisodeId(episodeId);
        s.setRun(run);
        return s;
    }

    private FinalCut fc(long id) {
        FinalCut f = new FinalCut();
        f.setId(id);
        return f;
    }

    @Test
    void approvePicksRunningQcAmongMultiple() {
        Run run = waitingRun(1L);
        AgentStep qc1 = qcStep(11L, AgentStepStatus.RUNNING, 21L, run);
        AgentStep qc2 = qcStep(12L, AgentStepStatus.PENDING, 22L, run);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(qc1, qc2));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(21L)).thenReturn(Optional.of(fc(31L)));
        runService.approve(1L, true, "ok");
        assertThat(qc1.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(qc2.getStatus()).isEqualTo(AgentStepStatus.PENDING);
        ArgumentCaptor<Long> cap = ArgumentCaptor.forClass(Long.class);
        verify(finalCutService).qc(cap.capture(), any());
        assertThat(cap.getValue()).isEqualTo(31L);
        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
    }

    @Test
    void approveFallsBackToLastQcWhenNoneRunning() {
        Run run = waitingRun(2L);
        AgentStep qc1 = qcStep(21L, AgentStepStatus.PENDING, 41L, run);
        AgentStep qc2 = qcStep(22L, AgentStepStatus.PENDING, 42L, run);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(2L)).thenReturn(List.of(qc1, qc2));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(42L)).thenReturn(Optional.of(fc(52L)));
        runService.approve(2L, true, "ok");
        assertThat(qc2.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(qc1.getStatus()).isEqualTo(AgentStepStatus.PENDING);
        ArgumentCaptor<Long> cap = ArgumentCaptor.forClass(Long.class);
        verify(finalCutService).qc(cap.capture(), any());
        assertThat(cap.getValue()).isEqualTo(52L);
    }

    @Test
    void approveRejectsWhenQcStepHasNullEpisodeId() {
        Run run = waitingRun(3L);
        AgentStep qc = qcStep(31L, AgentStepStatus.RUNNING, 0L, run);
        qc.setEpisodeId(null);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(3L)).thenReturn(List.of(qc));
        assertThatThrownBy(() -> runService.approve(3L, true, "ok")).isInstanceOf(IllegalStateException.class).hasMessage("运行无关联成片，无法审批：runId=3");
        verify(finalCutRepository, never()).findFirstByEpisodeIdOrderByIdDesc(any());
        verify(finalCutService, never()).qc(anyLong(), any());
    }
}
