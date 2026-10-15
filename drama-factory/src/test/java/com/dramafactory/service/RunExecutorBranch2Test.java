package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mockito;
import org.springframework.core.env.Environment;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * RunExecutor 分支覆盖补充测试（第二轮）。
 * 直接调用 protected advanceRun(Run)，不使用 @Scheduled tick。
 * 纯 Mockito，无 Spring 上下文、无数据库、无 socket。
 */
class RunExecutorBranch2Test {

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

    private RunExecutor executor;

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

        executor = new RunExecutor(
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
                skillService
        );
    }

    private Run runningRun(long id) {
        Run run = new Run();
        run.setId(id);
        run.setStatus(RunStatus.RUNNING);
        return run;
    }

    private AgentStep step(Long id, int seq, AgentType type, AgentStepStatus status, Long episodeId) {
        AgentStep s = new AgentStep();
        s.setId(id);
        s.setSeqNo(seq);
        s.setAgentType(type);
        s.setStatus(status);
        s.setEpisodeId(episodeId);
        return s;
    }

    private Records.GenerateScriptResponse mockScriptResp(String text, int scenes, String source,
                                                          String model, long promptTok, long completionTok,
                                                          String usedSkill) {
        Records.GenerateScriptResponse resp = mock(Records.GenerateScriptResponse.class);
        when(resp.scriptText()).thenReturn(text);
        when(resp.sceneCount()).thenReturn(scenes);
        when(resp.source()).thenReturn(source);
        when(resp.model()).thenReturn(model);
        when(resp.promptTokens()).thenReturn(promptTok);
        when(resp.completionTokens()).thenReturn(completionTok);
        when(resp.usedSkill()).thenReturn(usedSkill);
        return resp;
    }

    // ---------------------------------------------------------------------
    // 149: fresh 非空但 status != RUNNING → 直接 return
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_freshNotRunningStatus_returnsWithoutTouchingSteps() {
        // 覆盖行 126 if (fresh == null || fresh.getStatus() != RunStatus.RUNNING) 的 status 分支
        Run run = runningRun(1L);
        Run fresh = new Run();
        fresh.setId(1L);
        fresh.setStatus(RunStatus.PAUSED);
        when(runRepository.findById(1L)).thenReturn(Optional.of(fresh));

        executor.advanceRun(run);

        verify(agentStepRepository, never()).findByRunIdOrderBySeqNoAsc(anyLong());
        verify(runRepository, never()).save(any(Run.class));
    }

    // ---------------------------------------------------------------------
    // 159: steps 为空列表 → run 置 SUCCEEDED
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_emptySteps_marksRunSucceeded() {
        // 覆盖行 131 if (steps.isEmpty()) 的 true 分支
        Run run = runningRun(2L);
        Run fresh = runningRun(2L);
        when(runRepository.findById(2L)).thenReturn(Optional.of(fresh));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(2L)).thenReturn(new ArrayList<>());

        executor.advanceRun(run);

        assertEquals(RunStatus.SUCCEEDED, fresh.getStatus());
        verify(runRepository).save(fresh);
    }

    // ---------------------------------------------------------------------
    // 229: current != null 走执行路径（SCRIPT PENDING 成功）
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_pendingScriptStep_executesAndSucceeds() {
        // 覆盖行 146 if (current == null) 的 false 分支（有 PENDING 走执行）
        Run run = runningRun(3L);
        Run fresh = runningRun(3L);
        when(runRepository.findById(3L)).thenReturn(Optional.of(fresh));

        AgentStep scriptStep = step(10L, 1, AgentType.SCRIPT, AgentStepStatus.PENDING, 100L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(3L)).thenReturn(List.of(scriptStep));

        Records.GenerateScriptResponse resp = mockScriptResp("hello script", 3, "ai", "gpt", 10L, 20L, null);
        when(scriptService.generate(100L, "ai")).thenReturn(resp);

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.SUCCEEDED, scriptStep.getStatus());
        verify(agentStepRepository, times(3)).save(scriptStep); // RUNNING + SUCCEEDED + recordToolCall 各一次
        verify(scriptService).generate(100L, "ai");
    }

    // ---------------------------------------------------------------------
    // 253: current == null 且并非全部终态成功 → 不 finalizeRun 也不 checkVideoStep
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_noPendingNotAllTerminal_doesNotFinalizeOrCheckVideo() {
        // 覆盖行 148 allMatch(...) 的 false 分支（存在 FAILED step）
        Run run = runningRun(4L);
        Run fresh = runningRun(4L);
        when(runRepository.findById(4L)).thenReturn(Optional.of(fresh));

        // 注意：用 RUNNING 的 SCRIPT（而非 VIDEO），否则 advanceRun 会进 checkVideoStep 分支；
        // 本测试只覆盖"current==null 且 allMatch 为 false → 既不 finalize 也不 checkVideo"
        AgentStep scriptRunning = step(20L, 1, AgentType.SCRIPT, AgentStepStatus.RUNNING, 200L);
        AgentStep failedStep = step(21L, 2, AgentType.EDIT, AgentStepStatus.FAILED, 200L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(4L)).thenReturn(List.of(scriptRunning, failedStep));

        executor.advanceRun(run);

        // 不 finalizeRun
        verify(runRepository, never()).save(any(Run.class));
        // 也不会对 failedStep 做任何 save
        verify(agentStepRepository, never()).save(any(AgentStep.class));
    }

    // ---------------------------------------------------------------------
    // 260 + 267: RUNNING 但非 VIDEO（QC）→ 走 267 兜底 break，run 状态不变
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_runningQcStep_hitsQcFallbackBreakNoVideoCheck() {
        // 覆盖行 155 的 false 分支（RUNNING 且不是 VIDEO）以及行 159 QC 兜底 break
        Run run = runningRun(5L);
        Run fresh = runningRun(5L);
        when(runRepository.findById(5L)).thenReturn(Optional.of(fresh));

        AgentStep qcRunning = step(30L, 1, AgentType.QC, AgentStepStatus.RUNNING, 300L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(5L)).thenReturn(List.of(qcRunning));

        executor.advanceRun(run);

        verify(videoTaskRepository, never()).findByEpisodeId(anyLong());
        verify(runRepository, never()).save(any(Run.class));
    }

    // ---------------------------------------------------------------------
    // 282: QC step + manual-approval=false → 走自动检查（成功）
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_qcManualApprovalFalse_runsAutomaticQcCheck(@TempDir Path tmp) throws IOException {
        // 覆盖行 169 if (QC && isQcManualApproval()) 的 false 分支
        Path file = tmp.resolve("final.mp4");
        Files.write(file, new byte[]{1, 2, 3, 4});

        Run run = runningRun(6L);
        Run fresh = runningRun(6L);
        when(runRepository.findById(6L)).thenReturn(Optional.of(fresh));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep editStep = step(40L, 1, AgentType.EDIT, AgentStepStatus.SUCCEEDED, 400L);
        editStep.setOutputSummary("finalCutId=1, status=DONE, filePath=" + file.toAbsolutePath());
        AgentStep qcStep = step(41L, 2, AgentType.QC, AgentStepStatus.PENDING, 400L);

        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(6L)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.SUCCEEDED, qcStep.getStatus());
        assertTrue(qcStep.getOutputSummary().startsWith("qc=APPROVED"));
    }

    // ---------------------------------------------------------------------
    // 290: executeStep 抛异常走 advanceRun catch 分支（这里用 SCRIPT step 缺少 episodeId 触发）
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_stepThrowsException_marksStepAndRunFailed() {
        // 覆盖行 189-202 try/catch 的 catch 分支（executeStep 内部抛异常）
        Run run = runningRun(7L);
        Run fresh = runningRun(7L);
        when(runRepository.findById(7L)).thenReturn(Optional.of(fresh));

        AgentStep scriptStep = step(50L, 1, AgentType.SCRIPT, AgentStepStatus.PENDING, null);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(7L)).thenReturn(List.of(scriptStep));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.FAILED, scriptStep.getStatus());
        assertEquals(RunStatus.FAILED, fresh.getStatus());
        assertNotNull(scriptStep.getErrorMessage());
    }

    // ---------------------------------------------------------------------
    // 324 + 336: skillId 非空走三参 generate，且 toolCallsJson 含 skillId
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_scriptStepWithSkillId_callsThreeArgGenerateAndRecordsSkill() {
        // 覆盖行 229 三元表达式 skillId 非空分支 + 行 253 if (skillId != null) 的 true 分支
        Run run = runningRun(8L);
        Run fresh = runningRun(8L);
        when(runRepository.findById(8L)).thenReturn(Optional.of(fresh));

        AgentStep scriptStep = step(60L, 1, AgentType.SCRIPT, AgentStepStatus.PENDING, 600L);
        scriptStep.setSkillId(99L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(8L)).thenReturn(List.of(scriptStep));

        Records.GenerateScriptResponse resp = mockScriptResp("s", 1, "ai", "m", 1L, 1L, null);
        when(scriptService.generate(600L, "ai", 99L)).thenReturn(resp);

        executor.advanceRun(run);

        verify(scriptService).generate(600L, "ai", 99L);
        verify(scriptService, never()).generate(anyLong(), anyString());
        assertEquals(AgentStepStatus.SUCCEEDED, scriptStep.getStatus());
        assertNotNull(scriptStep.getToolCallsJson());
        assertTrue(scriptStep.getToolCallsJson().contains("skillId"));
    }

    // ---------------------------------------------------------------------
    // 329: scriptService.generate 返回 null → step FAILED / run FAILED
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_scriptGenerateReturnsNull_marksStepAndRunFailed() {
        // 覆盖行 232 if (resp == null) 的 true 分支
        Run run = runningRun(9L);
        Run fresh = runningRun(9L);
        when(runRepository.findById(9L)).thenReturn(Optional.of(fresh));

        AgentStep scriptStep = step(70L, 1, AgentType.SCRIPT, AgentStepStatus.PENDING, 700L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(9L)).thenReturn(List.of(scriptStep));
        when(scriptService.generate(700L, "ai")).thenReturn(null);

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.FAILED, scriptStep.getStatus());
        assertEquals(RunStatus.FAILED, fresh.getStatus());
    }

    // ---------------------------------------------------------------------
    // 394/395: checkVideoStep 中 createdAt=null 分支
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_videoTaskWithNullCreatedAt_succeedsWithZeroMs() {
        // 覆盖行 408 if (t.getCreatedAt() != null && t.getUpdatedAt() != null) 的 false 分支
        Run run = runningRun(10L);
        Run fresh = runningRun(10L);
        when(runRepository.findById(10L)).thenReturn(Optional.of(fresh));

        AgentStep videoRunning = step(80L, 1, AgentType.VIDEO, AgentStepStatus.RUNNING, 800L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(10L)).thenReturn(List.of(videoRunning));

        VideoTask task = new VideoTask();
        task.setId(1L);
        task.setProvider("mock");
        task.setStatus(VideoTaskStatus.DONE);
        task.setCreatedAt(null);
        task.setUpdatedAt(LocalDateTime.now());
        when(videoTaskRepository.findByEpisodeId(800L)).thenReturn(List.of(task));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.SUCCEEDED, videoRunning.getStatus());
        assertTrue(videoRunning.getOutputSummary().contains("totalMs=0"));
        assertTrue(videoRunning.getOutputSummary().contains("task=1, ms=0"));
    }

    // ---------------------------------------------------------------------
    // 408: provider 非 mock → anyUnknownCost=true，totalCostCents=null
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_videoTaskWithNonMockProvider_marksCostEstimatedAndNullCost() {
        // 覆盖行 414 "mock".equalsIgnoreCase(provider) 的 false 分支 + 行 436 if (anyUnknownCost) true 分支
        Run run = runningRun(11L);
        Run fresh = runningRun(11L);
        when(runRepository.findById(11L)).thenReturn(Optional.of(fresh));

        AgentStep videoRunning = step(90L, 1, AgentType.VIDEO, AgentStepStatus.RUNNING, 900L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(11L)).thenReturn(List.of(videoRunning));

        LocalDateTime t0 = LocalDateTime.now().minusSeconds(2);
        VideoTask task = new VideoTask();
        task.setId(2L);
        task.setProvider("agnes");
        task.setStatus(VideoTaskStatus.DONE);
        task.setCreatedAt(t0);
        task.setUpdatedAt(t0.plusSeconds(1));
        when(videoTaskRepository.findByEpisodeId(900L)).thenReturn(List.of(task));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.SUCCEEDED, videoRunning.getStatus());
        assertTrue(videoRunning.getOutputSummary().contains("totalCostCents=null"));
        assertTrue(Boolean.TRUE.equals(videoRunning.getCostEstimated()));
        assertNull(videoRunning.getCostCents());
    }

    // ---------------------------------------------------------------------
    // 484: runEditStep 里 buildFinalCut 返回 null → step FAILED / run FAILED
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_editBuildFinalCutReturnsNull_marksStepAndRunFailed() {
        // 覆盖行 456 if (resp == null) 的 true 分支
        Run run = runningRun(12L);
        Run fresh = runningRun(12L);
        when(runRepository.findById(12L)).thenReturn(Optional.of(fresh));

        AgentStep editStep = step(100L, 1, AgentType.EDIT, AgentStepStatus.PENDING, 1000L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(12L)).thenReturn(List.of(editStep));
        when(finalCutService.buildFinalCut(1000L)).thenReturn(null);

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.FAILED, editStep.getStatus());
        assertEquals(RunStatus.FAILED, fresh.getStatus());
    }

    // ---------------------------------------------------------------------
    // 504: QC 但同 run 无 EDIT 前置 step → executeStep 抛异常 → step FAILED
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_qcWithoutEditStep_marksStepFailed() {
        // 覆盖行 499 if (editStep == null) 的 true 分支
        Run run = runningRun(13L);
        Run fresh = runningRun(13L);
        when(runRepository.findById(13L)).thenReturn(Optional.of(fresh));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep qcStep = step(110L, 5, AgentType.QC, AgentStepStatus.PENDING, 1100L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(13L)).thenReturn(List.of(qcStep));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.FAILED, qcStep.getStatus());
        assertEquals(RunStatus.FAILED, fresh.getStatus());
    }

    // ---------------------------------------------------------------------
    // 509: EDIT 前置 step 的 outputSummary 为空白 → step FAILED
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_qcWithBlankEditOutput_marksStepFailed() {
        // 覆盖行 504 if (editOutput == null || editOutput.isBlank()) 的 true 分支
        Run run = runningRun(14L);
        Run fresh = runningRun(14L);
        when(runRepository.findById(14L)).thenReturn(Optional.of(fresh));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep editStep = step(120L, 1, AgentType.EDIT, AgentStepStatus.SUCCEEDED, 1200L);
        editStep.setOutputSummary("   ");
        AgentStep qcStep = step(121L, 2, AgentType.QC, AgentStepStatus.PENDING, 1200L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(14L)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.FAILED, qcStep.getStatus());
        assertEquals(RunStatus.FAILED, fresh.getStatus());
    }

    // ---------------------------------------------------------------------
    // 523: extractFilePath 返回 null（无 filePath= 标记）→ step FAILED
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_qcEditOutputWithoutFilePathMarker_marksStepFailed() {
        // 覆盖行 509 if (filePath == null || filePath.isBlank()) 的 true 分支
        Run run = runningRun(15L);
        Run fresh = runningRun(15L);
        when(runRepository.findById(15L)).thenReturn(Optional.of(fresh));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep editStep = step(130L, 1, AgentType.EDIT, AgentStepStatus.SUCCEEDED, 1300L);
        editStep.setOutputSummary("finalCutId=1, status=DONE");
        AgentStep qcStep = step(131L, 2, AgentType.QC, AgentStepStatus.PENDING, 1300L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(15L)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.FAILED, qcStep.getStatus());
        assertNotNull(qcStep.getErrorMessage());
        assertTrue(qcStep.getErrorMessage().contains("未找到成片文件路径"));
        assertEquals(RunStatus.FAILED, fresh.getStatus());
    }

    // ---------------------------------------------------------------------
    // 592(3): anyUnknownCost 三元表达式两臂 —— false 臂：全 mock provider
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_videoTasksAllMockProvider_totalCostZero() {
        // 覆盖行 426 sb.append("totalCostCents=").append(anyUnknownCost ? "null" : totalCost) 的 false 臂
        // + 行 439 else { step.setCostCents(totalCost) } 分支
        Run run = runningRun(16L);
        Run fresh = runningRun(16L);
        when(runRepository.findById(16L)).thenReturn(Optional.of(fresh));

        AgentStep videoRunning = step(140L, 1, AgentType.VIDEO, AgentStepStatus.RUNNING, 1400L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(16L)).thenReturn(List.of(videoRunning));

        LocalDateTime t0 = LocalDateTime.now().minusSeconds(2);
        VideoTask task = new VideoTask();
        task.setId(3L);
        task.setProvider("mock");
        task.setStatus(VideoTaskStatus.DONE);
        task.setCreatedAt(t0);
        task.setUpdatedAt(t0.plusSeconds(1));
        when(videoTaskRepository.findByEpisodeId(1400L)).thenReturn(List.of(task));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.SUCCEEDED, videoRunning.getStatus());
        assertTrue(videoRunning.getOutputSummary().contains("totalCostCents=0"));
        assertEquals(0L, videoRunning.getCostCents());
        assertFalse(Boolean.TRUE.equals(videoRunning.getCostEstimated()));
    }

    // ---------------------------------------------------------------------
    // 598: anyUnknownCost=false → step.costCents=totalCost, costEstimated=false
    // (与上一条同一场景，但显式断言，覆盖 else 分支)
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_videoTasksAllMockProvider_stepCostEstimatedFalse() {
        // 覆盖行 441 step.setCostEstimated(anyUnknownCost) 的 false 分支
        Run run = runningRun(17L);
        Run fresh = runningRun(17L);
        when(runRepository.findById(17L)).thenReturn(Optional.of(fresh));

        AgentStep videoRunning = step(150L, 1, AgentType.VIDEO, AgentStepStatus.RUNNING, 1500L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(17L)).thenReturn(List.of(videoRunning));

        LocalDateTime t0 = LocalDateTime.now().minusSeconds(1);
        VideoTask task = new VideoTask();
        task.setId(4L);
        task.setProvider("MOCK");
        task.setStatus(VideoTaskStatus.DONE);
        task.setCreatedAt(t0);
        task.setUpdatedAt(t0.plus(500, java.time.temporal.ChronoUnit.MILLIS));
        when(videoTaskRepository.findByEpisodeId(1500L)).thenReturn(List.of(task));

        executor.advanceRun(run);

        assertEquals(0L, videoRunning.getCostCents());
        assertFalse(Boolean.TRUE.equals(videoRunning.getCostEstimated()));
    }

    // ---------------------------------------------------------------------
    // 614: finalizeRun 中 tokensUsed == null 的 step
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_finalizeWithNullTokensUsed_skipsAccumulation() {
        // 覆盖行 556 if (s.getTokensUsed() != null) 的 false 分支
        Run run = runningRun(18L);
        Run fresh = runningRun(18L);
        when(runRepository.findById(18L)).thenReturn(Optional.of(fresh));

        AgentStep s1 = step(160L, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 1600L);
        s1.setTokensUsed(null);
        s1.setCostCents(null);
        AgentStep s2 = step(161L, 2, AgentType.BOARD, AgentStepStatus.SUCCEEDED, 1600L);
        s2.setTokensUsed(50L);
        s2.setCostCents(null);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(18L)).thenReturn(List.of(s1, s2));

        executor.advanceRun(run);

        assertEquals(RunStatus.SUCCEEDED, fresh.getStatus());
        assertEquals(50L, fresh.getTotalTokens());
    }

    // ---------------------------------------------------------------------
    // 626: finalizeRun 中 costCents == null 且非 VIDEO 的 step
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_finalizeWithNullCostCentsNonVideo_accumulatesZero() {
        // 覆盖行 559 if (s.getCostCents() != null) 的 false 分支 + 行 561 VIDEO 判断 false 分支
        Run run = runningRun(19L);
        Run fresh = runningRun(19L);
        when(runRepository.findById(19L)).thenReturn(Optional.of(fresh));

        AgentStep s1 = step(170L, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 1700L);
        s1.setTokensUsed(10L);
        s1.setCostCents(null);
        AgentStep s2 = step(171L, 2, AgentType.EDIT, AgentStepStatus.SUCCEEDED, 1700L);
        s2.setTokensUsed(20L);
        s2.setCostCents(5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(19L)).thenReturn(List.of(s1, s2));

        executor.advanceRun(run);

        assertEquals(RunStatus.SUCCEEDED, fresh.getStatus());
        assertEquals(5L, fresh.getTotalCostCents());
    }

    // ---------------------------------------------------------------------
    // 629: VIDEO + costEstimated=true → anyUnknown=true → totalCostCents=null
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_finalizeVideoCostEstimatedTrue_marksTotalCostUnknown() {
        // 覆盖行 561 else if (VIDEO && costEstimated == TRUE) 的 true 分支
        Run run = runningRun(20L);
        Run fresh = runningRun(20L);
        when(runRepository.findById(20L)).thenReturn(Optional.of(fresh));

        AgentStep video = step(180L, 1, AgentType.VIDEO, AgentStepStatus.SUCCEEDED, 1800L);
        video.setTokensUsed(0L);
        video.setCostCents(null);
        video.setCostEstimated(true);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(20L)).thenReturn(List.of(video));

        executor.advanceRun(run);

        assertEquals(RunStatus.SUCCEEDED, fresh.getStatus());
        assertNull(fresh.getTotalCostCents());
    }

    // ---------------------------------------------------------------------
    // 651: isQcManualApproval 中 v 为空串 → 走审批门（true）
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_qcManualApprovalPropertyEmptyString_takesApprovalGate() {
        // 覆盖行 576 if (v == null || v.isBlank()) 的 v.isBlank() true 分支
        Run run = runningRun(21L);
        Run fresh = runningRun(21L);
        when(runRepository.findById(21L)).thenReturn(Optional.of(fresh));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("");

        AgentStep qcStep = step(190L, 1, AgentType.QC, AgentStepStatus.PENDING, 1900L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(21L)).thenReturn(List.of(qcStep));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.RUNNING, qcStep.getStatus());
        assertEquals(RunStatus.WAITING_APPROVAL, fresh.getStatus());
    }

    // ---------------------------------------------------------------------
    // 662: safeMessage 中异常 message 为 null → 使用类简单名
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_exceptionWithNullMessage_usesSimpleClassName() {
        // 覆盖行 665 if (m == null || m.isBlank()) 的 m==null true 分支
        Run run = runningRun(22L);
        Run fresh = runningRun(22L);
        when(runRepository.findById(22L)).thenReturn(Optional.of(fresh));

        AgentStep scriptStep = step(200L, 1, AgentType.SCRIPT, AgentStepStatus.PENDING, 2000L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(22L)).thenReturn(List.of(scriptStep));
        // scriptService.generate 抛 RuntimeException（无 message）
        when(scriptService.generate(2000L, "ai")).thenThrow(new RuntimeException());

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.FAILED, scriptStep.getStatus());
        assertEquals("RuntimeException", scriptStep.getErrorMessage());
        assertTrue(scriptStep.getErrorMessage().length() <= 500);
        assertEquals(RunStatus.FAILED, fresh.getStatus());
    }

    // ---------------------------------------------------------------------
    // 补充：BOARD skillId 非空分支（合并覆盖 324/336 的邻近路径，非清单强制项但增强）
    // 说明：为避免过度扩张，这里保持精简，仅覆盖清单要求。
    // ---------------------------------------------------------------------

    // ---------------------------------------------------------------------
    // 附加覆盖：QC 前置 EDIT 输出含 filePath 但文件不存在 → FAILED 分支
    // （覆盖 runQcStep else 分支，即行 536-544 的失败路径，与 523 相互补充）
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_qcFileDoesNotExist_marksStepAndRunFailed(@TempDir Path tmp) {
        // 覆盖行 523 boolean ok = ... 的 false 分支（文件不存在）
        Run run = runningRun(23L);
        Run fresh = runningRun(23L);
        when(runRepository.findById(23L)).thenReturn(Optional.of(fresh));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        Path missing = tmp.resolve("missing.mp4");
        AgentStep editStep = step(210L, 1, AgentType.EDIT, AgentStepStatus.SUCCEEDED, 2100L);
        editStep.setOutputSummary("finalCutId=9, status=DONE, filePath=" + missing.toAbsolutePath());
        AgentStep qcStep = step(211L, 2, AgentType.QC, AgentStepStatus.PENDING, 2100L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(23L)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.FAILED, qcStep.getStatus());
        assertNotNull(qcStep.getErrorMessage());
        assertTrue(qcStep.getErrorMessage().contains("文件不存在或为空"));
        assertEquals(RunStatus.FAILED, fresh.getStatus());
    }

    // ---------------------------------------------------------------------
    // 附加覆盖：VIDEO 任务存在 FAILED → step FAILED（checkVideoStep 失败分支）
    // 对应行 378 if (firstFailed.isPresent()) 的 true 分支
    // ---------------------------------------------------------------------
    @Test
    void advanceRun_videoTaskFailed_marksStepAndRunFailed() {
        // 覆盖行 378 if (firstFailed.isPresent()) 的 true 分支
        Run run = runningRun(24L);
        Run fresh = runningRun(24L);
        when(runRepository.findById(24L)).thenReturn(Optional.of(fresh));

        AgentStep videoRunning = step(220L, 1, AgentType.VIDEO, AgentStepStatus.RUNNING, 2200L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(24L)).thenReturn(List.of(videoRunning));

        VideoTask failed = new VideoTask();
        failed.setId(5L);
        failed.setProvider("mock");
        failed.setStatus(VideoTaskStatus.FAILED);
        failed.setErrorMessage("boom");
        when(videoTaskRepository.findByEpisodeId(2200L)).thenReturn(List.of(failed));

        executor.advanceRun(run);

        assertEquals(AgentStepStatus.FAILED, videoRunning.getStatus());
        assertEquals(RunStatus.FAILED, fresh.getStatus());
        assertEquals("boom", videoRunning.getErrorMessage());
    }
}
