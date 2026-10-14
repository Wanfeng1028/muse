
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
import org.mockito.ArgumentCaptor;
import org.springframework.core.env.Environment;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
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
        executor = new RunExecutor(runRepository, agentStepRepository, videoTaskRepository,
                scriptService, scriptSplitterService, videoTaskService, finalCutService,
                runLogService, environment, objectMapper);
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
                        "Deepseek-v4-flash", 100L));

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
}

