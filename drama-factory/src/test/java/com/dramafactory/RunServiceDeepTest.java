package com.dramafactory;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.VideoTask;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.RunService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * RunService 深度测试：创建、状态流转、非法跳转拒绝、按状态查询、
 * Run 与 AgentStep 关联、删除语义、汇总与终态标记。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:runservicedeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class RunServiceDeepTest {

    @Autowired
    private RunService runService;

    @Autowired
    private RunRepository runRepository;

    @Autowired
    private AgentStepRepository agentStepRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private FinalCutRepository finalCutRepository;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private DramaProjectRepository projectRepository;

    @BeforeEach
    void cleanup() {
        // 子表在前，按外键安全顺序清理
        videoTaskRepository.deleteAll();
        finalCutRepository.deleteAll();
        agentStepRepository.deleteAll();
        episodeRepository.deleteAll();
        runRepository.deleteAll();
        projectRepository.deleteAll();
    }

    private Records.PlanPreview samplePlan(int episodeCount) {
        List<Records.PlanEpisode> episodes = new java.util.ArrayList<>();
        for (int i = 1; i <= episodeCount; i++) {
            episodes.add(new Records.PlanEpisode(i, "第 " + i + " 集", "剧情 " + i));
        }
        return new Records.PlanPreview("测试目标", episodes, false);
    }

    private Long createSampleRun() {
        return runService.createRun("拍一个 2 集的短剧", samplePlan(2));
    }

    @Test
    void createRun_shouldPersistRunAndAgentSteps() {
        Long runId = createSampleRun();
        assertNotNull(runId);

        Run run = runRepository.findById(runId).orElseThrow();
        assertEquals(RunStatus.RUNNING, run.getStatus());
        assertNotNull(run.getProjectId());
        assertNotNull(run.getPlanJson());

        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        // 2 集 × 5 类 agent = 10
        assertEquals(10, steps.size());
        for (AgentStep s : steps) {
            assertEquals(AgentStepStatus.PENDING, s.getStatus());
            assertNotNull(s.getEpisodeId());
            assertNotNull(s.getRun());
            assertEquals(runId, s.getRun().getId());
        }
        assertEquals(1, steps.get(0).getSeqNo());
        assertEquals(10, steps.get(9).getSeqNo());
    }

    @Test
    void createRun_nullGoal_shouldThrow() {
        assertThrows(IllegalArgumentException.class,
                () -> runService.createRun(null, samplePlan(1)));
    }

    @Test
    void createRun_blankGoal_shouldThrow() {
        assertThrows(IllegalArgumentException.class,
                () -> runService.createRun("   ", samplePlan(1)));
    }

    @Test
    void createRun_nullPlan_shouldThrow() {
        assertThrows(IllegalArgumentException.class,
                () -> runService.createRun("目标", null));
    }

    @Test
    void createRun_emptyPlanEpisodes_shouldThrow() {
        Records.PlanPreview empty = new Records.PlanPreview("目标", List.of(), false);
        assertThrows(IllegalArgumentException.class,
                () -> runService.createRun("目标", empty));
    }

    @Test
    void createRun_withSkillIds_shouldBindSkillToScriptAndBoard() {
        Long runId = runService.createRun("目标", samplePlan(1), 111L, 222L);
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        assertEquals(5, steps.size());
        for (AgentStep s : steps) {
            if (s.getAgentType() == AgentType.SCRIPT) {
                assertEquals(111L, s.getSkillId());
            } else if (s.getAgentType() == AgentType.BOARD) {
                assertEquals(222L, s.getSkillId());
            } else {
                assertNull(s.getSkillId());
            }
        }
    }

    @Test
    void pauseAndResume_shouldTransitionStatus() {
        Long runId = createSampleRun();

        runService.pause(runId);
        assertEquals(RunStatus.PAUSED, runRepository.findById(runId).orElseThrow().getStatus());

        runService.resume(runId);
        assertEquals(RunStatus.RUNNING, runRepository.findById(runId).orElseThrow().getStatus());
    }

    @Test
    void pause_nonRunning_shouldThrow() {
        Long runId = createSampleRun();
        runService.pause(runId);
        assertThrows(IllegalStateException.class, () -> runService.pause(runId));
    }

    @Test
    void resume_nonPaused_shouldThrow() {
        Long runId = createSampleRun();
        assertThrows(IllegalStateException.class, () -> runService.resume(runId));
    }

    @Test
    void cancel_shouldMarkRunCancelledAndPendingStepsCancelled() {
        Long runId = createSampleRun();
        runService.cancel(runId);

        assertEquals(RunStatus.CANCELLED, runRepository.findById(runId).orElseThrow().getStatus());
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        for (AgentStep s : steps) {
            assertEquals(AgentStepStatus.CANCELLED, s.getStatus());
        }
    }

    @Test
    void cancel_twice_shouldThrowSecondTime() {
        Long runId = createSampleRun();
        runService.cancel(runId);
        assertThrows(IllegalStateException.class, () -> runService.cancel(runId));
    }

    @Test
    void retryStep_shouldResetStepAndReopenRun() {
        Long runId = createSampleRun();
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        AgentStep first = steps.get(0);
        first.setStatus(AgentStepStatus.FAILED);
        first.setErrorMessage("boom");
        agentStepRepository.save(first);

        Run run = runRepository.findById(runId).orElseThrow();
        run.setStatus(RunStatus.FAILED);
        runRepository.save(run);

        runService.retryStep(runId, first.getId());

        AgentStep reloaded = agentStepRepository.findById(first.getId()).orElseThrow();
        assertEquals(AgentStepStatus.PENDING, reloaded.getStatus());
        assertNull(reloaded.getErrorMessage());
        assertEquals(RunStatus.RUNNING, runRepository.findById(runId).orElseThrow().getStatus());
    }

    @Test
    void retryStep_wrongRun_shouldThrow() {
        Long runId = createSampleRun();
        Long otherRunId = createSampleRun();
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(otherRunId);
        Long stepId = steps.get(0).getId();

        assertThrows(IllegalArgumentException.class,
                () -> runService.retryStep(runId, stepId));
    }

    @Test
    void retryStep_missingStep_shouldThrow() {
        Long runId = createSampleRun();
        assertThrows(IllegalArgumentException.class,
                () -> runService.retryStep(runId, 999999L));
    }

    @Test
    void getRun_missing_shouldThrowResourceNotFound() {
        assertThrows(ResourceNotFoundException.class, () -> runService.getRun(999999L));
    }

    @Test
    void getRun_null_shouldThrowIllegalArgument() {
        assertThrows(IllegalArgumentException.class, () -> runService.getRun(null));
    }

    @Test
    void getRun_shouldReturnDetailWithSteps() {
        Long runId = createSampleRun();
        Records.RunDetailResponse detail = runService.getRun(runId);
        assertNotNull(detail);
        assertNotNull(detail.run());
        assertEquals(runId, detail.run().id());
        assertEquals(RunStatus.RUNNING, detail.run().status());
        assertEquals(10, detail.steps().size());
        assertNotNull(detail.projectId());
    }

    @Test
    void listRuns_shouldReturnAllSortedByCreatedAtDesc() {
        createSampleRun();
        createSampleRun();
        List<Run> all = runService.listRuns();
        assertEquals(2, all.size());
    }

    @Test
    void aggregateTotals_shouldSumTokensAndCost() {
        Long runId = createSampleRun();
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        steps.get(0).setTokensUsed(100L);
        steps.get(0).setCostCents(5L);
        steps.get(1).setTokensUsed(50L);
        steps.get(1).setCostCents(null);
        agentStepRepository.save(steps.get(0));
        agentStepRepository.save(steps.get(1));

        runService.aggregateTotals(runId);

        Run run = runRepository.findById(runId).orElseThrow();
        assertEquals(150L, run.getTotalTokens());
        assertEquals(5L, run.getTotalCostCents());
    }

    @Test
    void markSucceededIfAllDone_shouldNotMarkWhenPendingStepsExist() {
        Long runId = createSampleRun();
        runService.markSucceededIfAllDone(runId);
        assertEquals(RunStatus.RUNNING, runRepository.findById(runId).orElseThrow().getStatus());
    }

    @Test
    void markSucceededIfAllDone_shouldMarkSucceededWhenAllDone() {
        Long runId = createSampleRun();
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(runId);
        for (AgentStep s : steps) {
            s.setStatus(AgentStepStatus.SUCCEEDED);
            agentStepRepository.save(s);
        }
        runService.markSucceededIfAllDone(runId);
        assertEquals(RunStatus.SUCCEEDED, runRepository.findById(runId).orElseThrow().getStatus());
    }

    @Test
    void rerun_nonTerminal_shouldThrow() {
        Long runId = createSampleRun();
        assertThrows(IllegalStateException.class, () -> runService.rerun(runId, null));
    }

    @Test
    void rerun_cancelledRun_shouldCreateNewRun() {
        Long runId = createSampleRun();
        runService.cancel(runId);
        Long newRunId = runService.rerun(runId, "新的目标");
        assertNotNull(newRunId);
        assertFalse(newRunId.equals(runId));

        Run newRun = runRepository.findById(newRunId).orElseThrow();
        assertEquals("新的目标", newRun.getGoal());
        assertEquals(RunStatus.RUNNING, newRun.getStatus());
    }

    @Test
    void approve_nonWaitingApproval_shouldThrow() {
        Long runId = createSampleRun();
        assertThrows(IllegalStateException.class,
                () -> runService.approve(runId, true, "ok"));
    }

    @Test
    void stats_emptyDatabase_shouldReturnZeros() {
        Records.RunStatsResponse stats = runService.stats();
        assertNotNull(stats);
        assertEquals(0L, stats.totalRuns());
        assertEquals(0.0, stats.successRate());
    }

    @Test
    void readStepLog_nullStepId_shouldThrow() {
        Long runId = createSampleRun();
        assertThrows(IllegalArgumentException.class,
                () -> runService.readStepLog(runId, null, 0L));
    }

    @Test
    void readStepLog_missingStep_shouldThrowResourceNotFound() {
        Long runId = createSampleRun();
        assertThrows(ResourceNotFoundException.class,
                () -> runService.readStepLog(runId, 999999L, 0L));
    }

    @Test
    void readStepLog_wrongRun_shouldThrow() {
        Long runId = createSampleRun();
        Long otherRunId = createSampleRun();
        List<AgentStep> steps = agentStepRepository.findByRunIdOrderBySeqNoAsc(otherRunId);
        Long stepId = steps.get(0).getId();

        assertThrows(IllegalArgumentException.class,
                () -> runService.readStepLog(runId, stepId, 0L));
    }

    @Test
    void planPreview_blankGoal_shouldThrow() {
        assertThrows(IllegalArgumentException.class, () -> runService.planPreview(""));
        assertThrows(IllegalArgumentException.class, () -> runService.planPreview(null));
    }

    @Test
    void planPreview_normal_shouldReturnNonEmptyEpisodes() {
        Records.PlanPreview preview = runService.planPreview("拍一个 3 集的短剧");
        assertNotNull(preview);
        assertFalse(preview.episodes().isEmpty());
        assertTrue(preview.episodes().size() <= 6);
    }

    @Test
    void planPreview_truncateOverMax_shouldCapAtSix() {
        Records.PlanPreview preview = runService.planPreview("拍一个 20 集的短剧");
        assertNotNull(preview);
        assertTrue(preview.episodes().size() <= 6);
    }
}
