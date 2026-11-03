package com.dramafactory.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.assertj.core.api.Assertions.*;
import org.mockito.ArgumentCaptor;
import java.util.List;
import java.util.Optional;
import java.time.LocalDateTime;
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

public class RunServiceApproveIdempotencyDeepTest {
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
    void approveTwiceAfterApprovedSecondThrows() {
        AgentStep qcStep = stubApproval(1L, 11L, 21L, 31L);
        runService.approve(1L, true, "ok");
        assertThat(qcStep.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThatThrownBy(() -> runService.approve(1L, true, "again")).isInstanceOf(IllegalStateException.class).hasMessageContaining("RUNNING");
        verify(finalCutService, times(1)).qc(anyLong(), any());
        ArgumentCaptor<Records.QcRequest> cap = ArgumentCaptor.forClass(Records.QcRequest.class);
        verify(finalCutService).qc(eq(31L), cap.capture());
        assertThat(cap.getValue().verdict()).isEqualTo("APPROVED");
        assertThat(cap.getValue().note()).isEqualTo("ok");
        assertThat(qcStep.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
    }

    @Test
    void approveTwiceKeepsEndedAtFromFirstApproval() {
        AgentStep qcStep = stubApproval(4L, 14L, 24L, 34L);
        runService.approve(4L, true, "ok");
        LocalDateTime t1 = qcStep.getEndedAt();
        assertThat(t1).isNotNull();
        assertThatThrownBy(() -> runService.approve(4L, true, "ok2")).isInstanceOf(IllegalStateException.class);
        assertThat(qcStep.getEndedAt()).isEqualTo(t1);
    }
}
