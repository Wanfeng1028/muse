package com.dramafactory.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.assertj.core.api.Assertions.*;
import java.util.List;
import java.util.Optional;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.config.CurrentUser;
import com.dramafactory.exception.ResourceNotFoundException;
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

class RunServiceTotalsIsolationDeepTest {
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
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
    }

    private AgentStep step(AgentStepStatus st, Long tokens, Long cost) {
        AgentStep s = new AgentStep();
        s.setStatus(st);
        s.setTokensUsed(tokens);
        s.setCostCents(cost);
        return s;
    }

    @Test
    void aggregateTotalsIsolatesRuns() {
        Run run1 = new Run();
        run1.setId(1L);
        run1.setStatus(RunStatus.RUNNING);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run1));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(step(AgentStepStatus.SUCCEEDED, 100L, 5L), step(AgentStepStatus.SUCCEEDED, null, null), step(AgentStepStatus.SUCCEEDED, 50L, null)));
        Run run2 = new Run();
        run2.setId(2L);
        runService.aggregateTotals(1L);
        assertThat(run1.getTotalTokens()).isEqualTo(150L);
        assertThat(run1.getTotalCostCents()).isEqualTo(5L);
        assertThat(run2.getTotalTokens()).isNull();
        assertThat(run2.getTotalCostCents()).isNull();
        verify(runRepository, times(1)).save(any(Run.class));
    }

    @Test
    void aggregateTotalsAllNullTotalsZero() {
        Run run = new Run();
        run.setId(3L);
        run.setStatus(RunStatus.RUNNING);
        when(runRepository.findById(3L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(3L)).thenReturn(List.of(step(AgentStepStatus.SUCCEEDED, null, null), step(AgentStepStatus.SKIPPED, null, null)));
        runService.aggregateTotals(3L);
        assertThat(run.getTotalTokens()).isEqualTo(0L);
        assertThat(run.getTotalCostCents()).isEqualTo(0L);
    }

    @Test
    void markSucceededIfAllDoneStopsOnFailedStep() {
        Run run = new Run();
        run.setId(4L);
        run.setStatus(RunStatus.RUNNING);
        when(runRepository.findById(4L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(4L)).thenReturn(List.of(step(AgentStepStatus.SUCCEEDED, 10L, null), step(AgentStepStatus.FAILED, null, null)));
        runService.markSucceededIfAllDone(4L);
        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
        assertThat(run.getTotalTokens()).isNull();
        verify(runRepository, never()).save(any(Run.class));
    }

    @Test
    void aggregateTotalsMissingRunThrows() {
        when(runRepository.findById(404L)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> runService.aggregateTotals(404L)).isInstanceOf(ResourceNotFoundException.class);
        verify(agentStepRepository, never()).findByRunIdOrderBySeqNoAsc(anyLong());
    }
}
