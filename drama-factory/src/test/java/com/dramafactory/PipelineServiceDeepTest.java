package com.dramafactory;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.PipelineService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * PipelineService 深度测试：管线编排核心流程、阶段失败处理与状态回写、非法输入拒绝。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:pipelinedeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class PipelineServiceDeepTest {

    @Autowired
    private PipelineService pipelineService;

    @Autowired
    private DramaProjectRepository dramaProjectRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private FinalCutRepository finalCutRepository;

    /** 每个用例前按外键安全顺序清库，避免用例间互相污染。 */
    @BeforeEach
    void cleanDatabase() {
        videoTaskRepository.deleteAll();
        shotRepository.deleteAll();
        finalCutRepository.deleteAll();
        episodeRepository.deleteAll();
        dramaProjectRepository.deleteAll();
    }

    /** 构造一个持久化项目。 */
    private DramaProject persistProject(String title) {
        DramaProject project = new DramaProject();
        project.setTitle(title);
        return dramaProjectRepository.save(project);
    }

    /** 构造一个持久化剧集。 */
    private Episode persistEpisode(Long projectId, int episodeNo, String title) {
        Episode episode = new Episode();
        episode.setProject(dramaProjectRepository.findById(projectId).orElseThrow());
        episode.setEpisodeNo(episodeNo);
        episode.setTitle(title);
        return episodeRepository.save(episode);
    }

    /** 构造一个持久化分镜。 */
    private Shot persistShot(Long episodeId, int shotNo, Integer durationSeconds) {
        Shot shot = new Shot();
        shot.setEpisode(episodeRepository.findById(episodeId).orElseThrow());
        shot.setShotNo(shotNo);
        shot.setDurationSeconds(durationSeconds);
        return shotRepository.save(shot);
    }

    /** 构造一个持久化视频任务。 */
    private VideoTask persistTask(Long episodeId, Long shotId, VideoTaskStatus status) {
        VideoTask task = new VideoTask();
        // VideoTask 只通过 Shot 关联，无 episode 字段。
        if (shotId != null) {
            task.setShot(shotRepository.findById(shotId).orElseThrow());
        }
        task.setStatus(status);
        return videoTaskRepository.save(task);
    }

    /** 构造一个持久化成片。 */
    private FinalCut persistFinalCut(Long episodeId, FinalCutStatus status) {
        FinalCut finalCut = new FinalCut();
        finalCut.setEpisode(episodeRepository.findById(episodeId).orElseThrow());
        finalCut.setStatus(status);
        return finalCutRepository.save(finalCut);
    }

    @Test
    void getProjectPipelineReturnsAggregatedViewForExistingProject() {
        DramaProject project = persistProject("聚合项目");
        Episode episode = persistEpisode(project.getId(), 1, "第一集");
        Shot shot1 = persistShot(episode.getId(), 1, 10);
        Shot shot2 = persistShot(episode.getId(), 2, 20);
        persistTask(episode.getId(), shot1.getId(), VideoTaskStatus.PENDING);
        persistTask(episode.getId(), shot2.getId(), VideoTaskStatus.PROCESSING);
        persistTask(episode.getId(), shot1.getId(), VideoTaskStatus.DONE);
        persistTask(episode.getId(), shot2.getId(), VideoTaskStatus.FAILED);
        persistFinalCut(episode.getId(), FinalCutStatus.READY);

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(project.getId());

        assertNotNull(view, "聚合视图不应为空");
        assertEquals(project.getId(), view.projectId(), "项目 ID 应回写正确");
        assertEquals("聚合项目", view.title(), "项目标题应回写正确");
        assertEquals(1, view.episodes().size(), "剧集数量应为 1");
        Records.PipelineEpisodeView episodeView = view.episodes().get(0);
        assertEquals(2L, episodeView.shotCount(), "分镜数量应为 2");
        assertEquals(1L, episodeView.pendingTasks(), "PENDING 任务数应为 1");
        assertEquals(1L, episodeView.processingTasks(), "PROCESSING 任务数应为 1");
        assertEquals(1L, episodeView.doneTasks(), "DONE 任务数应为 1");
        assertEquals(1L, episodeView.failedTasks(), "FAILED 任务数应为 1");
        assertEquals("READY", episodeView.finalCutStatus(), "成片状态应为 READY");
    }

    @Test
    void getProjectPipelineReturnsEmptyEpisodeListWhenProjectHasNoEpisodes() {
        DramaProject project = persistProject("空项目");

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(project.getId());

        assertNotNull(view, "聚合视图不应为空");
        assertTrue(view.episodes().isEmpty(), "无剧集时列表应为空");
    }

    @Test
    void getProjectPipelineFallsBackToNoneWhenNoFinalCut() {
        DramaProject project = persistProject("无成片项目");
        Episode episode = persistEpisode(project.getId(), 1, "唯一集");

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(project.getId());

        assertEquals("NONE", view.episodes().get(0).finalCutStatus(), "无成片时应回退为 NONE");
    }

    @Test
    void getProjectPipelineUsesLatestFinalCutStatus() {
        DramaProject project = persistProject("多成片项目");
        Episode episode = persistEpisode(project.getId(), 1, "唯一集");
        persistFinalCut(episode.getId(), FinalCutStatus.BUILDING);
        persistFinalCut(episode.getId(), FinalCutStatus.READY);

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(project.getId());

        assertEquals("READY", view.episodes().get(0).finalCutStatus(), "应取最新成片状态");
    }

    @Test
    void getProjectPipelineThrowsWhenProjectMissing() {
        assertThrows(ResourceNotFoundException.class,
                () -> pipelineService.getProjectPipeline(999999L),
                "项目不存在时应抛出 ResourceNotFoundException");
    }

    @Test
    void getProjectPipelineThrowsWhenProjectIdIsNull() {
        assertThrows(Exception.class,
                () -> pipelineService.getProjectPipeline(null),
                "项目 ID 为 null 时应拒绝");
    }

    @Test
    void getProductionStatsComputesRatesAndRenderSeconds() {
        DramaProject project = persistProject("统计项目");
        Episode episode = persistEpisode(project.getId(), 1, "第一集");
        Shot shot1 = persistShot(episode.getId(), 1, 30);
        Shot shot2 = persistShot(episode.getId(), 2, 50);
        persistTask(episode.getId(), shot1.getId(), VideoTaskStatus.DONE);
        persistTask(episode.getId(), shot2.getId(), VideoTaskStatus.FAILED);

        Records.ProductionStatsResponse stats = pipelineService.getProductionStats(project.getId());

        assertEquals(project.getId(), stats.projectId(), "项目 ID 应回写正确");
        assertEquals(2L, stats.shotCount(), "分镜总数应为 2");
        assertEquals(1L, stats.shotsCompleted(), "完成分镜数应为 1");
        assertEquals(0.5, stats.shotCompletionRate(), 1e-9, "分镜完成率应为 0.5");
        assertEquals(1L, stats.tasksDone(), "成功任务数应为 1");
        assertEquals(1L, stats.tasksFailed(), "失败任务数应为 1");
        assertEquals(0.5, stats.taskSuccessRate(), 1e-9, "任务成功率应为 0.5");
        assertEquals(30L, stats.totalRenderSeconds(), "累计渲染时长应为 30");
    }

    @Test
    void getProductionStatsReturnsZeroRatesWhenNoShotsAndNoTasks() {
        DramaProject project = persistProject("空统计项目");
        persistEpisode(project.getId(), 1, "空集");

        Records.ProductionStatsResponse stats = pipelineService.getProductionStats(project.getId());

        assertEquals(0L, stats.shotCount(), "无分镜时总数应为 0");
        assertEquals(0L, stats.shotsCompleted(), "无分镜时完成数应为 0");
        assertEquals(0.0, stats.shotCompletionRate(), 1e-9, "无分镜时完成率应为 0");
        assertEquals(0L, stats.tasksDone(), "无任务时成功数应为 0");
        assertEquals(0L, stats.tasksFailed(), "无任务时失败数应为 0");
        assertEquals(0.0, stats.taskSuccessRate(), 1e-9, "无任务时成功率应为 0");
        assertEquals(0L, stats.totalRenderSeconds(), "无任务时累计渲染时长应为 0");
    }

    @Test
    void getProductionStatsIgnoresUndecidedTasksInSuccessRate() {
        DramaProject project = persistProject("未决任务项目");
        Episode episode = persistEpisode(project.getId(), 1, "第一集");
        Shot shot = persistShot(episode.getId(), 1, 10);
        persistTask(episode.getId(), shot.getId(), VideoTaskStatus.DONE);
        Shot pendingShot2 = persistShot(episode.getId(), 2, 20);
        Shot processingShot2 = persistShot(episode.getId(), 3, 30);
        persistTask(episode.getId(), pendingShot2.getId(), VideoTaskStatus.PENDING);
        persistTask(episode.getId(), processingShot2.getId(), VideoTaskStatus.PROCESSING);

        Records.ProductionStatsResponse stats = pipelineService.getProductionStats(project.getId());

        assertEquals(1L, stats.tasksDone(), "成功任务数应为 1");
        assertEquals(0L, stats.tasksFailed(), "失败任务数应为 0");
        assertEquals(1.0, stats.taskSuccessRate(), 1e-9, "仅有 DONE 时成功率应为 1");
    }

    @Test
    void getProductionStatsThrowsWhenProjectMissing() {
        assertThrows(ResourceNotFoundException.class,
                () -> pipelineService.getProductionStats(888888L),
                "项目不存在时应抛出 ResourceNotFoundException");
    }

    @Test
    void listAllPipelinesReturnsEmptyListWhenNoProjects() {
        List<Records.PipelineProjectView> result = pipelineService.listAllPipelines();

        assertNotNull(result, "结果列表不应为空");
        assertTrue(result.isEmpty(), "无项目时列表应为空");
    }

    @Test
    void listAllPipelinesReturnsOneEntryPerProject() {
        DramaProject projectA = persistProject("项目A");
        DramaProject projectB = persistProject("项目B");
        persistEpisode(projectA.getId(), 1, "A-1");
        persistEpisode(projectB.getId(), 1, "B-1");
        persistEpisode(projectB.getId(), 2, "B-2");

        List<Records.PipelineProjectView> result = pipelineService.listAllPipelines();

        assertEquals(2, result.size(), "项目数应为 2");
        assertTrue(result.stream().anyMatch(v -> v.projectId().equals(projectA.getId())), "应包含项目A");
        assertTrue(result.stream().anyMatch(v -> v.projectId().equals(projectB.getId())), "应包含项目B");
    }

    @Test
    void getProjectPipelineIsIdempotentAcrossRepeatedCalls() {
        DramaProject project = persistProject("幂等项目");
        Episode episode = persistEpisode(project.getId(), 1, "第一集");
        Shot doneShot = persistShot(episode.getId(), 1, 15);
        persistTask(episode.getId(), doneShot.getId(), VideoTaskStatus.DONE);

        Records.PipelineProjectView first = pipelineService.getProjectPipeline(project.getId());
        Records.PipelineProjectView second = pipelineService.getProjectPipeline(project.getId());

        assertEquals(first.projectId(), second.projectId(), "重复调用项目 ID 应一致");
        assertEquals(first.episodes().size(), second.episodes().size(), "重复调用剧集数应一致");
        assertEquals(first.episodes().get(0).shotCount(), second.episodes().get(0).shotCount(),
                "重复调用分镜数应一致");
        assertEquals(first.episodes().get(0).doneTasks(), second.episodes().get(0).doneTasks(),
                "重复调用完成数应一致");
    }

    @Test
    void getProjectPipelineOrdersEpisodesByEpisodeNoAscending() {
        DramaProject project = persistProject("排序项目");
        persistEpisode(project.getId(), 3, "第三集");
        persistEpisode(project.getId(), 1, "第一集");
        persistEpisode(project.getId(), 2, "第二集");

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(project.getId());

        assertEquals(3, view.episodes().size(), "剧集数量应为 3");
        assertEquals(1, view.episodes().get(0).episodeNo(), "第一集编号应为 1");
        assertEquals(2, view.episodes().get(1).episodeNo(), "第二集编号应为 2");
        assertEquals(3, view.episodes().get(2).episodeNo(), "第三集编号应为 3");
    }

    @Test
    void getProductionStatsSkipsNullDurationWhenCountingRenderSeconds() {
        DramaProject project = persistProject("空时长项目");
        Episode episode = persistEpisode(project.getId(), 1, "第一集");
        Shot shot = persistShot(episode.getId(), 1, null);
        persistTask(episode.getId(), shot.getId(), VideoTaskStatus.DONE);

        Records.ProductionStatsResponse stats = pipelineService.getProductionStats(project.getId());

        assertEquals(1L, stats.shotsCompleted(), "完成分镜数应为 1");
        assertEquals(0L, stats.totalRenderSeconds(), "时长为 null 时不应累加");
    }
}
