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

public class RunServiceApproveRejectIdempotencyDeepTest {
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

    private AgentStep stubApproval(long runId, long stepId, long episodeId, long fcId) {
        Run run = new Run();
        run.setId(runId);
        run.setGoal("g");
        run.setStatus(RunStatus.WAITING_APPROVAL);
        AgentStep qcStep = new AgentStep();
        qcStep.setId(stepId);
        qcStep.setAgentType(AgentType.QC);
        qcStep.setStatus(AgentStepStatus.RUNNING);
        qcStep.setEpisodeId(episodeId);
        qcStep.setRun(run);
        FinalCut fc = new FinalCut();
        fc.setId(fcId);
        when(runRepository.findById(runId)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(runId)).thenReturn(List.of(qcStep));
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(episodeId)).thenReturn(Optional.of(fc));
        when(finalCutService.qc(anyLong(), any())).thenReturn(null);
        return qcStep;
    }

    @Test
    void approveTwiceAfterRejectedSecondThrows() {
        AgentStep qcStep = stubApproval(2L, 12L, 22L, 32L);
        runService.approve(2L, false, "no");
        assertThat(qcStep.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(qcStep.getErrorMessage()).isEqualTo("no");
        assertThatThrownBy(() -> runService.approve(2L, false, "x")).isInstanceOf(IllegalStateException.class).hasMessageContaining("FAILED");
        verify(finalCutService, times(1)).qc(anyLong(), any());
        ArgumentCaptor<Records.QcRequest> cap = ArgumentCaptor.forClass(Records.QcRequest.class);
        verify(finalCutService).qc(eq(32L), cap.capture());
        assertThat(cap.getValue().verdict()).isEqualTo("REJECTED");
        assertThat(cap.getValue().note()).isEqualTo("no");
    }

    @Test
    void approveOnCancelledRunThrows() {
        Run run = new Run();
        run.setId(3L);
        run.setGoal("g");
        run.setStatus(RunStatus.CANCELLED);
        when(runRepository.findById(3L)).thenReturn(Optional.of(run));
        assertThatThrownBy(() -> runService.approve(3L, true, "x")).isInstanceOf(IllegalStateException.class).hasMessageStartingWith("只有 WAITING_APPROVAL 状态可审批");
        verify(finalCutService, never()).qc(anyLong(), any());
    }
}
