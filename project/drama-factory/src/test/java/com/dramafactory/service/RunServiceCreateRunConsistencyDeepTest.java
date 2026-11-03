package com.dramafactory.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.assertj.core.api.Assertions.*;
import org.mockito.ArgumentCaptor;
import java.util.List;
import java.util.Optional;
import java.time.LocalDateTime;
import java.util.concurrent.atomic.AtomicLong;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.dramafactory.dto.Records;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.config.CurrentUser;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.service.LlmScriptService;
import com.dramafactory.service.ProjectService;
import com.dramafactory.service.EpisodeService;
import com.dramafactory.service.FinalCutService;
import com.dramafactory.service.RunLogService;

class RunServiceCreateRunConsistencyDeepTest {

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
        runService = new RunService(runRepository, agentStepRepository, episodeRepository,
                finalCutRepository, videoTaskRepository, llmScriptService, projectService,
                episodeService, finalCutService, runLogService, new ObjectMapper(), "Deepseek-v4-flash",
                currentUser, projectRepository);
    }

    private void stubCreateRun() {
        when(runRepository.save(any(Run.class))).thenAnswer(inv -> {
            Run r = inv.getArgument(0);
            if (r.getId() == null) r.setId(100L);
            return r;
        });
        when(projectService.create(any())).thenReturn(
                new Records.ProjectResponse(7L, "t", null, null, null, null, 0L, 0L, null, null, null));
        AtomicLong epId = new AtomicLong(50);
        when(episodeService.create(anyLong(), any())).thenAnswer(inv -> {
            Records.EpisodeRequest req = inv.getArgument(1);
            long id = epId.incrementAndGet();
            return new Records.EpisodeResponse(id, 7L, req.episodeNo(), req.title(), req.outline(),
                    null, null, 0L, null, null);
        });
    }

    @Test
    void createRunFromModelPlanBuildsTenSteps() {
        stubCreateRun();
        Long id = runService.createRun("拍 2 集", new Records.PlanPreview("拍 2 集", List.of(new Records.PlanEpisode(1, "重逢", "o1"), new Records.PlanEpisode(2, "告白", "o2")), false));
        assertThat(id).isEqualTo(100L);
        ArgumentCaptor<AgentStep> sc = ArgumentCaptor.forClass(AgentStep.class);
        verify(agentStepRepository, times(10)).save(sc.capture());
        List<AgentStep> steps = sc.getAllValues();
        assertThat(steps).hasSize(10);
        assertThat(steps.get(0).getAgentType()).isEqualTo(AgentType.SCRIPT);
        assertThat(steps.get(4).getAgentType()).isEqualTo(AgentType.QC);
        ArgumentCaptor<Records.EpisodeRequest> ec = ArgumentCaptor.forClass(Records.EpisodeRequest.class);
        verify(episodeService, times(2)).create(eq(7L), ec.capture());
        assertThat(ec.getAllValues().get(0).episodeNo()).isEqualTo(1);
        assertThat(ec.getAllValues().get(1).title()).isEqualTo("告白");
    }

    @Test
    void createRunTrimsGoal() {
        stubCreateRun();
        runService.createRun("  拍短剧  ", new Records.PlanPreview("拍短剧", List.of(new Records.PlanEpisode(1, "第 1 集", "o")), false));
        ArgumentCaptor<Run> rc = ArgumentCaptor.forClass(Run.class);
        verify(runRepository, atLeastOnce()).save(rc.capture());
        assertThat(rc.getAllValues().get(0).getGoal()).isEqualTo("拍短剧");
    }

    @Test
    void rerunRejectsPausedAndWaitingApproval() {
        Run a = new Run();
        a.setId(1L);
        a.setStatus(RunStatus.PAUSED);
        Run b = new Run();
        b.setId(2L);
        b.setStatus(RunStatus.WAITING_APPROVAL);
        when(runRepository.findById(1L)).thenReturn(Optional.of(a));
        when(runRepository.findById(2L)).thenReturn(Optional.of(b));
        assertThatThrownBy(() -> runService.rerun(1L, null)).isInstanceOf(IllegalStateException.class).hasMessageStartingWith("仅终态运行可重跑");
        assertThatThrownBy(() -> runService.rerun(2L, null)).isInstanceOf(IllegalStateException.class).hasMessageStartingWith("仅终态运行可重跑");
    }
}
