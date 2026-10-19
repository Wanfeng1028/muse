package com.dramafactory.service;

import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.dto.Records;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.env.Environment;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RunExecutorReviewGateTest {

    private RunRepository runRepository;
    private AgentStepRepository agentStepRepository;
    private VideoTaskRepository videoTaskRepository;
    private ScriptService scriptService;
    private ScriptSplitterService scriptSplitterService;
    private VideoTaskService videoTaskService;
    private FinalCutService finalCutService;
    private RunLogService runLogService;
    private Environment environment;
    private ObjectMapper objectMapper;
    private SkillService skillService;
    private ReviewService reviewService;

    private RunExecutor runExecutor;

    @BeforeEach
    void setUp() {
        runRepository = mock(RunRepository.class);
        agentStepRepository = mock(AgentStepRepository.class);
        videoTaskRepository = mock(VideoTaskRepository.class);
        scriptService = mock(ScriptService.class);
        scriptSplitterService = mock(ScriptSplitterService.class);
        videoTaskService = mock(VideoTaskService.class);
        finalCutService = mock(FinalCutService.class);
        runLogService = mock(RunLogService.class);
        environment = mock(Environment.class);
        objectMapper = new ObjectMapper();
        skillService = mock(SkillService.class);
        reviewService = mock(ReviewService.class);

        runExecutor = new RunExecutor(
                runRepository,
                agentStepRepository,
                videoTaskRepository,
                scriptService,
                scriptSplitterService,
                videoTaskService,
                finalCutService,
                runLogService,
                environment,
                objectMapper,
                skillService,
                reviewService
        );
    }

    @Test
    void reviewGateBlocked_pausesRunAndKeepsStepPending_andNeverSubmitsVideoTasks() {
        long runId = 7L;
        long episodeId = 7L;

        Run run = new Run();
        run.setId(runId);
        run.setStatus(RunStatus.RUNNING);

        AgentStep step = new AgentStep();
        step.setRun(run);
        step.setSeqNo(1);
        step.setAgentType(AgentType.VIDEO);
        step.setStatus(AgentStepStatus.PENDING);
        step.setEpisodeId(episodeId);

        when(runRepository.findById(runId)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(runId)).thenReturn(List.of(step));
        when(reviewService.isScriptApproved(runId)).thenReturn(false);
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runExecutor.advanceRun(run);

        assertEquals(RunStatus.PAUSED, run.getStatus());
        assertEquals(AgentStepStatus.PENDING, step.getStatus());
        verify(videoTaskService, never()).submitAllForEpisode(Mockito.anyLong());
    }

    @Test
    void reviewGateOpen_submitsVideoTasksOnce_andKeepsStepRunning() {
        long runId = 7L;
        long episodeId = 7L;

        Run run = new Run();
        run.setId(runId);
        run.setStatus(RunStatus.RUNNING);

        AgentStep step = new AgentStep();
        step.setRun(run);
        step.setSeqNo(1);
        step.setAgentType(AgentType.VIDEO);
        step.setStatus(AgentStepStatus.PENDING);
        step.setEpisodeId(episodeId);

        when(runRepository.findById(runId)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(runId)).thenReturn(List.of(step));
        when(reviewService.isScriptApproved(runId)).thenReturn(true);
        when(videoTaskService.submitAllForEpisode(episodeId)).thenReturn(List.of());
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runExecutor.advanceRun(run);

        verify(videoTaskService, times(1)).submitAllForEpisode(episodeId);
        assertEquals(AgentStepStatus.RUNNING, step.getStatus());
    }

    @Test
    void scriptStep_notAffectedByReviewGate_callsGenerate() {
        long runId = 7L;
        long episodeId = 7L;

        Run run = new Run();
        run.setId(runId);
        run.setStatus(RunStatus.RUNNING);

        AgentStep step = new AgentStep();
        step.setRun(run);
        step.setSeqNo(1);
        step.setAgentType(AgentType.SCRIPT);
        step.setStatus(AgentStepStatus.PENDING);
        step.setEpisodeId(episodeId);

        Records.GenerateScriptResponse response = new Records.GenerateScriptResponse(
                episodeId, 0, "text", "ai", "model", 1L, 1, 1, null);

        when(runRepository.findById(runId)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(runId)).thenReturn(List.of(step));
        when(reviewService.isScriptApproved(runId)).thenReturn(false);
        when(scriptService.generate(eq(episodeId), anyString())).thenReturn(response);
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        runExecutor.advanceRun(run);

        verify(scriptService, times(1)).generate(eq(episodeId), eq("ai"));
    }
}
