package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
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
import org.springframework.core.env.Environment;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ApprovalGateDeepTest {

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

        runService = new RunService(
                runRepository,
                agentStepRepository,
                episodeRepository,
                finalCutRepository,
                videoTaskRepository,
                llmScriptService,
                projectService,
                episodeService,
                finalCutService,
                runLogService,
                new ObjectMapper(),
                "Deepseek-v4-flash",
                currentUser,
                projectRepository);
    }

    private Run runWithStatus(Long id, RunStatus status) {
        Run run = new Run();
        run.setId(id);
        run.setGoal("goal");
        run.setStatus(status);
        return run;
    }

    private AgentStep qcStep(Long id, Long episodeId, AgentStepStatus status) {
        AgentStep step = new AgentStep();
        step.setId(id);
        step.setAgentType(AgentType.QC);
        step.setEpisodeId(episodeId);
        step.setStatus(status);
        return step;
    }

    private FinalCut finalCut(Long id) {
        FinalCut fc = new FinalCut();
        fc.setId(id);
        return fc;
    }

    private void stubRun(Long runId, Run run) {
        when(runRepository.findById(runId)).thenReturn(Optional.of(run));
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
    }

    private void stubAgentSteps(Long runId, List<AgentStep> steps) {
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(runId)).thenReturn(steps);
        when(agentStepRepository.save(any(AgentStep.class))).thenAnswer(inv -> inv.getArgument(0));
    }

    @Test
    void approve_approvedWithNullNote_qcCalledWithNullNote() {
        Run run = runWithStatus(1L, RunStatus.WAITING_APPROVAL);
        AgentStep qc = qcStep(10L, 700L, AgentStepStatus.RUNNING);
        stubRun(1L, run);
        stubAgentSteps(1L, List.of(qc));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(700L))
                .thenReturn(Optional.of(finalCut(900L)));

        runService.approve(1L, true, null);

        verify(finalCutService).qc(eq(900L), eq(new Records.QcRequest("APPROVED", null)));
        assertEquals(AgentStepStatus.SUCCEEDED, qc.getStatus());
        assertNotNull(qc.getEndedAt());
        assertEquals(RunStatus.RUNNING, run.getStatus());
    }

    @Test
    void approve_rejectedWithNullNote_errorMessageNull() {
        Run run = runWithStatus(1L, RunStatus.WAITING_APPROVAL);
        AgentStep qc = qcStep(10L, 700L, AgentStepStatus.RUNNING);
        stubRun(1L, run);
        stubAgentSteps(1L, List.of(qc));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(700L))
                .thenReturn(Optional.of(finalCut(900L)));

        runService.approve(1L, false, null);

        verify(finalCutService).qc(eq(900L), eq(new Records.QcRequest("REJECTED", null)));
        assertEquals(AgentStepStatus.FAILED, qc.getStatus());
        assertNull(qc.getErrorMessage());
        assertEquals(RunStatus.FAILED, run.getStatus());
    }

    @Test
    void approve_onPausedRun_throws() {
        Run run = runWithStatus(1L, RunStatus.PAUSED);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        assertThrows(IllegalStateException.class, () -> runService.approve(1L, true, "note"));

        verify(finalCutService, never()).qc(any(), any());
    }

    @Test
    void approve_onCancelledRun_throws() {
        Run run = runWithStatus(1L, RunStatus.CANCELLED);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        assertThrows(IllegalStateException.class, () -> runService.approve(1L, false, "note"));

        verify(finalCutService, never()).qc(any(), any());
    }

    @Test
    void approve_setsQcStepEndedAtOnBothBranches() {
        Run runA = runWithStatus(1L, RunStatus.WAITING_APPROVAL);
        AgentStep qcA = qcStep(10L, 700L, AgentStepStatus.RUNNING);
        stubRun(1L, runA);
        stubAgentSteps(1L, List.of(qcA));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(700L))
                .thenReturn(Optional.of(finalCut(900L)));

        runService.approve(1L, true, "ok");
        assertNotNull(qcA.getEndedAt());

        Run runB = runWithStatus(2L, RunStatus.WAITING_APPROVAL);
        AgentStep qcB = qcStep(20L, 701L, AgentStepStatus.RUNNING);
        stubRun(2L, runB);
        stubAgentSteps(2L, List.of(qcB));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(701L))
                .thenReturn(Optional.of(finalCut(901L)));

        runService.approve(2L, false, "no");
        assertNotNull(qcB.getEndedAt());
    }

    @Test
    void approve_afterApproved_tickPicksUpRun() {
        Run run = runWithStatus(1L, RunStatus.WAITING_APPROVAL);
        AgentStep qc = qcStep(10L, 700L, AgentStepStatus.RUNNING);
        stubRun(1L, run);
        stubAgentSteps(1L, List.of(qc));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(700L))
                .thenReturn(Optional.of(finalCut(900L)));

        runService.approve(1L, true, "ok");
        assertEquals(RunStatus.RUNNING, run.getStatus());

        RunRepository executorRunRepository = runRepository;
        AgentStepRepository executorAgentStepRepository = mock(AgentStepRepository.class);
        VideoTaskRepository executorVideoTaskRepository = mock(VideoTaskRepository.class);
        ScriptService executorScriptService = mock(ScriptService.class);
        ScriptSplitterService executorScriptSplitterService = mock(ScriptSplitterService.class);
        VideoTaskService executorVideoTaskService = mock(VideoTaskService.class);
        FinalCutService executorFinalCutService = mock(FinalCutService.class);
        RunLogService executorRunLogService = mock(RunLogService.class);
        Environment executorEnvironment = mock(Environment.class);
        ObjectMapper executorObjectMapper = new ObjectMapper();
        SkillService executorSkillService = mock(SkillService.class);
        ReviewService executorReviewService = mock(ReviewService.class);

        when(executorRunRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING))
                .thenReturn(List.of(run));
        when(executorRunRepository.findById(1L)).thenReturn(Optional.of(run));
        when(executorRunRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));
        when(executorAgentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of());

        RunExecutor executor = new RunExecutor(
                executorRunRepository,
                executorAgentStepRepository,
                executorVideoTaskRepository,
                executorScriptService,
                executorScriptSplitterService,
                executorVideoTaskService,
                executorFinalCutService,
                executorRunLogService,
                executorEnvironment,
                executorObjectMapper,
                executorSkillService,
                executorReviewService);

        executor.tick();

        ArgumentCaptor<Run> captor = ArgumentCaptor.forClass(Run.class);
        verify(executorRunRepository, org.mockito.Mockito.atLeastOnce()).save(captor.capture());
        boolean sawSucceeded = captor.getAllValues().stream()
                .anyMatch(r -> r.getStatus() == RunStatus.SUCCEEDED);
        assertTrue(sawSucceeded);
    }

    @Test
    void approve_rejected_leavesOtherStepsUntouched() {
        Run run = runWithStatus(1L, RunStatus.WAITING_APPROVAL);
        AgentStep scriptStep = new AgentStep();
        scriptStep.setId(5L);
        scriptStep.setAgentType(AgentType.SCRIPT);
        scriptStep.setStatus(AgentStepStatus.SUCCEEDED);
        AgentStep qc = qcStep(10L, 700L, AgentStepStatus.RUNNING);

        stubRun(1L, run);
        stubAgentSteps(1L, List.of(scriptStep, qc));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(700L))
                .thenReturn(Optional.of(finalCut(900L)));

        runService.approve(1L, false, "不行");

        assertEquals(AgentStepStatus.SUCCEEDED, scriptStep.getStatus());
        assertEquals(AgentStepStatus.FAILED, qc.getStatus());
        assertEquals("不行", qc.getErrorMessage());
    }

    @Test
    void approve_finalCutMissingForEpisode_throws() {
        Run run = runWithStatus(1L, RunStatus.WAITING_APPROVAL);
        AgentStep qc = qcStep(10L, 701L, AgentStepStatus.RUNNING);
        stubRun(1L, run);
        stubAgentSteps(1L, List.of(qc));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(701L))
                .thenReturn(Optional.empty());

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> runService.approve(1L, true, "ok"));

        assertTrue(ex.getMessage().contains("运行无关联成片"));
        verify(finalCutService, never()).qc(any(), any());
        assertEquals(RunStatus.WAITING_APPROVAL, run.getStatus());
    }

    @Test
    void approve_verdictPassedToQc_exactly() {
        Run runA = runWithStatus(1L, RunStatus.WAITING_APPROVAL);
        AgentStep qcA = qcStep(10L, 700L, AgentStepStatus.RUNNING);
        stubRun(1L, runA);
        stubAgentSteps(1L, List.of(qcA));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(700L))
                .thenReturn(Optional.of(finalCut(900L)));

        runService.approve(1L, true, "中文备注");

        ArgumentCaptor<Records.QcRequest> captorA = ArgumentCaptor.forClass(Records.QcRequest.class);
        verify(finalCutService).qc(eq(900L), captorA.capture());
        assertEquals("APPROVED", captorA.getValue().verdict());
        assertEquals("中文备注", captorA.getValue().note());

        Run runB = runWithStatus(2L, RunStatus.WAITING_APPROVAL);
        AgentStep qcB = qcStep(20L, 702L, AgentStepStatus.RUNNING);
        stubRun(2L, runB);
        stubAgentSteps(2L, List.of(qcB));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(702L))
                .thenReturn(Optional.of(finalCut(902L)));

        runService.approve(2L, true, "");

        ArgumentCaptor<Records.QcRequest> captorB = ArgumentCaptor.forClass(Records.QcRequest.class);
        verify(finalCutService).qc(eq(902L), captorB.capture());
        assertEquals("APPROVED", captorB.getValue().verdict());
        assertEquals("", captorB.getValue().note());
    }

    @Test
    void approve_qcStepWithNullEpisodeId_throwsNoFinalCut() {
        Run run = runWithStatus(1L, RunStatus.WAITING_APPROVAL);
        AgentStep qc = qcStep(10L, null, AgentStepStatus.RUNNING);
        stubRun(1L, run);
        stubAgentSteps(1L, List.of(qc));

        assertThrows(IllegalStateException.class, () -> runService.approve(1L, true, "ok"));

        verify(finalCutService, never()).qc(any(), any());
    }
}