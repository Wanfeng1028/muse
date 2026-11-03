// 文件：src/test/java/com/dramafactory/service/RunExecutorV229D2Test.java

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
import org.springframework.core.env.Environment;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.nio.file.Path;
import java.util.Arrays;
import java.util.Collections;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RunExecutorV229D2Test {

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
        runExecutor = new RunExecutor(runRepository, agentStepRepository, videoTaskRepository,
                scriptService, scriptSplitterService, videoTaskService, finalCutService,
                runLogService, environment, objectMapper, skillService, mock(ReviewService.class));
        when(environment.getProperty("harness.qc.manual-approval")).thenReturn("false");
    }

    @Test
    @DisplayName("line509: EDIT 输出 filePath 为空字符串时 QC 走未找到成片路径 FAILED 分支")
    void qcStep_blankFilePath_marksFailed() {
        Run run = new Run();
        run.setId(7L);
        run.setStatus(RunStatus.RUNNING);

        AgentStep editStep = mock(AgentStep.class);
        when(editStep.getAgentType()).thenReturn(AgentType.EDIT);
        when(editStep.getSeqNo()).thenReturn(1);
        when(editStep.getId()).thenReturn(101L);
        when(editStep.getOutputSummary()).thenReturn("filePath=, size=0");

        AgentStep qcStep = mock(AgentStep.class);
        when(qcStep.getAgentType()).thenReturn(AgentType.QC);
        when(qcStep.getSeqNo()).thenReturn(2);
        when(qcStep.getStatus()).thenReturn(AgentStepStatus.PENDING);
        when(qcStep.getEpisodeId()).thenReturn(1L);

        when(runRepository.findById(7L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(7L))
                .thenReturn(Arrays.asList(editStep, qcStep));

        runExecutor.advanceRun(run);

        ArgumentCaptor<AgentStepStatus> statusCaptor = ArgumentCaptor.forClass(AgentStepStatus.class);
        verify(qcStep, atLeastOnce()).setStatus(statusCaptor.capture());
        assertTrue(statusCaptor.getAllValues().contains(AgentStepStatus.FAILED));

        ArgumentCaptor<String> msgCaptor = ArgumentCaptor.forClass(String.class);
        verify(qcStep, times(2)).setErrorMessage(msgCaptor.capture());
        assertTrue(msgCaptor.getAllValues().get(1).contains("QC 自动检查失败: 未找到成片文件路径"));

        assertEquals(RunStatus.FAILED, run.getStatus());
        verify(runRepository, atLeastOnce()).save(run);
    }

    @Test
    @DisplayName("line523: filePath 指向目录时 ok 为 false 走文件不存在或为空 FAILED 分支")
    void qcStep_pathIsDirectory_marksFailed(@TempDir Path tempDir) {
        Run run = new Run();
        run.setId(7L);
        run.setStatus(RunStatus.RUNNING);

        String dirPath = tempDir.toString();

        AgentStep editStep = mock(AgentStep.class);
        when(editStep.getAgentType()).thenReturn(AgentType.EDIT);
        when(editStep.getSeqNo()).thenReturn(1);
        when(editStep.getOutputSummary()).thenReturn("filePath=" + dirPath + ", size=0");

        AgentStep qcStep = mock(AgentStep.class);
        when(qcStep.getAgentType()).thenReturn(AgentType.QC);
        when(qcStep.getSeqNo()).thenReturn(2);
        when(qcStep.getStatus()).thenReturn(AgentStepStatus.PENDING);
        when(qcStep.getEpisodeId()).thenReturn(1L);

        when(runRepository.findById(7L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(7L))
                .thenReturn(Arrays.asList(editStep, qcStep));

        runExecutor.advanceRun(run);

        ArgumentCaptor<AgentStepStatus> statusCaptor = ArgumentCaptor.forClass(AgentStepStatus.class);
        verify(qcStep, atLeastOnce()).setStatus(statusCaptor.capture());
        assertTrue(statusCaptor.getAllValues().contains(AgentStepStatus.FAILED));

        ArgumentCaptor<String> msgCaptor = ArgumentCaptor.forClass(String.class);
        verify(qcStep, times(2)).setErrorMessage(msgCaptor.capture());
        assertTrue(msgCaptor.getAllValues().get(1).contains("QC 自动检查失败: 文件不存在或为空"));

        assertEquals(RunStatus.FAILED, run.getStatus());
        verify(runRepository, atLeastOnce()).save(run);
    }

    @Test
    @DisplayName("line598: 前置 EDIT step seqNo 为 null 时被跳过导致 QC 找不到前置 EDIT step")
    void qcStep_previousEditSeqNoNull_throwsQcNoPreviousEdit() {
        Run run = new Run();
        run.setId(7L);
        run.setStatus(RunStatus.RUNNING);

        AgentStep editStep = mock(AgentStep.class);
        when(editStep.getAgentType()).thenReturn(AgentType.EDIT);
        when(editStep.getSeqNo()).thenReturn(null);

        AgentStep qcStep = mock(AgentStep.class);
        when(qcStep.getAgentType()).thenReturn(AgentType.QC);
        when(qcStep.getSeqNo()).thenReturn(2);
        when(qcStep.getStatus()).thenReturn(AgentStepStatus.PENDING);
        when(qcStep.getEpisodeId()).thenReturn(1L);

        when(runRepository.findById(7L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(7L))
                .thenReturn(Arrays.asList(editStep, qcStep));

        runExecutor.advanceRun(run);

        ArgumentCaptor<String> msgCaptor = ArgumentCaptor.forClass(String.class);
        verify(qcStep, times(2)).setErrorMessage(msgCaptor.capture());
        String realMsg = msgCaptor.getAllValues().get(1);
        assertNotNull(realMsg);
        assertTrue(realMsg.contains("QC 找不到前置 EDIT step"));

        ArgumentCaptor<AgentStepStatus> statusCaptor = ArgumentCaptor.forClass(AgentStepStatus.class);
        verify(qcStep, atLeastOnce()).setStatus(statusCaptor.capture());
        assertTrue(statusCaptor.getAllValues().contains(AgentStepStatus.FAILED));

        assertEquals(RunStatus.FAILED, run.getStatus());
        verify(runRepository, atLeastOnce()).save(run);
    }
}