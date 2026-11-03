package com.dramafactory.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.assertj.core.api.Assertions.*;
import java.util.List;
import java.util.Optional;
import java.time.LocalDateTime;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.env.Environment;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.ScriptService;
import com.dramafactory.service.ScriptSplitterService;
import com.dramafactory.service.VideoTaskService;
import com.dramafactory.service.FinalCutService;
import com.dramafactory.service.RunLogService;
import com.dramafactory.service.SkillService;
import com.dramafactory.service.ReviewService;

class RunExecutorApprovalStallDeepTest {

    private RunRepository runRepository;
    private AgentStepRepository agentStepRepository;
    private RunExecutor runExecutor;

    @BeforeEach
    void setUp() {
        runRepository = mock(RunRepository.class);
        agentStepRepository = mock(AgentStepRepository.class);
        runExecutor = new RunExecutor(runRepository, agentStepRepository, mock(VideoTaskRepository.class),
                mock(ScriptService.class), mock(ScriptSplitterService.class), mock(VideoTaskService.class),
                mock(FinalCutService.class), mock(RunLogService.class), mock(Environment.class),
                new ObjectMapper(), mock(SkillService.class), mock(ReviewService.class));
    }

    @Test
    void tickNeverTouchesStaleWaitingApprovalRun() {
        Run run = new Run();
        run.setId(1L);
        run.setGoal("g");
        run.setStatus(RunStatus.WAITING_APPROVAL);
        run.setUpdatedAt(LocalDateTime.now().minusDays(3));
        when(runRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING)).thenReturn(List.of());
        runExecutor.tick();
        assertThat(run.getStatus()).isEqualTo(RunStatus.WAITING_APPROVAL);
        verify(runRepository, never()).findById(anyLong());
        verify(agentStepRepository, never()).findByRunIdOrderBySeqNoAsc(anyLong());
    }

    @Test
    void tickAdvancesAllRunningRunsWithNoSteps() {
        Run a = new Run();
        a.setId(11L);
        a.setGoal("g");
        a.setStatus(RunStatus.RUNNING);
        Run b = new Run();
        b.setId(12L);
        b.setGoal("g");
        b.setStatus(RunStatus.RUNNING);
        when(runRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING)).thenReturn(List.of(a, b));
        when(runRepository.findById(11L)).thenReturn(Optional.of(a));
        when(runRepository.findById(12L)).thenReturn(Optional.of(b));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(11L)).thenReturn(List.of());
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(12L)).thenReturn(List.of());
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        runExecutor.tick();
        assertThat(a.getStatus()).isEqualTo(RunStatus.SUCCEEDED);
        assertThat(b.getStatus()).isEqualTo(RunStatus.SUCCEEDED);
        verify(runRepository, times(2)).save(any(Run.class));
    }

    @Test
    void tickIsolatesFailingRunAndContinues() {
        Run a = new Run();
        a.setId(21L);
        a.setGoal("g");
        a.setStatus(RunStatus.RUNNING);
        Run b = new Run();
        b.setId(22L);
        b.setGoal("g");
        b.setStatus(RunStatus.RUNNING);
        when(runRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING)).thenReturn(List.of(a, b));
        when(runRepository.findById(21L)).thenThrow(new RuntimeException("db down"));
        when(runRepository.findById(22L)).thenReturn(Optional.of(b));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(22L)).thenReturn(List.of());
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        runExecutor.tick();
        assertThat(b.getStatus()).isEqualTo(RunStatus.SUCCEEDED);
    }
}
