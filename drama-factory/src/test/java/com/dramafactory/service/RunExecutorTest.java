
package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import org.junit.jupiter.api.io.TempDir;


import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.core.env.Environment;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * {@link RunExecutor} 纯 Mockito 单元测试：零数据库、零 socket、零外网。
 * <p>
 * 测试类与被测类同包（com.dramafactory.service），因此可直接调用 protected 的
 * {@code advanceRun(Run)}；不测 @Scheduled 的定时触发，只直接调用。
 */
class RunExecutorTest {

    private static final Long RUN_ID = 1L;
    private static final Long EPISODE_ID = 7L;

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
        executor = new RunExecutor(runRepository, agentStepRepository, videoTaskRepository,
                scriptService, scriptSplitterService, videoTaskService, finalCutService,
                runLogService, environment, objectMapper, skillService);
    }

    /** 构造一个 RUNNING 状态的 Run，并 stub findById 返回它。 */
    private Run runningRun() {
        Run run = new Run();
        run.setId(RUN_ID);
        run.setStatus(RunStatus.RUNNING);
        when(runRepository.findById(RUN_ID)).thenReturn(Optional.of(run));
        return run;
    }

    /** 构造一个 PENDING 的 AgentStep。 */
    private AgentStep pendingStep(Long id, Integer seqNo, AgentType type) {
        AgentStep step = new AgentStep();
        step.setId(id);
        step.setSeqNo(seqNo);
        step.setAgentType(type);
        step.setStatus(AgentStepStatus.PENDING);
        step.setEpisodeId(EPISODE_ID);
        return step;
    }

    /** 捕获最后一次 agentStepRepository.save 的 step。 */
    private AgentStep captureLastSavedStep() {
        ArgumentCaptor<AgentStep> captor = ArgumentCaptor.forClass(AgentStep.class);
        verify(agentStepRepository, atLeastOnce()).save(captor.capture());
        return captor.getValue();
    }

    /** 捕获最后一次 runRepository.save 的 run。 */
    private Run captureLastSavedRun() {
        ArgumentCaptor<Run> captor = ArgumentCaptor.forClass(Run.class);
        verify(runRepository, atLeastOnce()).save(captor.capture());
        return captor.getValue();
    }

    // 1. tick：没有 RUNNING 的 Run 时什么都不做
    @Test
    void tick_noRunningRuns_doesNothing() {
        when(runRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING)).thenReturn(List.of());

        executor.tick();

        verify(agentStepRepository, never()).save(any());
    }

    // 2. SCRIPT 步骤正常路径：generate 被调用，step 最终 SUCCEEDED
    @Test
    void advanceRun_scriptStepHappyPath() {
        Run run = runningRun();
        AgentStep step = pendingStep(11L, 1, AgentType.SCRIPT);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        when(scriptService.generate(EPISODE_ID, "ai"))
                .thenReturn(new Records.GenerateScriptResponse(EPISODE_ID, 3, "剧本正文", "ai",
                        "Deepseek-v4-flash", 100L, 1000L, 2000L, null));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        assertEquals("剧本正文", saved.getOutputSummary());
        verify(scriptService).generate(EPISODE_ID, "ai");
        verify(runLogService, atLeastOnce()).append(eq(RUN_ID), any(), anyString());
    }

    // 3. BOARD 步骤读取前置 SCRIPT 的 outputSummary 作为剧本原文
    @Test
    void advanceRun_boardStepReadsPreviousScriptOutput() {
        Run run = runningRun();
        AgentStep scriptStep = new AgentStep();
        scriptStep.setId(21L);
        scriptStep.setSeqNo(1);
        scriptStep.setAgentType(AgentType.SCRIPT);
        scriptStep.setStatus(AgentStepStatus.SUCCEEDED);
        scriptStep.setEpisodeId(EPISODE_ID);
        scriptStep.setOutputSummary("剧本正文");

        AgentStep boardStep = pendingStep(22L, 2, AgentType.BOARD);

        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID))
                .thenReturn(List.of(scriptStep, boardStep));
        when(scriptSplitterService.splitFromScript(EPISODE_ID, "剧本正文")).thenReturn(List.of());

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        assertEquals("shotCount=0, shotNos=", saved.getOutputSummary());
        verify(scriptSplitterService).splitFromScript(EPISODE_ID, "剧本正文");
    }

    // 4. QC 人工审批门：run 置 WAITING_APPROVAL，step 保持 RUNNING
    @Test
    void advanceRun_qcManualApprovalParksRun() {
        Run run = runningRun();
        AgentStep step = pendingStep(31L, 1, AgentType.QC);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("true");

        executor.advanceRun(run);

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.WAITING_APPROVAL, savedRun.getStatus());

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.RUNNING, savedStep.getStatus());

        verify(finalCutService, never()).buildFinalCut(any());
    }

    // 5. 步骤抛异常：step FAILED 且 errorMessage 为 "boom"，run FAILED
    @Test
    void advanceRun_stepExceptionMarksFailed() {
        Run run = runningRun();
        AgentStep step = pendingStep(41L, 1, AgentType.SCRIPT);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(scriptService.generate(any(), any())).thenThrow(new RuntimeException("boom"));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertEquals("boom", savedStep.getErrorMessage());

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.FAILED, savedRun.getStatus());
        assertEquals("boom", savedRun.getErrorMessage());
    }

    // 6. VIDEO 步骤提交后保持 RUNNING，不结束，也不 save run
    @Test
    void advanceRun_videoStepStaysRunning() {
        Run run = runningRun();
        AgentStep step = pendingStep(51L, 1, AgentType.VIDEO);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(videoTaskService.submitAllForEpisode(EPISODE_ID)).thenReturn(List.of());

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.RUNNING, saved.getStatus());
        verify(runRepository, never()).save(any());
    }

    // 7. VIDEO 跨 tick 检查：所有任务 DONE，step 最终 SUCCEEDED
    @Test
    void advanceRun_videoCheckAllDone() {
        Run run = runningRun();
        AgentStep videoStep = new AgentStep();
        videoStep.setId(61L);
        videoStep.setSeqNo(1);
        videoStep.setAgentType(AgentType.VIDEO);
        videoStep.setStatus(AgentStepStatus.RUNNING);
        videoStep.setEpisodeId(EPISODE_ID);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(videoStep));

        VideoTask task = new VideoTask();
        task.setId(611L);
        task.setStatus(VideoTaskStatus.DONE);
        task.setProvider("mock");
        when(videoTaskRepository.findByEpisodeId(EPISODE_ID)).thenReturn(List.of(task));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
    }

    // 8. VIDEO 跨 tick 检查：有 FAILED 任务，step FAILED、run FAILED，run.errorMessage 含原因
    @Test
    void advanceRun_videoCheckFailed() {
        Run run = runningRun();
        AgentStep videoStep = new AgentStep();
        videoStep.setId(71L);
        videoStep.setSeqNo(1);
        videoStep.setAgentType(AgentType.VIDEO);
        videoStep.setStatus(AgentStepStatus.RUNNING);
        videoStep.setEpisodeId(EPISODE_ID);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(videoStep));

        VideoTask task = new VideoTask();
        task.setId(711L);
        task.setStatus(VideoTaskStatus.FAILED);
        task.setProvider("mock");
        task.setErrorMessage("gpu 爆了");
        when(videoTaskRepository.findByEpisodeId(EPISODE_ID)).thenReturn(List.of(task));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.FAILED, savedRun.getStatus());
        assertNotNull(savedRun.getErrorMessage());
        assertTrue(savedRun.getErrorMessage().contains("gpu 爆了"));
    }

    // 9. 所有 step 终态 SUCCEEDED：run 汇总 token 后置 SUCCEEDED
    @Test
    void advanceRun_allSucceededFinalizesRun() {
        Run run = runningRun();

        AgentStep s1 = new AgentStep();
        s1.setId(81L);
        s1.setSeqNo(1);
        s1.setAgentType(AgentType.SCRIPT);
        s1.setStatus(AgentStepStatus.SUCCEEDED);
        s1.setEpisodeId(EPISODE_ID);
        s1.setTokensUsed(100L);

        AgentStep s2 = new AgentStep();
        s2.setId(82L);
        s2.setSeqNo(2);
        s2.setAgentType(AgentType.BOARD);
        s2.setStatus(AgentStepStatus.SUCCEEDED);
        s2.setEpisodeId(EPISODE_ID);
        s2.setTokensUsed(200L);

        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(s1, s2));

        executor.advanceRun(run);

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.SUCCEEDED, savedRun.getStatus());
        assertEquals(300L, savedRun.getTotalTokens());
        assertNull(savedRun.getErrorMessage());
        verify(runLogService).append(eq(RUN_ID), eq(0), anyString());
    }

    // 10. tick 吞掉 repository 异常，不向外抛
    @Test
    void tick_swallowsRepositoryException() {
        when(runRepository.findByStatusOrderByCreatedAtAsc(any()))
                .thenThrow(new RuntimeException("db down"));

        assertDoesNotThrow(() -> executor.tick());
    }

    // E1. findById 返回空：run 已不存在，直接返回，不落库
    @Test
    void advanceRun_runGoneFromDb_returns() {
        when(runRepository.findById(RUN_ID)).thenReturn(Optional.empty());
        Run run = new Run();
        run.setId(RUN_ID);

        executor.advanceRun(run);

        verify(agentStepRepository, never()).save(any());
    }

    // E2. run 已不是 RUNNING：直接返回，不查 steps
    @Test
    void advanceRun_runNoLongerRunning_returns() {
        Run run = runningRun();
        run.setStatus(RunStatus.SUCCEEDED);

        executor.advanceRun(run);

        verify(agentStepRepository, never()).findByRunIdOrderBySeqNoAsc(any());
    }

    // E3. 没有任何 step：run 直接置 SUCCEEDED
    @Test
    void advanceRun_noSteps_marksSucceeded() {
        Run run = runningRun();
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of());

        executor.advanceRun(run);

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.SUCCEEDED, savedRun.getStatus());
    }

    // E4. QC step 处于 RUNNING（无 PENDING）：本轮不推进，不落库
    @Test
    void advanceRun_runningQcStepWithoutPending_waits() {
        Run run = runningRun();
        AgentStep qcStep = pendingStep(41L, 5, AgentType.QC);
        qcStep.setStatus(AgentStepStatus.RUNNING);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(qcStep));

        executor.advanceRun(run);

        verify(agentStepRepository, never()).save(any());
    }

    // E6. step 缺少 agentType：step FAILED 且 errorMessage 含"缺少 agentType"，run FAILED
    @Test
    void advanceRun_nullAgentType_marksStepFailed() {
        Run run = runningRun();
        AgentStep step = pendingStep(42L, 1, AgentType.SCRIPT);
        step.setAgentType(null);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertNotNull(savedStep.getErrorMessage());
        assertTrue(savedStep.getErrorMessage().contains("缺少 agentType"));

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.FAILED, savedRun.getStatus());
    }

    // E7. SCRIPT generate 返回 null：step FAILED 且 errorMessage 含"返回为空"
    @Test
    void advanceRun_scriptNullResponse_marksFailed() {
        Run run = runningRun();
        AgentStep step = pendingStep(43L, 1, AgentType.SCRIPT);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        when(scriptService.generate(EPISODE_ID, "ai")).thenReturn(null);

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertNotNull(savedStep.getErrorMessage());
        assertTrue(savedStep.getErrorMessage().contains("返回为空"));
    }

    // E8. SCRIPT step 缺少 episodeId：step FAILED 且 errorMessage 含"缺少 episodeId"
    @Test
    void advanceRun_scriptMissingEpisodeId_marksFailed() {
        Run run = runningRun();
        AgentStep step = pendingStep(44L, 1, AgentType.SCRIPT);
        step.setEpisodeId(null);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertNotNull(savedStep.getErrorMessage());
        assertTrue(savedStep.getErrorMessage().contains("缺少 episodeId"));
    }

    // E9. BOARD 找不到前置 SCRIPT：step FAILED 且 errorMessage 含"找不到前置 SCRIPT"
    @Test
    void advanceRun_boardMissingScriptStep_marksFailed() {
        Run run = runningRun();
        AgentStep boardStep = pendingStep(45L, 1, AgentType.BOARD);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(boardStep));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertNotNull(savedStep.getErrorMessage());
        assertTrue(savedStep.getErrorMessage().contains("找不到前置 SCRIPT"));
    }

    // E10. BOARD 前置 SCRIPT 输出为空白：step FAILED 且 errorMessage 含"输出为空"
    @Test
    void advanceRun_boardBlankScriptOutput_marksFailed() {
        Run run = runningRun();
        AgentStep scriptStep = new AgentStep();
        scriptStep.setId(46L);
        scriptStep.setSeqNo(1);
        scriptStep.setAgentType(AgentType.SCRIPT);
        scriptStep.setStatus(AgentStepStatus.SUCCEEDED);
        scriptStep.setEpisodeId(EPISODE_ID);
        scriptStep.setOutputSummary(" ");

        AgentStep boardStep = pendingStep(47L, 2, AgentType.BOARD);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID))
                .thenReturn(List.of(scriptStep, boardStep));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertNotNull(savedStep.getErrorMessage());
        assertTrue(savedStep.getErrorMessage().contains("输出为空"));
    }

    // E11. splitFromScript 返回 null：step FAILED 且 errorMessage 含"返回为空"
    @Test
    void advanceRun_boardNullShots_marksFailed() {
        Run run = runningRun();
        AgentStep scriptStep = new AgentStep();
        scriptStep.setId(48L);
        scriptStep.setSeqNo(1);
        scriptStep.setAgentType(AgentType.SCRIPT);
        scriptStep.setStatus(AgentStepStatus.SUCCEEDED);
        scriptStep.setEpisodeId(EPISODE_ID);
        scriptStep.setOutputSummary("剧本正文");

        AgentStep boardStep = pendingStep(49L, 2, AgentType.BOARD);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID))
                .thenReturn(List.of(scriptStep, boardStep));
        when(scriptSplitterService.splitFromScript(EPISODE_ID, "剧本正文")).thenReturn(null);

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertNotNull(savedStep.getErrorMessage());
        assertTrue(savedStep.getErrorMessage().contains("返回为空"));
    }

    // E12. submitAllForEpisode 返回 null：step FAILED 且 errorMessage 含"返回为空"
    @Test
    void advanceRun_videoNullTasks_marksFailed() {
        Run run = runningRun();
        AgentStep step = pendingStep(50L, 1, AgentType.VIDEO);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(videoTaskService.submitAllForEpisode(EPISODE_ID)).thenReturn(null);

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertNotNull(savedStep.getErrorMessage());
        assertTrue(savedStep.getErrorMessage().contains("返回为空"));
    }

    // E13. EDIT 正常路径：step SUCCEEDED 且 outputSummary 含 finalCutId=9
    @Test
    void advanceRun_editStepHappyPath() {
        Run run = runningRun();
        AgentStep step = pendingStep(51L, 1, AgentType.EDIT);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        when(finalCutService.buildFinalCut(EPISODE_ID))
                .thenReturn(new Records.FinalCutResponse(9L, EPISODE_ID, "t", "/tmp/x.mp4", "x.mp4",
                        FinalCutStatus.READY, "已完成", 60.0, null, null, null, null, null, null));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, savedStep.getStatus());
        assertNotNull(savedStep.getOutputSummary());
        assertTrue(savedStep.getOutputSummary().contains("finalCutId=9"));
    }

    // E14. buildFinalCut 返回 null：step FAILED 且 errorMessage 含"返回为空"
    @Test
    void advanceRun_editNullResponse_marksFailed() {
        Run run = runningRun();
        AgentStep step = pendingStep(52L, 1, AgentType.EDIT);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        when(finalCutService.buildFinalCut(EPISODE_ID)).thenReturn(null);

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertNotNull(savedStep.getErrorMessage());
        assertTrue(savedStep.getErrorMessage().contains("返回为空"));
    }


    // Q1. QC 自动审批：成片文件存在，QC step SUCCEEDED
    @Test
    void advanceRun_qcAutoApproval_fileExists_succeeds(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("final.mp4");
        Files.write(f, "data".getBytes());
        Run run = runningRun();
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep editStep = new AgentStep();
        editStep.setId(51L);
        editStep.setSeqNo(4);
        editStep.setAgentType(AgentType.EDIT);
        editStep.setStatus(AgentStepStatus.SUCCEEDED);
        editStep.setEpisodeId(EPISODE_ID);
        editStep.setOutputSummary("finalCutId=9, status=READY, filePath=" + f.toString());

        AgentStep qcStep = pendingStep(52L, 5, AgentType.QC);

        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        assertTrue(saved.getOutputSummary().contains("qc=APPROVED"));
    }

    // Q2. QC 自动审批：文件不存在，QC step FAILED、run FAILED
    @Test
    void advanceRun_qcMissingFile_fails(@TempDir Path dir) throws Exception {
        Path missing = dir.resolve("missing.mp4");
        Run run = runningRun();
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep editStep = new AgentStep();
        editStep.setId(53L);
        editStep.setSeqNo(4);
        editStep.setAgentType(AgentType.EDIT);
        editStep.setStatus(AgentStepStatus.SUCCEEDED);
        editStep.setEpisodeId(EPISODE_ID);
        editStep.setOutputSummary("finalCutId=9, status=READY, filePath=" + missing.toString());

        AgentStep qcStep = pendingStep(54L, 5, AgentType.QC);

        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, saved.getStatus());
        assertTrue(saved.getErrorMessage().contains("文件不存在或为空"));

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.FAILED, savedRun.getStatus());
    }

    // Q3. QC 自动审批：EDIT 输出无 filePath，QC step FAILED
    @Test
    void advanceRun_qcNoFilePathInEditOutput_fails() {
        Run run = runningRun();
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep editStep = new AgentStep();
        editStep.setId(55L);
        editStep.setSeqNo(4);
        editStep.setAgentType(AgentType.EDIT);
        editStep.setStatus(AgentStepStatus.SUCCEEDED);
        editStep.setEpisodeId(EPISODE_ID);
        editStep.setOutputSummary("finalCutId=9, status=READY");

        AgentStep qcStep = pendingStep(56L, 5, AgentType.QC);

        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, saved.getStatus());
        assertTrue(saved.getErrorMessage().contains("未找到成片文件路径"));
    }

    // Q4. QC 自动审批：找不到前置 EDIT step，QC step FAILED
    @Test
    void advanceRun_qcMissingEditStep_marksFailed() {
        Run run = runningRun();
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep qcStep = pendingStep(57L, 5, AgentType.QC);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(qcStep));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, saved.getStatus());
        assertTrue(saved.getErrorMessage().contains("找不到前置 EDIT"));
    }

    // Q5. QC 自动审批：EDIT 输出为空白，QC step FAILED
    @Test
    void advanceRun_qcBlankEditOutput_marksFailed() {
        Run run = runningRun();
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep editStep = new AgentStep();
        editStep.setId(58L);
        editStep.setSeqNo(4);
        editStep.setAgentType(AgentType.EDIT);
        editStep.setStatus(AgentStepStatus.SUCCEEDED);
        editStep.setEpisodeId(EPISODE_ID);
        editStep.setOutputSummary(" ");

        AgentStep qcStep = pendingStep(59L, 5, AgentType.QC);

        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, saved.getStatus());
        assertTrue(saved.getErrorMessage().contains("输出为空"));
    }

    // C1. VIDEO 跨 tick 检查：无任务时抛 IllegalStateException
    @Test
    void advanceRun_videoStepNoTasks_throws() {
        Run run = runningRun();

        AgentStep videoStep = new AgentStep();
        videoStep.setId(61L);
        videoStep.setSeqNo(1);
        videoStep.setAgentType(AgentType.VIDEO);
        videoStep.setStatus(AgentStepStatus.RUNNING);
        videoStep.setEpisodeId(EPISODE_ID);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(videoStep));

        when(videoTaskRepository.findByEpisodeId(EPISODE_ID)).thenReturn(List.of());

        assertThrows(IllegalStateException.class, () -> executor.advanceRun(run));
    }

    // C2. VIDEO 失败且 errorMessage 为 null，用默认信息
    @Test
    void advanceRun_videoFailedWithNullErrorMessage_marksFailed() {
        Run run = runningRun();

        AgentStep videoStep = new AgentStep();
        videoStep.setId(62L);
        videoStep.setSeqNo(1);
        videoStep.setAgentType(AgentType.VIDEO);
        videoStep.setStatus(AgentStepStatus.RUNNING);
        videoStep.setEpisodeId(EPISODE_ID);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(videoStep));

        VideoTask t = new VideoTask();
        t.setStatus(VideoTaskStatus.FAILED);
        t.setErrorMessage(null);
        when(videoTaskRepository.findByEpisodeId(EPISODE_ID)).thenReturn(List.of(t));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, savedStep.getStatus());
        assertEquals("video task failed", savedStep.getErrorMessage());

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.FAILED, savedRun.getStatus());
    }

    // C3. VIDEO 全 DONE 且非 mock provider，成本未知
    @Test
    void advanceRun_videoAllDoneNonMockProvider_unknownCost() {
        Run run = runningRun();

        AgentStep videoStep = new AgentStep();
        videoStep.setId(63L);
        videoStep.setSeqNo(1);
        videoStep.setAgentType(AgentType.VIDEO);
        videoStep.setStatus(AgentStepStatus.RUNNING);
        videoStep.setEpisodeId(EPISODE_ID);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(videoStep));

        VideoTask t = new VideoTask();
        t.setId(701L);
        t.setStatus(VideoTaskStatus.DONE);
        t.setProvider("agnes");
        t.setCreatedAt(LocalDateTime.now().minusSeconds(5));
        t.setUpdatedAt(LocalDateTime.now());
        when(videoTaskRepository.findByEpisodeId(EPISODE_ID)).thenReturn(List.of(t));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        assertNull(saved.getCostCents());
        assertEquals(Boolean.TRUE, saved.getCostEstimated());
    }

    // C4. VIDEO 全 DONE 且任务无时间戳，latency 为 0
    @Test
    void advanceRun_videoAllDoneTaskWithoutTimestamps_succeeds() {
        Run run = runningRun();

        AgentStep videoStep = new AgentStep();
        videoStep.setId(64L);
        videoStep.setSeqNo(1);
        videoStep.setAgentType(AgentType.VIDEO);
        videoStep.setStatus(AgentStepStatus.RUNNING);
        videoStep.setEpisodeId(EPISODE_ID);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(videoStep));

        VideoTask t = new VideoTask();
        t.setStatus(VideoTaskStatus.DONE);
        t.setProvider("mock");
        when(videoTaskRepository.findByEpisodeId(EPISODE_ID)).thenReturn(List.of(t));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        assertEquals(0L, saved.getLatencyMs());
    }

    // F1. 汇总时 VIDEO 成本未知，run 总成本置 null
    @Test
    void advanceRun_finalizeWithUnknownVideoCost_nullsTotalCost() {
        Run run = runningRun();

        AgentStep s1 = new AgentStep();
        s1.setId(91L);
        s1.setSeqNo(1);
        s1.setAgentType(AgentType.SCRIPT);
        s1.setStatus(AgentStepStatus.SUCCEEDED);
        s1.setEpisodeId(EPISODE_ID);
        s1.setTokensUsed(100L);
        s1.setCostCents(50L);

        AgentStep s2 = new AgentStep();
        s2.setId(92L);
        s2.setSeqNo(2);
        s2.setAgentType(AgentType.VIDEO);
        s2.setStatus(AgentStepStatus.SUCCEEDED);
        s2.setEpisodeId(EPISODE_ID);
        s2.setTokensUsed(null);
        s2.setCostCents(null);
        s2.setCostEstimated(true);

        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(s1, s2));

        executor.advanceRun(run);

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.SUCCEEDED, savedRun.getStatus());
        assertEquals(100L, savedRun.getTotalTokens());
        assertNull(savedRun.getTotalCostCents());
    }

    // H1. QC 人工审批配置为空白，默认启用，run WAITING_APPROVAL
    @Test
    void advanceRun_qcManualApprovalBlank_waits() {
        Run run = runningRun();
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn(" ");

        AgentStep qcStep = pendingStep(95L, 5, AgentType.QC);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(qcStep));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.RUNNING, savedStep.getStatus());

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.WAITING_APPROVAL, savedRun.getStatus());
    }

    // H2. 步骤异常超长信息被截断到 500 字符
    @Test
    void advanceRun_stepExceptionLongMessage_truncated() {
        Run run = runningRun();
        AgentStep step = pendingStep(96L, 1, AgentType.SCRIPT);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(scriptService.generate(eq(EPISODE_ID), eq("ai")))
                .thenThrow(new RuntimeException("e".repeat(600)));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, saved.getStatus());
        assertEquals(500, saved.getErrorMessage().length());
    }

    // H3. 步骤异常无 message 时用类名
    @Test
    void advanceRun_stepExceptionNullMessage_usesClassName() {
        Run run = runningRun();
        AgentStep step = pendingStep(97L, 1, AgentType.SCRIPT);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(scriptService.generate(eq(EPISODE_ID), eq("ai")))
                .thenThrow(new RuntimeException());

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, saved.getStatus());
        assertEquals("RuntimeException", saved.getErrorMessage());
    }

    // N1. steps 里只有一个 FAILED 步骤：current==null 且非全终态成功、无 RUNNING VIDEO/QC → 直接返回
    @Test
    void advanceRun_singleFailedStepNoPending_returns() {
        Run run = runningRun();
        AgentStep failed = new AgentStep();
        failed.setId(101L);
        failed.setSeqNo(1);
        failed.setAgentType(AgentType.SCRIPT);
        failed.setStatus(AgentStepStatus.FAILED);
        failed.setEpisodeId(EPISODE_ID);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(failed));

        assertDoesNotThrow(() -> executor.advanceRun(run));

        verify(agentStepRepository, never()).save(any());
        verify(runRepository, never()).save(any());
    }

    // N2. tick：findByStatusOrderByCreatedAtAsc 返回 [runningRun]，但内层 findById 抛异常 → 不向外抛
    @Test
    void tick_innerFindByIdThrows_swallowed() {
        Run run = new Run();
        run.setId(RUN_ID);
        run.setStatus(RunStatus.RUNNING);
        when(runRepository.findByStatusOrderByCreatedAtAsc(RunStatus.RUNNING)).thenReturn(List.of(run));
        when(runRepository.findById(RUN_ID)).thenThrow(new RuntimeException("inner db down"));

        assertDoesNotThrow(() -> executor.tick());
    }

    // N3. isQcManualApproval：environment.getProperty 不 stub 返回 null → 默认启用人工审批
    @Test
    void advanceRun_qcManualApprovalPropertyNull_defaultsToApproval() {
        Run run = runningRun();
        AgentStep qcStep = pendingStep(102L, 1, AgentType.QC);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(qcStep));

        executor.advanceRun(run);

        AgentStep savedStep = captureLastSavedStep();
        assertEquals(AgentStepStatus.RUNNING, savedStep.getStatus());

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.WAITING_APPROVAL, savedRun.getStatus());
    }

    // N4. runQcStep：EDIT 输出 filePath 指向 0 字节文件 → QC FAILED 且 errorMessage 含"文件不存在或为空"
    @Test
    void advanceRun_qcEmptyFile_fails(@TempDir Path dir) throws Exception {
        Path empty = dir.resolve("empty.mp4");
        Files.write(empty, new byte[0]);
        Run run = runningRun();
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep editStep = new AgentStep();
        editStep.setId(103L);
        editStep.setSeqNo(4);
        editStep.setAgentType(AgentType.EDIT);
        editStep.setStatus(AgentStepStatus.SUCCEEDED);
        editStep.setEpisodeId(EPISODE_ID);
        editStep.setOutputSummary("finalCutId=9, status=READY, filePath=" + empty.toString());

        AgentStep qcStep = pendingStep(104L, 5, AgentType.QC);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, saved.getStatus());
        assertTrue(saved.getErrorMessage().contains("文件不存在或为空"));

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.FAILED, savedRun.getStatus());
    }

    // N5. runEditStep：buildFinalCut 返回 filePath=null → EDIT SUCCEEDED 且 outputSummary 不含 "filePath="
    @Test
    void advanceRun_editNullFilePath_noFilePathInSummary() {
        Run run = runningRun();
        AgentStep step = pendingStep(105L, 1, AgentType.EDIT);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        when(finalCutService.buildFinalCut(EPISODE_ID))
                .thenReturn(new Records.FinalCutResponse(9L, EPISODE_ID, "t", null, "x.mp4",
                        FinalCutStatus.READY, "已完成", 60.0, null, null, null, null, null, null));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        assertNotNull(saved.getOutputSummary());
        assertTrue(saved.getOutputSummary().contains("finalCutId=9"));
        assertTrue(!saved.getOutputSummary().contains("filePath="));
    }

    // N6. checkVideoStep：findByEpisodeId 返回 null → advanceRun 抛 IllegalStateException
    @Test
    void advanceRun_videoTasksNull_throws() {
        Run run = runningRun();
        AgentStep videoStep = new AgentStep();
        videoStep.setId(106L);
        videoStep.setSeqNo(1);
        videoStep.setAgentType(AgentType.VIDEO);
        videoStep.setStatus(AgentStepStatus.RUNNING);
        videoStep.setEpisodeId(EPISODE_ID);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(videoStep));
        when(videoTaskRepository.findByEpisodeId(EPISODE_ID)).thenReturn(null);

        assertThrows(IllegalStateException.class, () -> executor.advanceRun(run));
    }

    // N7. safeMessage：scriptService.generate 抛 new RuntimeException("   ") → errorMessage 为 "RuntimeException"
    @Test
    void advanceRun_stepExceptionBlankMessage_usesClassName() {
        Run run = runningRun();
        AgentStep step = pendingStep(107L, 1, AgentType.SCRIPT);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(scriptService.generate(eq(EPISODE_ID), eq("ai")))
                .thenThrow(new RuntimeException("   "));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.FAILED, saved.getStatus());
        assertEquals("RuntimeException", saved.getErrorMessage());
    }

    // N8. findPreviousStepOfType：seqNo=null 的候选被跳过，匹配到 seqNo=1 的 SCRIPT → BOARD SUCCEEDED
    @Test
    void advanceRun_boardSkipsNullSeqNoPreviousScript_succeeds() {
        Run run = runningRun();
        AgentStep scriptNullSeq = new AgentStep();
        scriptNullSeq.setId(108L);
        scriptNullSeq.setSeqNo(null);
        scriptNullSeq.setAgentType(AgentType.SCRIPT);
        scriptNullSeq.setStatus(AgentStepStatus.SUCCEEDED);
        scriptNullSeq.setEpisodeId(EPISODE_ID);
        scriptNullSeq.setOutputSummary("无用");

        AgentStep scriptSeq1 = new AgentStep();
        scriptSeq1.setId(109L);
        scriptSeq1.setSeqNo(1);
        scriptSeq1.setAgentType(AgentType.SCRIPT);
        scriptSeq1.setStatus(AgentStepStatus.SUCCEEDED);
        scriptSeq1.setEpisodeId(EPISODE_ID);
        scriptSeq1.setOutputSummary("剧本正文");

        AgentStep boardStep = pendingStep(110L, 2, AgentType.BOARD);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID))
                .thenReturn(List.of(scriptNullSeq, scriptSeq1, boardStep));
        when(scriptSplitterService.splitFromScript(EPISODE_ID, "剧本正文")).thenReturn(List.of());

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        assertEquals("shotCount=0, shotNos=", saved.getOutputSummary());
        verify(scriptSplitterService).splitFromScript(EPISODE_ID, "剧本正文");
    }

    // N9. extractFilePath：EDIT outputSummary 以 filePath 结尾（无逗号）→ 走 editOutput.length() 分支，QC SUCCEEDED
    @Test
    void advanceRun_qcFilePathAtEnd_succeeds(@TempDir Path dir) throws Exception {
        Path f = dir.resolve("final.mp4");
        Files.write(f, "data".getBytes());
        Run run = runningRun();
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");

        AgentStep editStep = new AgentStep();
        editStep.setId(111L);
        editStep.setSeqNo(4);
        editStep.setAgentType(AgentType.EDIT);
        editStep.setStatus(AgentStepStatus.SUCCEEDED);
        editStep.setEpisodeId(EPISODE_ID);
        editStep.setOutputSummary("finalCutId=9, status=READY, filePath=" + f.toString());

        AgentStep qcStep = pendingStep(112L, 5, AgentType.QC);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(editStep, qcStep));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        assertTrue(saved.getOutputSummary().contains("qc=APPROVED"));
    }

    // N10. recordToolCall：SCRIPT 预置合法 JSON 数组 → 执行后解析长度为 2
    @Test
    void advanceRun_scriptMergesExistingToolCalls() throws Exception {
        Run run = runningRun();
        AgentStep step = pendingStep(113L, 1, AgentType.SCRIPT);
        step.setToolCallsJson("[{\"tool\":\"old\"}]");
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        when(scriptService.generate(EPISODE_ID, "ai"))
                .thenReturn(new Records.GenerateScriptResponse(EPISODE_ID, 3, "剧本正文", "ai",
                        "Deepseek-v4-flash", 100L, 1000L, 2000L, null));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        var node = objectMapper.readTree(saved.getToolCallsJson());
        assertEquals(2, node.size());
    }

    // N11. recordToolCall：SCRIPT 预置损坏 JSON → 执行后解析长度为 1
    @Test
    void advanceRun_scriptCorruptToolCallsRebuilt() throws Exception {
        Run run = runningRun();
        AgentStep step = pendingStep(114L, 1, AgentType.SCRIPT);
        step.setToolCallsJson("corrupt{{{");
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(step));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        when(scriptService.generate(EPISODE_ID, "ai"))
                .thenReturn(new Records.GenerateScriptResponse(EPISODE_ID, 3, "剧本正文", "ai",
                        "Deepseek-v4-flash", 100L, 1000L, 2000L, null));

        executor.advanceRun(run);

        AgentStep saved = captureLastSavedStep();
        assertEquals(AgentStepStatus.SUCCEEDED, saved.getStatus());
        var node = objectMapper.readTree(saved.getToolCallsJson());
        assertEquals(1, node.size());
    }

    // N12. finalizeRun：VIDEO 成本未知但 costEstimated=false → totalCostCents=0（不是 null），totalTokens=100
    @Test
    void advanceRun_finalizeVideoUnknownCostButNotEstimated_zeroTotalCost() {
        Run run = runningRun();

        AgentStep s1 = new AgentStep();
        s1.setId(115L);
        s1.setSeqNo(1);
        s1.setAgentType(AgentType.SCRIPT);
        s1.setStatus(AgentStepStatus.SUCCEEDED);
        s1.setEpisodeId(EPISODE_ID);
        s1.setTokensUsed(100L);
        s1.setCostCents(50L);

        AgentStep s2 = new AgentStep();
        s2.setId(116L);
        s2.setSeqNo(2);
        s2.setAgentType(AgentType.VIDEO);
        s2.setStatus(AgentStepStatus.SUCCEEDED);
        s2.setEpisodeId(EPISODE_ID);
        s2.setTokensUsed(null);
        s2.setCostCents(null);
        s2.setCostEstimated(false);

        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(RUN_ID)).thenReturn(List.of(s1, s2));

        executor.advanceRun(run);

        Run savedRun = captureLastSavedRun();
        assertEquals(RunStatus.SUCCEEDED, savedRun.getStatus());
        assertEquals(100L, savedRun.getTotalTokens());
        // SCRIPT 的 50 分计入，VIDEO 未估算不置 null（区别于 F1 的未知成本置 null）
        assertNotNull(savedRun.getTotalCostCents());
        assertEquals(50L, savedRun.getTotalCostCents());
    }

}
