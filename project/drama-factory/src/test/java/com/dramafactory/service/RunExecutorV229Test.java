// 文件：src/test/java/com/dramafactory/service/RunExecutorV229Test.java

package com.dramafactory.service;

import com.dramafactory.service.ReviewService;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.ArgumentCaptor;
import org.springframework.core.env.Environment;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * RunExecutor 分支覆盖补齐测试（C5）。纯 Mockito，无 Spring 上下文。
 *
 * <p>诚实声明：以下 5 个分支是防御性不可达分支，本测试<b>不</b>用反射硬调 private 方法来凑覆盖率：
 * <ul>
 *   <li>findPreviousStepOfType 的 runId == null（1 个）：runQcStep 内部永远传 run.getId()，非 null。</li>
 *   <li>findPreviousStepOfType 的 seqNo == null（1 个）：永远传 step.getSeqNo()，非 null。</li>
 *   <li>findPreviousStepOfType 的 type == null（1 个）：永远传 AgentType.EDIT 常量。</li>
 *   <li>truncate 的 s == null → null（1 个）：safeMessage 永不返回 null。</li>
 *   <li>safeMessage 的 t == null → "unknown error"（1 个）：catch (Exception ex) 的 ex 永不为 null。</li>
 * </ul>
 */
@ExtendWith(MockitoExtension.class)
class RunExecutorV229Test {

    @Mock
    private RunRepository runRepository;

    @Mock
    private AgentStepRepository agentStepRepository;

    @Mock
    private VideoTaskRepository videoTaskRepository;

    @Mock
    private ScriptService scriptService;

    @Mock
    private ScriptSplitterService scriptSplitterService;

    @Mock
    private VideoTaskService videoTaskService;

    @Mock
    private FinalCutService finalCutService;

    @Mock
    private RunLogService runLogService;

    @Mock
    private Environment environment;

    @Mock
    private SkillService skillService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private RunExecutor runExecutor;

    @BeforeEach
    void setUp() {
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
                skillService, mock(ReviewService.class));
        // 关闭 QC 人工审批门，避免被提前拦截
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
    }

    private Run runningRun(Long id) {
        Run run = new Run();
        run.setId(id);
        run.setStatus(RunStatus.RUNNING);
        return run;
    }

    private AgentStep qcStep(Long id, int seqNo) {
        AgentStep step = new AgentStep();
        step.setId(id);
        step.setSeqNo(seqNo);
        step.setAgentType(AgentType.QC);
        step.setStatus(AgentStepStatus.PENDING);
        step.setEpisodeId(1L);
        return step;
    }

    private AgentStep editStep(Long id, int seqNo, String outputSummary) {
        AgentStep step = new AgentStep();
        step.setId(id);
        step.setSeqNo(seqNo);
        step.setAgentType(AgentType.EDIT);
        step.setStatus(AgentStepStatus.SUCCEEDED);
        step.setOutputSummary(outputSummary);
        return step;
    }

    @Test
    @DisplayName("场景A：QC 找不到前置 EDIT step → step FAILED 且消息含「QC 找不到前置 EDIT step」")
    void scenarioANoPreviousEditStep() {
        Run run = runningRun(1L);
        AgentStep qc = qcStep(100L, 2);

        when(runRepository.findById(1L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of(qc));

        runExecutor.advanceRun(run);

        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(qc.getErrorMessage()).contains("QC 找不到前置 EDIT step");
        assertThat(run.getStatus()).isEqualTo(RunStatus.FAILED);
    }

    @Test
    @DisplayName("场景B：EDIT step 输出为空白 → step FAILED 且消息含「输出为空」")
    void scenarioBEditOutputBlank() {
        Run run = runningRun(2L);
        AgentStep edit = editStep(200L, 1, " ");
        AgentStep qc = qcStep(201L, 2);

        when(runRepository.findById(2L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(2L)).thenReturn(List.of(edit, qc));

        runExecutor.advanceRun(run);

        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(qc.getErrorMessage()).contains("输出为空");
        assertThat(run.getStatus()).isEqualTo(RunStatus.FAILED);
    }

    @Test
    @DisplayName("场景C：EDIT 输出无 filePath → step FAILED 且含「未找到成片文件路径」，run FAILED")
    void scenarioCEditOutputWithoutFilePath() {
        Run run = runningRun(3L);
        AgentStep edit = editStep(300L, 1, "render done, size=123");
        AgentStep qc = qcStep(301L, 2);

        when(runRepository.findById(3L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(3L)).thenReturn(List.of(edit, qc));

        runExecutor.advanceRun(run);

        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(qc.getErrorMessage()).contains("未找到成片文件路径");
        assertThat(run.getStatus()).isEqualTo(RunStatus.FAILED);
        assertThat(run.getErrorMessage()).contains("未找到成片文件路径");
    }

    @Test
    @DisplayName("场景D：filePath 指向不存在的文件 → step FAILED 且含「文件不存在或为空」")
    void scenarioDFilePathNotExisting() {
        Run run = runningRun(4L);
        AgentStep edit = editStep(400L, 1, "filePath=/nonexistent/xyz.mp4, size=0");
        AgentStep qc = qcStep(401L, 2);

        when(runRepository.findById(4L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(4L)).thenReturn(List.of(edit, qc));

        runExecutor.advanceRun(run);

        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(qc.getErrorMessage()).contains("文件不存在或为空");
        assertThat(run.getStatus()).isEqualTo(RunStatus.FAILED);
    }

    @Test
    @DisplayName("场景E：filePath 指向存在的空文件 → step FAILED")
    void scenarioEFileExistsButEmpty(@TempDir Path tempDir) throws IOException {
        Path emptyFile = tempDir.resolve("empty.mp4");
        Files.createFile(emptyFile);

        Run run = runningRun(5L);
        AgentStep edit = editStep(500L, 1, "filePath=" + emptyFile.toAbsolutePath() + ", size=0");
        AgentStep qc = qcStep(501L, 2);

        when(runRepository.findById(5L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(5L)).thenReturn(List.of(edit, qc));

        runExecutor.advanceRun(run);

        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(qc.getErrorMessage()).contains("文件不存在或为空");
        assertThat(run.getStatus()).isEqualTo(RunStatus.FAILED);
    }

    @Test
    @DisplayName("场景F：filePath 指向存在的非空文件 → step SUCCEEDED 且 outputSummary 含 qc=APPROVED")
    void scenarioFFileExistsAndNonEmpty(@TempDir Path tempDir) throws IOException {
        Path file = tempDir.resolve("final.mp4");
        Files.write(file, new byte[]{1, 2, 3, 4, 5});

        Run run = runningRun(6L);
        AgentStep edit = editStep(600L, 1, "filePath=" + file.toAbsolutePath() + ", size=5");
        AgentStep qc = qcStep(601L, 2);

        when(runRepository.findById(6L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(6L)).thenReturn(List.of(edit, qc));

        runExecutor.advanceRun(run);

        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.SUCCEEDED);
        assertThat(qc.getOutputSummary()).contains("qc=APPROVED");
        assertThat(qc.getOutputSummary()).contains("filePath=" + file.toAbsolutePath());
        assertThat(run.getStatus()).isNotEqualTo(RunStatus.FAILED);
    }

    @Test
    @DisplayName("场景G：超长异常消息走 truncate substring 分支，errorMessage 长度恰为 500")
    void scenarioGTruncateLongMessageAndSafeMessageSimpleName() {
        Run run = runningRun(7L);
        String longMessage = "x".repeat(600);

        AgentStep edit = mock(AgentStep.class);
        when(edit.getAgentType()).thenReturn(AgentType.EDIT);
        when(edit.getSeqNo()).thenReturn(1);
        when(edit.getOutputSummary()).thenThrow(new RuntimeException(longMessage));

        AgentStep qc = mock(AgentStep.class);
        when(qc.getAgentType()).thenReturn(AgentType.QC);
        when(qc.getSeqNo()).thenReturn(2);
        when(qc.getStatus()).thenReturn(AgentStepStatus.PENDING);
        when(qc.getEpisodeId()).thenReturn(1L);

        when(runRepository.findById(7L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(7L)).thenReturn(List.of(edit, qc));

        runExecutor.advanceRun(run);

        ArgumentCaptor<AgentStepStatus> statusCaptor = ArgumentCaptor.forClass(AgentStepStatus.class);
        verify(qc, atLeastOnce()).setStatus(statusCaptor.capture());
        assertThat(statusCaptor.getValue()).isEqualTo(AgentStepStatus.FAILED);

        ArgumentCaptor<String> msgCaptor = ArgumentCaptor.forClass(String.class);
        verify(qc, times(2)).setErrorMessage(msgCaptor.capture());
        assertThat(msgCaptor.getAllValues().get(1)).hasSize(500);
        assertThat(msgCaptor.getAllValues().get(1)).isEqualTo(longMessage.substring(0, 500));

        assertThat(run.getStatus()).isEqualTo(RunStatus.FAILED);
    }

    @Test
    @DisplayName("场景G2：无消息异常走 safeMessage simpleName 分支，errorMessage 为异常类名")
    void scenarioG2SafeMessageSimpleName() {
        Run run = runningRun(8L);

        AgentStep edit = mock(AgentStep.class);
        when(edit.getAgentType()).thenReturn(AgentType.EDIT);
        when(edit.getSeqNo()).thenReturn(1);
        when(edit.getOutputSummary()).thenThrow(new RuntimeException());

        AgentStep qc = mock(AgentStep.class);
        when(qc.getAgentType()).thenReturn(AgentType.QC);
        when(qc.getSeqNo()).thenReturn(2);
        when(qc.getStatus()).thenReturn(AgentStepStatus.PENDING);
        when(qc.getEpisodeId()).thenReturn(1L);

        when(runRepository.findById(8L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(8L)).thenReturn(List.of(edit, qc));

        runExecutor.advanceRun(run);

        ArgumentCaptor<String> msgCaptor = ArgumentCaptor.forClass(String.class);
        verify(qc, times(2)).setErrorMessage(msgCaptor.capture());
        assertThat(msgCaptor.getAllValues().get(1)).isEqualTo("RuntimeException");
    }

    @Test
    @DisplayName("findPreviousStepOfType 正常分支：存在多个前置同类型 step 时返回 seqNo 最大的那个")
    void findPreviousStepReturnsLatestMatching() {
        Run run = runningRun(9L);
        AgentStep edit1 = editStep(900L, 1, "filePath=/nonexistent/a.mp4, size=0");
        AgentStep edit2 = editStep(901L, 3, "filePath=/nonexistent/b.mp4, size=0");
        AgentStep qc = qcStep(902L, 5);

        when(runRepository.findById(9L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(9L)).thenReturn(List.of(edit1, edit2, qc));

        runExecutor.advanceRun(run);

        // 取到 edit2（seqNo=3 < 5），路径 b.mp4 不存在
        assertThat(qc.getStatus()).isEqualTo(AgentStepStatus.FAILED);
        assertThat(qc.getErrorMessage()).contains("/nonexistent/b.mp4");
    }
}