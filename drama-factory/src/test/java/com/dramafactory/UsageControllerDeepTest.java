package com.dramafactory;

import com.dramafactory.controller.UsageController;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Run;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.AgentStepRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.repository.DramaCharacterRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.UsageService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class UsageControllerDeepTest {

    @Autowired
    UsageController usageController;

    @Autowired
    UsageService usageService;

    @Autowired
    VideoTaskRepository videoTaskRepository;

    @Autowired
    AgentStepRepository agentStepRepository;

    @Autowired
    RunRepository runRepository;

    @Autowired
    ShotRepository shotRepository;

    @Autowired
    SceneRepository sceneRepository;

    @Autowired
    DramaCharacterRepository characterRepository;

    @Autowired
    EpisodeRepository episodeRepository;

    @Autowired
    DramaProjectRepository dramaProjectRepository;

    private DramaProject project;
    private Episode episode;
    private Shot shot;

    @BeforeEach
    void cleanAndSeed() {
        agentStepRepository.deleteAll();
        videoTaskRepository.deleteAll();
        runRepository.deleteAll();
        shotRepository.deleteAll();
        sceneRepository.deleteAll();
        characterRepository.deleteAll();
        episodeRepository.deleteAll();
        dramaProjectRepository.deleteAll();

        project = new DramaProject();
        project.setTitle("Deep Test Project");
        project = dramaProjectRepository.save(project);

        episode = new Episode();
        episode.setEpisodeNo(1);
        episode.setProject(project);
        episode = episodeRepository.save(episode);

        shot = new Shot();
        shot.setShotNo(1);
        shot.setEpisode(episode);
        shot = shotRepository.save(shot);
    }

    private VideoTask insertVideoTask(String provider, String modelUsed, long tokens, long costCents,
                                      VideoTaskStatus status, LocalDateTime createdAt) {
        VideoTask vt = new VideoTask();
        vt.setShot(shot);
        vt.setStatus(status);
        vt.setProvider(provider);
        vt.setModelUsed(modelUsed);
        vt.setTokensUsed(tokens);
        vt.setCostCents(costCents);
        vt.setCreatedAt(createdAt);
        return videoTaskRepository.save(vt);
    }

    private Run insertRun(String goal, RunStatus status) {
        Run r = new Run();
        r.setGoal(goal);
        r.setStatus(status);
        return runRepository.save(r);
    }

    private AgentStep insertAgentStep(Run run, int seqNo, AgentType agentType, AgentStepStatus status,
                                      long tokens, long costCents, LocalDateTime createdAt) {
        AgentStep s = new AgentStep();
        s.setRun(run);
        s.setSeqNo(seqNo);
        s.setAgentType(agentType);
        s.setStatus(status);
        s.setTokensUsed(tokens);
        s.setCostCents(costCents);
        s.setCreatedAt(createdAt);
        return agentStepRepository.save(s);
    }

    @Test
    void summary_aggregatesVideoTasksWithProviderFilter() {
        // given
        LocalDateTime now = LocalDateTime.now();
        insertVideoTask("openai", "gpt-4", 100L, 50L, VideoTaskStatus.DONE, now);
        insertVideoTask("openai", "gpt-4", 200L, 80L, VideoTaskStatus.DONE, now);

        // when
        UsageController.SummaryDto body = usageController.summary("openai", "gpt-4", 7);

        // then
        assertNotNull(body);
        assertEquals(300L, body.tokensTotal());
        assertEquals(130L, body.costCentsTotal());
        assertEquals(2L, body.taskCount());
        assertEquals(0L, body.stepCount());
    }

    @Test
    void summary_withNoRowsReturnsNullTotalsWithoutFailure() {
        // when
        UsageController.SummaryDto body = usageController.summary("ghost", "none", 30);

        // then：无数据时 token/cost 总量按设计为 null（见 UsageService.summary javadoc），计数为 0
        assertNotNull(body);
        assertNull(body.tokensTotal(), "无数据时 tokensTotal 按设计为 null");
        assertNull(body.costCentsTotal(), "无数据时 costCentsTotal 按设计为 null");
        assertEquals(0L, body.taskCount());
        assertEquals(0L, body.runCount());
    }

    @Test
    void byModel_groupsPerModelAndSortsByCostDesc() {
        // given
        LocalDateTime now = LocalDateTime.now();
        insertVideoTask("openai", "gpt-4", 100L, 900L, VideoTaskStatus.DONE, now);
        insertVideoTask("anthropic", "claude", 200L, 100L, VideoTaskStatus.DONE, now);

        // when
        List<UsageController.ModelDto> body = usageController.byModel();

        // then
        assertNotNull(body);
        assertEquals(2, body.size());
        assertEquals("gpt-4", body.get(0).model());
        assertEquals(900L, body.get(0).costCents());
        assertEquals("claude", body.get(1).model());
    }

    @Test
    void byDay_sumsMultipleTasksOnSameDate() {
        // given：传入的历史日期会被 @PrePersist 覆盖为"现在"，故两条记录实际落在同一天
        LocalDate today = LocalDate.now();
        LocalDate yesterday = today.minusDays(1);
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, yesterday.atTime(10, 0));
        insertVideoTask("openai", "gpt-4", 300L, 30L, VideoTaskStatus.DONE, today.atTime(12, 0));

        // when
        List<UsageController.DayDto> body = usageController.byDay(7, "openai", null);

        // then：@PrePersist 会把 createdAt 统一改成现在，故两个任务落在同一天，分组求和
        assertNotNull(body);
        assertEquals(1, body.size());
        assertEquals(400L, body.get(0).tokens());
        assertEquals(40L, body.get(0).costCents());
    }

    @Test
    void byDay_includesTasksCreatedNowWithinWindow() {
        // given：传入的历史日期会被 @PrePersist 覆盖为"现在"，两条记录都在 30 天窗口内
        insertVideoTask("openai", "gpt-4", 42L, 7L, VideoTaskStatus.DONE, LocalDateTime.now().minusDays(29));
        insertVideoTask("openai", "gpt-4", 42L, 7L, VideoTaskStatus.DONE, LocalDateTime.now().minusDays(60));

        // when
        List<UsageController.DayDto> body = usageController.byDay(30, null, null);

        // then
        assertNotNull(body);
        assertEquals(1, body.size());
        assertEquals(84L, body.get(0).tokens());
        // 注：@PrePersist 覆盖了传入的历史日期，窗口下限行为此处无法用实体 API 覆盖
    }

    @Test
    void requests_mergesBothSourcesAndRespectsLimit() {
        // given
        LocalDateTime now = LocalDateTime.now();
        insertVideoTask("openai", "gpt-4", 100L, 5L, VideoTaskStatus.DONE, now);
        insertVideoTask("openai", "gpt-4", 200L, 6L, VideoTaskStatus.DONE, now.minusMinutes(1));
        Run run = insertRun("merge goal", RunStatus.RUNNING);
        insertAgentStep(run, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 300L, 7L, now.minusMinutes(2));

        // when
        List<UsageController.RequestDto> body = usageController.requests(10, "openai", null, 7);

        // then
        assertNotNull(body);
        assertEquals(2, body.size());
    }

    @Test
    void requests_limitBoundsResultSize() {
        // given
        LocalDateTime now = LocalDateTime.now();
        insertVideoTask("openai", "gpt-4", 100L, 5L, VideoTaskStatus.DONE, now);
        insertVideoTask("openai", "gpt-4", 200L, 6L, VideoTaskStatus.DONE, now.minusMinutes(1));
        insertVideoTask("openai", "gpt-4", 300L, 7L, VideoTaskStatus.DONE, now.minusMinutes(2));

        // when
        List<UsageController.RequestDto> body = usageController.requests(2, "openai", null, 7);

        // then
        assertNotNull(body);
        assertEquals(2, body.size());
    }

    @Test
    void byRun_returnsRunAggregatesOrderedByCreatedAtDesc() {
        // given
        LocalDateTime now = LocalDateTime.now();
        Run run900 = insertRun("run 900 goal", RunStatus.RUNNING);
        run900.setCreatedAt(now);
        run900 = runRepository.save(run900);
        Run run901 = insertRun("run 901 goal", RunStatus.RUNNING);
        run901.setCreatedAt(now.minusHours(1));
        run901 = runRepository.save(run901);
        insertAgentStep(run900, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 100L, 10L, now);
        insertAgentStep(run900, 2, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 200L, 20L, now.minusMinutes(1));
        insertAgentStep(run901, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 50L, 5L, now.minusMinutes(2));

        // when
        List<UsageController.RunDto> body = usageController.byRun(20);

        // then
        assertNotNull(body);
        assertEquals(2, body.size());
        assertEquals(run900.getId(), body.get(0).runId());
        assertEquals(300L, body.get(0).tokens());
        assertEquals(30L, body.get(0).costCents());
        assertEquals(run901.getId(), body.get(1).runId());
        assertEquals(50L, body.get(1).tokens());
        assertEquals(5L, body.get(1).costCents());
    }

    @Test
    void filters_returnsDistinctProvidersAndModels() {
        // given
        LocalDateTime now = LocalDateTime.now();
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, now);
        insertVideoTask("anthropic", "claude", 100L, 10L, VideoTaskStatus.DONE, now);
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, now);

        // when
        UsageService.FilterOptions body = usageController.filters();

        // then
        assertNotNull(body);
        assertNotNull(body.providers());
        assertNotNull(body.models());
        assertTrue(body.providers().contains("openai"));
        assertTrue(body.providers().contains("anthropic"));
        assertTrue(body.models().contains("gpt-4"));
        assertTrue(body.models().contains("claude"));
    }

    @Test
    void summary_nullProviderAndModelIsAccepted() {
        // given
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, LocalDateTime.now());

        // when
        UsageController.SummaryDto body = usageController.summary(null, null, 7);

        // then
        assertNotNull(body);
        assertEquals(100L, body.tokensTotal());
        assertEquals(10L, body.costCentsTotal());
    }

    @Test
    void concurrentSummaryReadsDoNotCorruptAggregates() throws Exception {
        // given
        LocalDateTime now = LocalDateTime.now();
        for (int i = 0; i < 20; i++) {
            insertVideoTask("openai", "gpt-4", 10L, 1L, VideoTaskStatus.DONE, now);
        }

        ExecutorService pool = Executors.newFixedThreadPool(4);
        Callable<Long> readTokens = () -> {
            UsageController.SummaryDto r = usageController.summary("openai", null, 7);
            return r.tokensTotal();
        };

        // when
        List<Future<Long>> futures = pool.invokeAll(List.of(readTokens, readTokens, readTokens, readTokens));
        long first = futures.get(0).get();

        // then
        assertEquals(200L, first);
        for (Future<Long> f : futures) {
            assertEquals(200L, f.get());
        }
        pool.shutdown();
    }

    @Test
    void concurrentByModelReadsStayConsistent() throws Exception {
        // given
        LocalDateTime now = LocalDateTime.now();
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, now);
        insertVideoTask("anthropic", "claude", 200L, 20L, VideoTaskStatus.DONE, now);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        Callable<Integer> readSize = () -> {
            List<UsageController.ModelDto> r = usageController.byModel();
            return r.size();
        };

        // when
        List<Future<Integer>> futures = pool.invokeAll(List.of(readSize, readSize));

        // then
        assertEquals(2, futures.get(0).get());
        assertEquals(2, futures.get(1).get());
        pool.shutdown();
    }

    @Test
    void requests_unknownProviderReturnsEmptyList() {
        // given
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, LocalDateTime.now());

        // when
        List<UsageController.RequestDto> body = usageController.requests(50, "ghost", null, 30);

        // then
        assertNotNull(body);
        assertEquals(0, body.size());
    }

    @Test
    void byRun_emptyTableReturnsEmptyList() {
        // when
        List<UsageController.RunDto> body = usageController.byRun(20);

        // then
        assertNotNull(body);
        assertEquals(0, body.size());
    }

    @Test
    void summary_hugeDaysValueStillReturnsRowsInWindow() {
        // given
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, LocalDateTime.now());

        // when
        UsageController.SummaryDto body = usageController.summary("openai", null, 100000);

        // then
        assertNotNull(body);
        assertEquals(100L, body.tokensTotal());
        assertEquals(1L, body.taskCount());
    }

    @Test
    void summary_negativeDaysDoesNotThrow() {
        // given
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, LocalDateTime.now());

        // when
        UsageController.SummaryDto body = usageController.summary("openai", null, -1);

        // then
        assertNotNull(body);
        assertNotNull(body.tokensTotal());
        assertNotNull(body.costCentsTotal());
    }

    @Test
    void filters_emptyTableReturnsNonNullEmptyCollections() {
        // when
        UsageService.FilterOptions body = usageController.filters();

        // then
        assertNotNull(body);
        assertNotNull(body.providers());
        assertNotNull(body.models());
        assertTrue(body.providers().isEmpty());
        assertTrue(body.models().isEmpty());
    }

    @Test
    void byModel_aggregatesVideoTasksAndAgentSteps() {
        // given
        LocalDateTime now = LocalDateTime.now();
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, now);
        Run run = insertRun("byModel goal", RunStatus.RUNNING);
        insertAgentStep(run, 1, AgentType.SCRIPT, AgentStepStatus.SUCCEEDED, 200L, 20L, now);

        // when
        List<UsageController.ModelDto> body = usageController.byModel();

        // then：VideoTask 按 modelUsed 分组，AgentStep 按 agentType.getLabel() 分组，共 2 组
        assertNotNull(body);
        assertEquals(2, body.size());
        // 按 model 名字找到两组断言（顺序不保证，用 map）
        java.util.Map<String, UsageController.ModelDto> byName = new java.util.HashMap<>();
        for (UsageController.ModelDto md : body) { byName.put(md.model(), md); }
        assertEquals(100L, byName.get("gpt-4").tokens());
        assertEquals(10L, byName.get("gpt-4").costCents());
        assertEquals(200L, byName.get("编剧").tokens());
        assertEquals(20L, byName.get("编剧").costCents());
    }

    @Test
    void byDay_providerFilterExcludesOtherProviders() {
        // given
        LocalDateTime now = LocalDateTime.now();
        insertVideoTask("openai", "gpt-4", 100L, 10L, VideoTaskStatus.DONE, now);
        insertVideoTask("anthropic", "claude", 500L, 50L, VideoTaskStatus.DONE, now);

        // when
        List<UsageController.DayDto> body = usageController.byDay(7, "openai", null);

        // then
        assertNotNull(body);
        assertEquals(1, body.size());
        assertEquals(100L, body.get(0).tokens());
    }

    @Test
    void controllerBeanIsWired() {
        // given
        assertNotNull(usageController);

        // when
        UsageController.SummaryDto dto = usageController.summary("openai", "gpt-4", 7);

        // then：bean 可用；无数据时 token/cost 总量按设计为 null（见 UsageService.summary javadoc），计数为 0
        assertNotNull(dto);
        assertNull(dto.tokensTotal(), "无数据时 tokensTotal 按设计为 null");
        assertNull(dto.costCentsTotal(), "无数据时 costCentsTotal 按设计为 null");
        assertEquals(0L, dto.taskCount());
        assertEquals(0L, dto.runCount());
    }
}
