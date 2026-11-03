package com.dramafactory.service;

/*
 * 诚实跳过清单（经分析确认不可达，不硬编测试）：
 *
 * - RunExecutor.java:592 的 `runId == null` 臂：findPreviousStepOfType 的唯一调用者传入的
 *   runId 来自 runRepository.findById 命中的 Run 实体（advanceRun 第 125 行已判 null 返回），
 *   恒非 null。防御性不可达。
 * - RunExecutor.java:592 的 `type == null` 臂：两个调用点分别硬编码 AgentType.SCRIPT /
 *   AgentType.EDIT 编译期常量，恒非 null。防御性不可达。
 * - RunExecutor.java:651 truncate 的 `s == null` 臂：两处调用方分别是 193 行 safeMessage(ex)
 *   （永不为 null，见下条）与 381 行 `f.getErrorMessage() == null ? "video task failed" : ...`
 *   （保证非空）。防御性不可达。
 * - RunExecutor.java:662 safeMessage 的 `t == null` 臂：唯一调用方传入 catch 到的异常实例，
 *   永不为 null。防御性不可达。
 */

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

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class RunExecutorBranch3Test {

    private RunRepository runRepository;
    private AgentStepRepository agentStepRepository;
    private VideoTaskRepository videoTaskRepository;
    private ScriptService scriptService;
    private ScriptSplitterService scriptSplitterService;
    private VideoTaskService videoTaskService;
    private FinalCutService finalCutService;
    private RunLogService runLogService;
    private Environment environment;
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
                new ObjectMapper(),
                skillService, mock(ReviewService.class));
    }

    private Run runningRun(Long id) {
        Run run = new Run();
        run.setId(id);
        run.setStatus(RunStatus.RUNNING);
        return run;
    }

    private AgentStep step(Long id, Integer seqNo, AgentType type, AgentStepStatus status, Long episodeId) {
        AgentStep s = new AgentStep();
        s.setId(id);
        s.setSeqNo(seqNo);
        s.setAgentType(type);
        s.setStatus(status);
        s.setEpisodeId(episodeId);
        return s;
    }

    // ---- 149 SKIPPED 臂：steps 全终态（SUCCEEDED + SKIPPED）触发 finalizeRun ----
    @Test
    void noPendingStep_allTerminalWithSkipped_expectsRunSucceeded() {
        Run run = runningRun(1L);
        when(runRepository.findById(1L)).thenReturn(Optional.of(run));

        List<AgentStep> steps = new ArrayList<>();
        AgentStep script = step(10L, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 5L);
        script.setTokensUsed(7L);
        script.setCostCents(3L);
        AgentStep board = step(11L, 2, AgentType.BOARD, AgentStepStatus.SKIPPED, 5L);
        steps.add(script);
        steps.add(board);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(steps);

        executor.advanceRun(run);

        // 覆盖第 149 行 `|| s.getStatus() == SKIPPED` 的 SKIPPED 臂，并进入 finalizeRun
        assertThat(run.getStatus()).isEqualTo(RunStatus.SUCCEEDED);
        assertThat(run.getTotalTokens()).isEqualTo(7L);
        assertThat(run.getTotalCostCents()).isEqualTo(3L);
        Mockito.verify(runRepository).save(run);
    }

    // ---- 260 + 267：SCRIPT 且 usedSkill != null ----
    @Test
    void scriptStep_withSkillAndUsedSkill_expectsSucceededAndToolCallsContainSkill() {
        Run run = runningRun(2L);
        when(runRepository.findById(2L)).thenReturn(Optional.of(run));

        AgentStep script = step(20L, 1, AgentType.SCRIPT, AgentStepStatus.PENDING, 5L);
        script.setSkillId(99L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(2L)).thenReturn(List.of(script));

        Records.GenerateScriptResponse resp = mock(Records.GenerateScriptResponse.class);
        when(resp.scriptText()).thenReturn("剧本内容");
        when(resp.sceneCount()).thenReturn(4);
        when(resp.source()).thenReturn("ai");
        when(resp.model()).thenReturn("m1");
        when(resp.promptTokens()).thenReturn(10L);
        when(resp.completionTokens()).thenReturn(20L);
        when(resp.usedSkill()).thenReturn("my-skill v2");
        when(scriptService.generate(eq(5L), eq("ai"), eq(99L))).thenReturn(resp);

        executor.advanceRun(run);

        // 覆盖第 260 行（output.usedSkill 写入）与第 267 行（日志 usedSkill）的 true 臂
        assertThat(script.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(script.getToolCallsJson()).contains("my-skill");
    }

    // ---- 282 null 臂：前置 SCRIPT outputSummary == null ----
    @Test
    void boardStep_previousScriptOutputNull_expectsFailed() {
        Run run = runningRun(3L);
        when(runRepository.findById(3L)).thenReturn(Optional.of(run));

        AgentStep script = step(30L, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 5L);
        script.setOutputSummary(null);
        AgentStep board = step(31L, 2, AgentType.BOARD, AgentStepStatus.PENDING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(3L)).thenReturn(List.of(script, board));

        executor.advanceRun(run);

        // 覆盖第 282 行 `scriptText == null` 臂
        assertThat(board.getStatus()).isEqualTo(AgentStepStatus.FAILED);
    }

    // ---- 282 blank 臂：前置 SCRIPT outputSummary == "" ----
    @Test
    void boardStep_previousScriptOutputBlank_expectsFailed() {
        Run run = runningRun(4L);
        when(runRepository.findById(4L)).thenReturn(Optional.of(run));

        AgentStep script = step(40L, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 5L);
        script.setOutputSummary("");
        AgentStep board = step(41L, 2, AgentType.BOARD, AgentStepStatus.PENDING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(4L)).thenReturn(List.of(script, board));

        executor.advanceRun(run);

        // 覆盖第 282 行 `scriptText.isBlank()` 臂
        assertThat(board.getStatus()).isEqualTo(AgentStepStatus.FAILED);
    }

    // ---- 290 + 324 + 329 + 336：BOARD 且 boardSkillId != null ----
    @Test
    void boardStep_withSkillId_expectsSucceededAndToolCallsContainSkillId() {
        Run run = runningRun(5L);
        when(runRepository.findById(5L)).thenReturn(Optional.of(run));

        AgentStep script = step(50L, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 5L);
        script.setOutputSummary("剧本正文…");
        AgentStep board = step(51L, 2, AgentType.BOARD, AgentStepStatus.PENDING, 5L);
        board.setSkillId(99L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(5L)).thenReturn(List.of(script, board));

        SkillService.ResolvedSkill resolved = mock(SkillService.ResolvedSkill.class);
        when(resolved.renderedPrompt()).thenReturn("skill-prompt");
        when(resolved.name()).thenReturn("s");
        when(resolved.version()).thenReturn("1");
        when(skillService.resolveForUse(eq(99L), any())).thenReturn(resolved);
        when(scriptSplitterService.splitFromScript(eq(5L), eq("剧本正文…"), eq("skill-prompt")))
                .thenReturn(List.of());

        executor.advanceRun(run);

        // 覆盖 290（boardSkillId != null 分支）、324（input.skillId）、329（output.usedSkill）、336（日志）
        assertThat(board.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(board.getToolCallsJson()).contains("skillId");
    }

    // ---- 394 false 臂 + 395 true 臂：VIDEO 未全部 DONE ----
    @Test
    void videoStepRunning_partialDone_expectsStepStaysRunning() {
        Run run = runningRun(6L);
        when(runRepository.findById(6L)).thenReturn(Optional.of(run));

        AgentStep video = step(60L, 1, AgentType.VIDEO, AgentStepStatus.RUNNING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(6L)).thenReturn(List.of(video));

        VideoTask done = new VideoTask();
        done.setId(1L);
        done.setStatus(VideoTaskStatus.DONE);
        VideoTask processing = new VideoTask();
        processing.setId(2L);
        processing.setStatus(VideoTaskStatus.PROCESSING);
        when(videoTaskRepository.findByEpisodeId(5L)).thenReturn(List.of(done, processing));

        executor.advanceRun(run);

        // 覆盖第 394 行 allMatch 的 false 臂与第 395 行 `if (!allDone)` 的 true 臂
        assertThat(video.getStatus()).isEqualTo(AgentStepStatus.RUNNING);
        assertThat(run.getStatus()).isEqualTo(RunStatus.RUNNING);
    }

    // ---- 408：updatedAt == null 臂 ----
    @Test
    void videoStepDone_updatedAtNull_expectsSucceeded() {
        Run run = runningRun(7L);
        when(runRepository.findById(7L)).thenReturn(Optional.of(run));

        AgentStep video = step(70L, 1, AgentType.VIDEO, AgentStepStatus.RUNNING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(7L)).thenReturn(List.of(video));

        VideoTask done = new VideoTask();
        done.setId(1L);
        done.setStatus(VideoTaskStatus.DONE);
        done.setProvider("mock");
        done.setCreatedAt(LocalDateTime.now());
        done.setUpdatedAt(null);
        when(videoTaskRepository.findByEpisodeId(5L)).thenReturn(List.of(done));

        executor.advanceRun(run);

        // 覆盖第 408 行 `t.getUpdatedAt() != null` 的 false 臂（taskMs 按 0 汇总）
        assertThat(video.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(video.getLatencyMs()).isEqualTo(0L);
    }

    // ---- 484：FinalCutResponse.status() == null 臂 ----
    @Test
    void editStep_finalCutStatusNull_expectsSucceeded() {
        Run run = runningRun(8L);
        when(runRepository.findById(8L)).thenReturn(Optional.of(run));

        AgentStep edit = step(80L, 1, AgentType.EDIT, AgentStepStatus.PENDING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(8L)).thenReturn(List.of(edit));

        Records.FinalCutResponse resp = mock(Records.FinalCutResponse.class);
        when(resp.id()).thenReturn(7L);
        when(resp.status()).thenReturn(null);
        when(resp.filePath()).thenReturn(null);
        when(finalCutService.buildFinalCut(5L)).thenReturn(resp);

        executor.advanceRun(run);

        // 覆盖第 484 行 `resp.status() == null ? null : ...` 的 null 臂
        assertThat(edit.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
    }

    // ---- 504：QC 自动检查，editOutput == null 臂 ----
    @Test
    void qcStep_editOutputNull_expectsFailed() {
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        Run run = runningRun(9L);
        when(runRepository.findById(9L)).thenReturn(Optional.of(run));

        AgentStep edit = step(90L, 1, AgentType.EDIT, AgentStepStatus.SUCCEEDED, 5L);
        edit.setOutputSummary(null);
        AgentStep qc = step(91L, 2, AgentType.QC, AgentStepStatus.PENDING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(9L)).thenReturn(List.of(edit, qc));

        executor.advanceRun(run);

        // 覆盖第 504 行 `editOutput == null` 臂
        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
    }

    // ---- 509：QC 自动检查，filePath == null 臂 ----
    @Test
    void qcStep_noFilePathMarker_expectsFailedWithMissingPath() {
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        Run run = runningRun(10L);
        when(runRepository.findById(10L)).thenReturn(Optional.of(run));

        AgentStep edit = step(100L, 1, AgentType.EDIT, AgentStepStatus.SUCCEEDED, 5L);
        edit.setOutputSummary("一段不含标记的纯文本");
        AgentStep qc = step(101L, 2, AgentType.QC, AgentStepStatus.PENDING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(10L)).thenReturn(List.of(edit, qc));

        executor.advanceRun(run);

        // 覆盖第 509 行 `filePath == null` 臂
        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(qc.getErrorMessage()).contains("未找到成片文件路径");
    }

    // ---- 523：QC 自动检查，length == 0 臂 ----
    @Test
    void qcStep_emptyFile_expectsFailed(@TempDir Path dir) throws Exception {
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        Run run = runningRun(11L);
        when(runRepository.findById(11L)).thenReturn(Optional.of(run));

        Path empty = dir.resolve("empty.mp4");
        Files.createFile(empty);

        AgentStep edit = step(110L, 1, AgentType.EDIT, AgentStepStatus.SUCCEEDED, 5L);
        edit.setOutputSummary("qc=EDIT, filePath=" + empty.toAbsolutePath() + ", size=0");
        AgentStep qc = step(111L, 2, AgentType.QC, AgentStepStatus.PENDING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(11L)).thenReturn(List.of(edit, qc));

        executor.advanceRun(run);

        // 覆盖第 523 行 `f.length() > 0` 的 false 臂（文件存在但为空）
        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
    }

    // ---- 592：seqNo == null 臂 ----
    @Test
    void boardStep_seqNoNull_expectsFailedMissingScript() {
        Run run = runningRun(12L);
        when(runRepository.findById(12L)).thenReturn(Optional.of(run));

        AgentStep board = step(120L, null, AgentType.BOARD, AgentStepStatus.PENDING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(12L)).thenReturn(List.of(board));

        executor.advanceRun(run);

        // 覆盖第 592 行 `seqNo == null` 臂（findPreviousStepOfType 返回 null）
        assertThat(board.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(board.getErrorMessage()).contains("BOARD 找不到前置 SCRIPT step");
    }

    // ---- 598：s.getSeqNo() == null 臂（跳过 null seqNo，选中较小 seqNo） ----
    @Test
    void boardStep_previousScriptSeqNoNull_expectsPicksSeqNo3AndSucceeds() {
        Run run = runningRun(13L);
        when(runRepository.findById(13L)).thenReturn(Optional.of(run));

        AgentStep scriptNullSeq = step(130L, null, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 5L);
        scriptNullSeq.setOutputSummary("x");
        AgentStep scriptSeq3 = step(131L, 3, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 5L);
        scriptSeq3.setOutputSummary("剧本正文…");
        AgentStep board = step(132L, 5, AgentType.BOARD, AgentStepStatus.PENDING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(13L))
                .thenReturn(List.of(scriptNullSeq, scriptSeq3, board));

        when(scriptSplitterService.splitFromScript(eq(5L), eq("剧本正文…"))).thenReturn(List.of());

        executor.advanceRun(run);

        // 覆盖第 598 行 `s.getSeqNo() != null` 的 false 臂：跳过 null seqNo 的 SCRIPT
        assertThat(board.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
    }

    // ---- 614：filePath 后无逗号的臂 ----
    @Test
    void qcStep_filePathNoComma_expectsApproved(@TempDir Path dir) throws Exception {
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
        Run run = runningRun(14L);
        when(runRepository.findById(14L)).thenReturn(Optional.of(run));

        Path file = dir.resolve("movie.mp4");
        Files.write(file, new byte[]{1, 2, 3});

        AgentStep edit = step(140L, 1, AgentType.EDIT, AgentStepStatus.SUCCEEDED, 5L);
        edit.setOutputSummary("qc=EDIT, filePath=" + file.toAbsolutePath());
        AgentStep qc = step(141L, 2, AgentType.QC, AgentStepStatus.PENDING, 5L);
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(14L)).thenReturn(List.of(edit, qc));

        executor.advanceRun(run);

        // 覆盖第 614 行 `if (end < 0)` 的 true 臂（无逗号 → 取到串尾）
        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(qc.getOutputSummary()).contains("qc=APPROVED");
    }

    // ---- 626：existing.isBlank() 为 true 臂 ----
    @Test
    void scriptStep_existingToolCallsBlank_expectsRebuildArray() {
        Run run = runningRun(15L);
        when(runRepository.findById(15L)).thenReturn(Optional.of(run));

        AgentStep script = step(150L, 1, AgentType.SCRIPT, AgentStepStatus.PENDING, 5L);
        script.setToolCallsJson("");
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(15L)).thenReturn(List.of(script));

        Records.GenerateScriptResponse resp = mock(Records.GenerateScriptResponse.class);
        when(resp.scriptText()).thenReturn("t");
        when(resp.sceneCount()).thenReturn(1);
        when(resp.source()).thenReturn("ai");
        when(resp.model()).thenReturn("m");
        when(resp.promptTokens()).thenReturn(1L);
        when(resp.completionTokens()).thenReturn(1L);
        when(resp.usedSkill()).thenReturn(null);
        when(scriptService.generate(anyLong(), eq("ai"))).thenReturn(resp);

        executor.advanceRun(run);

        // 覆盖第 626 行 `!existing.isBlank()` 的 false 臂（旧空串被丢弃重建）
        assertThat(script.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(script.getToolCallsJson()).startsWith("[");
    }

    // ---- 629：node.isArray() 为 false 臂 ----
    @Test
    void scriptStep_existingToolCallsNonArrayJson_expectsRebuildArray() {
        Run run = runningRun(16L);
        when(runRepository.findById(16L)).thenReturn(Optional.of(run));

        AgentStep script = step(160L, 1, AgentType.SCRIPT, AgentStepStatus.PENDING, 5L);
        script.setToolCallsJson("{\"x\":1}");
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(16L)).thenReturn(List.of(script));

        Records.GenerateScriptResponse resp = mock(Records.GenerateScriptResponse.class);
        when(resp.scriptText()).thenReturn("t");
        when(resp.sceneCount()).thenReturn(1);
        when(resp.source()).thenReturn("ai");
        when(resp.model()).thenReturn("m");
        when(resp.promptTokens()).thenReturn(1L);
        when(resp.completionTokens()).thenReturn(1L);
        when(resp.usedSkill()).thenReturn(null);
        when(scriptService.generate(anyLong(), eq("ai"))).thenReturn(resp);

        executor.advanceRun(run);

        // 覆盖第 629 行 `if (node.isArray())` 的 false 臂（合法 JSON 但非数组，重建）
        assertThat(script.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(script.getToolCallsJson()).startsWith("[");
    }
}
