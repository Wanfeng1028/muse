/*
 * 覆盖说明（JaCoCo 补漏，分支 -> 测试方法）：
 * - RunService.cancel：PAUSED 走正常取消流程的臂 -> cancel_pausedRun_proceeds
 * - RunService.readStepLog：ownerRunId.equals(runId) 为 true 的臂 -> readStepLog_matchingRunId_proceeds
 * - RunService.stats：createdAt 非空但 updatedAt 为空的臂 -> stats_skipsDurationWhenUpdatedAtNull
 * - PromptRecipe.onCreate：usageCount 非空臂 + visibility 非空臂 -> promptRecipe_onCreate_keepsExistingValues
 * - SceneService.delete：existsById 为 true 的臂 -> sceneService_delete_existing_deletes
 * - JwtVerifier 构造器：secret == null 的臂 -> jwtVerifier_nullSecret_disables
 * - CurrentUser.currentUserId：instanceof 为真、request 非空、userId 为 null 的臂 -> currentUser_noUserIdAttribute_returnsLocal
 */
package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.config.JwtVerifier;
import com.dramafactory.dto.Records;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.data.domain.Sort;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class BranchCatchUpTest {

    @Test
    void cancel_pausedRun_proceeds() {
        RunRepository runRepository = mock(RunRepository.class);
        AgentStepRepository agentStepRepository = mock(AgentStepRepository.class);
        EpisodeRepository episodeRepository = mock(EpisodeRepository.class);
        FinalCutRepository finalCutRepository = mock(FinalCutRepository.class);
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        LlmScriptService llmScriptService = mock(LlmScriptService.class);
        ProjectService projectService = mock(ProjectService.class);
        EpisodeService episodeService = mock(EpisodeService.class);
        FinalCutService finalCutService = mock(FinalCutService.class);
        RunLogService runLogService = mock(RunLogService.class);
        ObjectMapper objectMapper = new ObjectMapper();
        CurrentUser currentUser = mock(CurrentUser.class);
        DramaProjectRepository projectRepository = mock(DramaProjectRepository.class);

        RunService service = new RunService(runRepository, agentStepRepository, episodeRepository,
                finalCutRepository, videoTaskRepository, llmScriptService, projectService,
                episodeService, finalCutService, runLogService, objectMapper, "Deepseek-v4-flash",
                currentUser, projectRepository);

        Run run = new Run();
        run.setId(1L);
        run.setStatus(RunStatus.PAUSED);

        when(runRepository.findById(1L)).thenReturn(Optional.of(run));
        when(agentStepRepository.findByRunIdOrderBySeqNoAsc(1L)).thenReturn(List.of());
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> inv.getArgument(0));

        service.cancel(1L);

        assertEquals(RunStatus.CANCELLED, run.getStatus());
    }

    @Test
    void readStepLog_matchingRunId_proceeds() {
        RunRepository runRepository = mock(RunRepository.class);
        AgentStepRepository agentStepRepository = mock(AgentStepRepository.class);
        EpisodeRepository episodeRepository = mock(EpisodeRepository.class);
        FinalCutRepository finalCutRepository = mock(FinalCutRepository.class);
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        LlmScriptService llmScriptService = mock(LlmScriptService.class);
        ProjectService projectService = mock(ProjectService.class);
        EpisodeService episodeService = mock(EpisodeService.class);
        FinalCutService finalCutService = mock(FinalCutService.class);
        RunLogService runLogService = mock(RunLogService.class);
        ObjectMapper objectMapper = new ObjectMapper();
        CurrentUser currentUser = mock(CurrentUser.class);
        DramaProjectRepository projectRepository = mock(DramaProjectRepository.class);

        RunService service = new RunService(runRepository, agentStepRepository, episodeRepository,
                finalCutRepository, videoTaskRepository, llmScriptService, projectService,
                episodeService, finalCutService, runLogService, objectMapper, "Deepseek-v4-flash",
                currentUser, projectRepository);

        Run run = new Run();
        run.setId(1L);
        AgentStep step = new AgentStep();
        step.setId(5L);
        step.setRun(run);
        step.setSeqNo(2);

        when(agentStepRepository.findById(5L)).thenReturn(Optional.of(step));
        RunLogService.LogReadResult res = new RunLogService.LogReadResult("abc", 3L, true);
        when(runLogService.read(eq(1L), eq(2), eq(0L))).thenReturn(res);

        Records.LogReadResponse response = service.readStepLog(1L, 5L, 0L);

        assertEquals("abc", response.content());
        assertEquals(3L, response.nextOffset());
    }

    @Test
    void stats_skipsDurationWhenUpdatedAtNull() {
        RunRepository runRepository = mock(RunRepository.class);
        AgentStepRepository agentStepRepository = mock(AgentStepRepository.class);
        EpisodeRepository episodeRepository = mock(EpisodeRepository.class);
        FinalCutRepository finalCutRepository = mock(FinalCutRepository.class);
        VideoTaskRepository videoTaskRepository = mock(VideoTaskRepository.class);
        LlmScriptService llmScriptService = mock(LlmScriptService.class);
        ProjectService projectService = mock(ProjectService.class);
        EpisodeService episodeService = mock(EpisodeService.class);
        FinalCutService finalCutService = mock(FinalCutService.class);
        RunLogService runLogService = mock(RunLogService.class);
        ObjectMapper objectMapper = new ObjectMapper();
        CurrentUser currentUser = mock(CurrentUser.class);
        DramaProjectRepository projectRepository = mock(DramaProjectRepository.class);

        RunService service = new RunService(runRepository, agentStepRepository, episodeRepository,
                finalCutRepository, videoTaskRepository, llmScriptService, projectService,
                episodeService, finalCutService, runLogService, objectMapper, "Deepseek-v4-flash",
                currentUser, projectRepository);

        when(currentUser.currentUserId()).thenReturn("u1");

        DramaProject owned = new DramaProject();
        owned.setId(5L);
        when(projectRepository.findByOwnerId(eq("u1"), any(Sort.class))).thenReturn(List.of(owned));

        Run run = new Run();
        run.setStatus(RunStatus.SUCCEEDED);
        run.setProjectId(5L);
        run.setCreatedAt(LocalDateTime.of(2026, 1, 1, 0, 0, 0));
        run.setUpdatedAt(null);
        when(runRepository.findAll()).thenReturn(List.of(run));

        Records.RunStatsResponse stats = service.stats();

        assertEquals(1L, stats.totalRuns());
        assertEquals(0L, stats.avgDurationMs());
    }

    @Test
    void promptRecipe_onCreate_keepsExistingValues() {
        PromptRecipe r = new PromptRecipe();
        r.setUsageCount(5L);
        r.setVisibility(RecipeVisibility.PRIVATE);

        r.onCreate();

        assertEquals(5L, r.getUsageCount());
        assertEquals(RecipeVisibility.PRIVATE, r.getVisibility());
    }

    @Test
    void sceneService_delete_existing_deletes() {
        SceneRepository repo = mock(SceneRepository.class);
        EpisodeRepository epRepo = mock(EpisodeRepository.class);
        SceneService service = new SceneService(repo, epRepo);

        when(repo.existsById(1L)).thenReturn(true);

        service.delete(1L);

        verify(repo).deleteById(1L);
    }

    @Test
    void jwtVerifier_nullSecret_disables() {
        JwtVerifier v = new JwtVerifier(null);
        assertFalse(v.isEnabled());
    }

    @Test
    void currentUser_noUserIdAttribute_returnsLocal() {
        HttpServletRequest req = mock(HttpServletRequest.class);
        when(req.getAttribute("auth.userId")).thenReturn(null);
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(req));
        try {
            assertEquals("local", new CurrentUser().currentUserId());
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
    }
}
