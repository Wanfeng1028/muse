package com.dramafactory.service;
import com.dramafactory.config.CurrentUser;

import com.dramafactory.dto.Records;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.Run;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
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
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * RunService.approve 及相关私有方法（findWaitingQcStep / findFinalCutId）分支覆盖测试。
 * 同时覆盖 createRun 中 SCRIPT/BOARD skillId 赋值分支。
 */
class RunServiceApproveTest {

    @Mock
    private RunRepository runRepository;
    @Mock
    private AgentStepRepository agentStepRepository;
    @Mock
    private EpisodeRepository episodeRepository;
    @Mock
    private FinalCutRepository finalCutRepository;
    @Mock
    private VideoTaskRepository videoTaskRepository;
    @Mock
    private LlmScriptService llmScriptService;
    @Mock
    private ProjectService projectService;
    @Mock
    private EpisodeService episodeService;
    @Mock
    private FinalCutService finalCutService;
    @Mock
    private RunLogService runLogService;
    @Mock
    private CurrentUser currentUser;
    @Mock
    private DramaProjectRepository projectRepository;

    private RunService runService;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
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

    private Run waitingRun(Long id) {
        Run run = new Run();
        run.setId(id);
        run.setGoal("目标");
        run.setStatus(RunStatus.WAITING_APPROVAL);
        return run;
    }

    private AgentStep qcStep(Long id, AgentStepStatus status, Long episodeId) {
        AgentStep s = new AgentStep();
        s.setId(id);
        s.setAgentType(AgentType.QC);
        s.setStatus(status);
        s.setEpisodeId(episodeId);
        return s;
    }

    // 覆盖 L411 mb=1：approve 状态校验分支（run 状态非 WAITING_APPROVAL）
    @Test
    void approve_notWaitingApproval_throwsIllegalState() {
        Run run = waitingRun(1L);
        run.setStatus(RunStatus.RUNNING);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> runService.approve(1L, true, "ok"));
        assertEquals(true, ex.getMessage().contains("WAITING_APPROVAL"));
    }

    // 覆盖 L422 mb=1：approved=true 且 qcStep != null，QC 步被更新为 SUCCEEDED
    @Test
    void approve_approvedWithQcStep_succeedsAndMarksQcSucceeded() {
        Run run = waitingRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep step = qcStep(50L, AgentStepStatus.RUNNING, 10L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(step));

        FinalCut fc = new FinalCut();
        fc.setId(99L);
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(10L)).thenReturn(Optional.of(fc));

        runService.approve(1L, true, "ok");

        verify(finalCutService).qc(eq(99L), eq(new Records.QcRequest("APPROVED", "ok")));
        assertEquals(RunStatus.RUNNING, run.getStatus());
        assertEquals(AgentStepStatus.SUCCEEDED, step.getStatus());
        assertNotNull(step.getEndedAt());
        verify(agentStepRepository).save(step);
        verify(runRepository).save(run);
    }

    // 覆盖 L431 mb=1：approved=false 且 qcStep != null，QC 步被更新为 FAILED
    @Test
    void approve_rejectedWithQcStep_failsAndMarksQcFailed() {
        Run run = waitingRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep step = qcStep(50L, AgentStepStatus.RUNNING, 10L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(step));

        FinalCut fc = new FinalCut();
        fc.setId(99L);
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(10L)).thenReturn(Optional.of(fc));

        runService.approve(1L, false, "不行");

        verify(finalCutService).qc(eq(99L), eq(new Records.QcRequest("REJECTED", "不行")));
        assertEquals(RunStatus.FAILED, run.getStatus());
        assertEquals(AgentStepStatus.FAILED, step.getStatus());
        assertEquals("不行", step.getErrorMessage());
        verify(agentStepRepository).save(step);
        verify(runRepository).save(run);
    }

    // 覆盖 L461 mb=1：findFinalCutId 中 qcStep == null（steps 为空）→ 抛"运行无关联成片"
    @Test
    void approve_noSteps_throwsNoFinalCut() {
        Run run = waitingRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(Collections.emptyList());

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> runService.approve(1L, true, "ok"));
        assertEquals(true, ex.getMessage().contains("运行无关联成片"));
    }

    // 覆盖 L461 mb=1：findFinalCutId 中 qcStep.getEpisodeId() == null → 抛"运行无关联成片"
    @Test
    void approve_qcStepEpisodeIdNull_throwsNoFinalCut() {
        Run run = waitingRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep step = qcStep(50L, AgentStepStatus.RUNNING, null);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(step));

        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> runService.approve(1L, true, "ok"));
        assertEquals(true, ex.getMessage().contains("运行无关联成片"));
    }

    // 覆盖 L449 mb=1 的 fallback 路径：QC step 非 RUNNING，作为 fallback 返回并被更新
    @Test
    void approve_qcStepNotRunning_usesFallback() {
        Run run = waitingRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep step = qcStep(50L, AgentStepStatus.SUCCEEDED, 10L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(step));

        FinalCut fc = new FinalCut();
        fc.setId(99L);
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(10L)).thenReturn(Optional.of(fc));

        runService.approve(1L, true, "ok");

        verify(finalCutService).qc(eq(99L), eq(new Records.QcRequest("APPROVED", "ok")));
        assertEquals(RunStatus.RUNNING, run.getStatus());
        assertEquals(AgentStepStatus.SUCCEEDED, step.getStatus());
    }

    // 覆盖 L449 mb=1：多个 QC step，RUNNING 优先（第二个被选中）
    @Test
    void approve_multipleQcSteps_runningOneIsSelected() {
        Run run = waitingRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        AgentStep first = qcStep(50L, AgentStepStatus.SUCCEEDED, 10L);
        AgentStep second = qcStep(51L, AgentStepStatus.RUNNING, 10L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(first, second));

        FinalCut fc = new FinalCut();
        fc.setId(99L);
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(10L)).thenReturn(Optional.of(fc));

        runService.approve(1L, true, "ok");

        // 只有 RUNNING 的那个 QC step 被更新为 SUCCEEDED
        verify(agentStepRepository, times(1)).save(second);
        assertEquals(AgentStepStatus.SUCCEEDED, second.getStatus());
        // 第一个已经 SUCCEEDED，approve 不会保存它
        verify(agentStepRepository, times(0)).save(first);
    }

    // 覆盖 L278 mb=1：createRun 时 SCRIPT step 的 skillId 被设置（非 null 分支）
    @Test
    void createRun_withSkillIds_setsScriptAndBoardSkillIds() {
        Records.PlanPreview plan = new Records.PlanPreview(
                "目标",
                List.of(new Records.PlanEpisode(1, "第一集", "大纲")),
                false);

        Records.ProjectResponse projectResponse = org.mockito.Mockito.mock(Records.ProjectResponse.class);
        org.mockito.Mockito.when(projectResponse.id()).thenReturn(7L);
        when(projectService.create(any())).thenReturn(projectResponse);

        Records.EpisodeResponse episodeResponse = org.mockito.Mockito.mock(Records.EpisodeResponse.class);
        org.mockito.Mockito.when(episodeResponse.id()).thenReturn(11L);
        when(episodeService.create(any(), any())).thenReturn(episodeResponse);

        when(runRepository.save(any(Run.class))).thenAnswer(inv -> {
            Run r = inv.getArgument(0);
            if (r.getId() == null) {
                r.setId(1L);
            }
            return r;
        });

        Long runId = runService.createRun("目标", plan, 100L, 200L);
        assertNotNull(runId);

        ArgumentCaptor<AgentStep> captor = ArgumentCaptor.forClass(AgentStep.class);
        verify(agentStepRepository, times(5)).save(captor.capture());

        List<AgentStep> saved = new ArrayList<>(captor.getAllValues());
        Long scriptSkillId = null;
        Long boardSkillId = null;
        Long videoSkillId = null;
        for (AgentStep s : saved) {
            if (s.getAgentType() == AgentType.SCRIPT) {
                scriptSkillId = s.getSkillId();
            } else if (s.getAgentType() == AgentType.BOARD) {
                boardSkillId = s.getSkillId();
            } else if (s.getAgentType() == AgentType.VIDEO) {
                videoSkillId = s.getSkillId();
            }
        }
        assertEquals(100L, scriptSkillId);
        assertEquals(200L, boardSkillId);
        assertNull(videoSkillId);
    }

    // 覆盖 L278/L281 反分支：createRun 时 skillId 为 null，SCRIPT/BOARD step 的 skillId 也为 null
    @Test
    void createRun_withoutSkillIds_leavesSkillIdNull() {
        Records.PlanPreview plan = new Records.PlanPreview(
                "目标",
                List.of(new Records.PlanEpisode(1, "第一集", "大纲")),
                false);

        Records.ProjectResponse projectResponse = org.mockito.Mockito.mock(Records.ProjectResponse.class);
        org.mockito.Mockito.when(projectResponse.id()).thenReturn(7L);
        when(projectService.create(any())).thenReturn(projectResponse);

        Records.EpisodeResponse episodeResponse = org.mockito.Mockito.mock(Records.EpisodeResponse.class);
        org.mockito.Mockito.when(episodeResponse.id()).thenReturn(11L);
        when(episodeService.create(any(), any())).thenReturn(episodeResponse);

        when(runRepository.save(any(Run.class))).thenAnswer(inv -> {
            Run r = inv.getArgument(0);
            if (r.getId() == null) {
                r.setId(2L);
            }
            return r;
        });

        Long runId = runService.createRun("目标", plan, null, null);
        assertNotNull(runId);

        ArgumentCaptor<AgentStep> captor = ArgumentCaptor.forClass(AgentStep.class);
        verify(agentStepRepository, times(5)).save(captor.capture());

        for (AgentStep s : captor.getAllValues()) {
            if (s.getAgentType() == AgentType.SCRIPT || s.getAgentType() == AgentType.BOARD) {
                assertNull(s.getSkillId());
            }
        }
    }

    // 覆盖 requireRun：runId 不存在 → ResourceNotFoundException
    @Test
    void approve_runNotFound_throwsResourceNotFound() {
        when(runRepository.findById(999L)).thenReturn(Optional.empty());
        assertThrows(com.dramafactory.exception.ResourceNotFoundException.class,
                () -> runService.approve(999L, true, "ok"));
    }
}
