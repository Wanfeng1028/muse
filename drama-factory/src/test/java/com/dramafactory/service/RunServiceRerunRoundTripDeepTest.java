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

class RunServiceRerunRoundTripDeepTest {
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

    private void stubRerun() {
        Run old = new Run();
        old.setId(1L);
        old.setStatus(RunStatus.SUCCEEDED);
        old.setGoal("做短剧");
        old.setPlanJson("{\"goal\":\"做短剧\",\"fallback\":false,\"episodes\":[{\"episodeNo\":1,\"title\":\"重逢\",\"outline\":\"o1\"},{\"episodeNo\":2,\"title\":\"告白\",\"outline\":\"o2\"}]}");
        when(runRepository.findById(1L)).thenReturn(Optional.of(old));
        when(runRepository.save(any())).thenAnswer(inv -> {
            Run r = inv.getArgument(0);
            if (r.getId() == null) {
                r.setId(100L);
            }
            return r;
        });
        when(projectService.create(any())).thenReturn(new Records.ProjectResponse(7L, "做短剧", null, null, null, null, 0L, 0L, null, null, null));
        AtomicLong epId = new AtomicLong(50);
        when(episodeService.create(anyLong(), any())).thenAnswer(inv -> {
            Records.EpisodeRequest req = inv.getArgument(1);
            long id = epId.incrementAndGet();
            return new Records.EpisodeResponse(id, 7L, req.episodeNo(), req.title(), req.outline(), null, null, 0L, null, null);
        });
    }

    @Test
    void rerunPreservesEpisodeCountFromPlanJson() {
        stubRerun();

        Long newId = runService.rerun(1L, null);
        assertThat(newId).isEqualTo(100L);

        ArgumentCaptor<AgentStep> sc = ArgumentCaptor.forClass(AgentStep.class);
        verify(agentStepRepository, times(10)).save(sc.capture());
        List<AgentStep> steps = sc.getAllValues();
        assertThat(steps).hasSize(10);
        for (int i = 0; i < 10; i++) {
            assertThat(steps.get(i).getSeqNo()).isEqualTo(i + 1);
        }
        assertThat(steps.get(0).getName()).isEqualTo("第 1 集 · 编剧");
        assertThat(steps.get(4).getName()).isEqualTo("第 1 集 · 质检");
        assertThat(steps.get(5).getName()).isEqualTo("第 2 集 · 编剧");
        assertThat(steps).allMatch(s -> s.getStatus() == AgentStepStatus.PENDING);

        ArgumentCaptor<Run> rc = ArgumentCaptor.forClass(Run.class);
        verify(runRepository, times(3)).save(rc.capture());
        Run last = rc.getAllValues().get(2);
        assertThat(last.getStatus()).isEqualTo(RunStatus.RUNNING);
        assertThat(last.getGoal()).isEqualTo("做短剧");
    }

    @Test
    void rerunGoalOverrideReplacesGoal() {
        stubRerun();

        runService.rerun(1L, "  新目标  ");
        ArgumentCaptor<Run> first = ArgumentCaptor.forClass(Run.class);
        verify(runRepository, times(3)).save(first.capture());
        assertThat(first.getAllValues().get(2).getGoal()).isEqualTo("新目标");

        runService.rerun(1L, "   ");
        ArgumentCaptor<Run> second = ArgumentCaptor.forClass(Run.class);
        verify(runRepository, times(6)).save(second.capture());
        assertThat(second.getAllValues().get(5).getGoal()).isEqualTo("做短剧");
    }
}
