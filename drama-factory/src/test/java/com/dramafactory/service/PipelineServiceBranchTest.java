package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
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
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PipelineServiceBranchTest {

    @Mock
    private DramaProjectRepository dramaProjectRepository;
    @Mock
    private EpisodeRepository episodeRepository;
    @Mock
    private ShotRepository shotRepository;
    @Mock
    private VideoTaskRepository videoTaskRepository;
    @Mock
    private FinalCutRepository finalCutRepository;

    private PipelineService pipelineService;

    @BeforeEach
    void setUp() {
        pipelineService = new PipelineService(
                dramaProjectRepository,
                episodeRepository,
                shotRepository,
                videoTaskRepository,
                finalCutRepository);
    }

    private DramaProject project(long id, String title) {
        DramaProject p = new DramaProject();
        p.setId(id);
        p.setTitle(title);
        return p;
    }

    private Episode episode(long id, int no, String title, EpisodeStatus status) {
        Episode e = new Episode();
        e.setId(id);
        e.setEpisodeNo(no);
        e.setTitle(title);
        e.setStatus(status);
        return e;
    }

    private Shot shot(long id, Integer durationSeconds) {
        Shot s = new Shot();
        s.setId(id);
        s.setDurationSeconds(durationSeconds);
        return s;
    }

    private VideoTask task(long id, VideoTaskStatus status, Shot shot) {
        VideoTask t = new VideoTask();
        t.setId(id);
        t.setStatus(status);
        t.setShot(shot);
        return t;
    }

    // 覆盖 L77-L78：findById 返回 empty → orElseThrow 分支抛 ResourceNotFoundException
    @Test
    void branch_getProductionStats_projectNotFound_throws() {
        when(dramaProjectRepository.findById(9L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class,
                () -> pipelineService.getProductionStats(9L));
    }

    // 覆盖 L113 shotCount==0 三元 true 分支、L115 decided==0 三元 true 分支
    // episodes 空列表 → 循环体 L88-L111 不进入，shotCount 保持 0
    @Test
    void branch_getProductionStats_emptyEpisodes_zeroRates() {
        when(dramaProjectRepository.findById(1L)).thenReturn(Optional.of(project(1L, "测试项目")));
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(List.of());

        Records.ProductionStatsResponse resp = pipelineService.getProductionStats(1L);

        assertEquals(1L, resp.projectId());
        assertEquals(0L, resp.shotCount());
        assertEquals(0L, resp.shotsCompleted());
        assertEquals(0.0, resp.shotCompletionRate());
        assertEquals(0L, resp.tasksDone());
        assertEquals(0L, resp.tasksFailed());
        assertEquals(0.0, resp.taskSuccessRate());
        assertEquals(0L, resp.totalRenderSeconds());
    }

    // 覆盖 L94-L102：shot 维度 DONE 判定 + durationSeconds 非空累加
    //   shotA DONE 且 duration=30 → done 分支真 + duration 非空分支真
    //   shotB DONE 且 duration=null → done 分支真 + duration 非空分支假
    //   shotC findFirst empty → orElse(false) 分支
    //   shotD 任务 PROCESSING → map 内 t.getStatus()==DONE 为 false
    // 覆盖 L113 shotCount!=0 三元 false 分支 → 2/4 = 0.5
    // 覆盖 L104-L110：任务状态 DONE/FAILED/其他 三分支
    // 覆盖 L115 decided!=0 三元 false 分支 → 1/2 = 0.5
    @Test
    void branch_getProductionStats_shotAndTaskAggregation() {
        Episode e = episode(10L, 1, "第一集", EpisodeStatus.SCRIPTED);
        when(dramaProjectRepository.findById(1L)).thenReturn(Optional.of(project(1L, "测试项目")));
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(List.of(e));

        Shot shotA = shot(100L, 30);
        Shot shotB = shot(101L, null);
        Shot shotC = shot(102L, 20);
        Shot shotD = shot(103L, 40);
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L))
                .thenReturn(List.of(shotA, shotB, shotC, shotD));

        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(100L))
                .thenReturn(Optional.of(task(1000L, VideoTaskStatus.DONE, shotA)));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(101L))
                .thenReturn(Optional.of(task(1001L, VideoTaskStatus.DONE, shotB)));
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(102L))
                .thenReturn(Optional.empty());
        when(videoTaskRepository.findFirstByShotIdOrderByIdDesc(103L))
                .thenReturn(Optional.of(task(1003L, VideoTaskStatus.PROCESSING, shotD)));

        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(List.of(
                task(1000L, VideoTaskStatus.DONE, shotA),
                task(1001L, VideoTaskStatus.FAILED, shotB),
                task(1002L, VideoTaskStatus.PENDING, shotC)));

        Records.ProductionStatsResponse resp = pipelineService.getProductionStats(1L);

        assertEquals(4L, resp.shotCount());
        assertEquals(2L, resp.shotsCompleted());
        assertEquals(0.5, resp.shotCompletionRate());
        assertEquals(1L, resp.tasksDone());
        assertEquals(1L, resp.tasksFailed());
        assertEquals(0.5, resp.taskSuccessRate());
        assertEquals(30L, resp.totalRenderSeconds());
    }

    // 覆盖 L129-L134：listAllPipelines findAll 返回空 → 循环不进入，返回空列表
    @Test
    void branch_listAllPipelines_emptyProjects_returnsEmpty() {
        when(dramaProjectRepository.findAll()).thenReturn(List.of());

        List<Records.PipelineProjectView> result = pipelineService.listAllPipelines();

        assertTrue(result.isEmpty());
    }

    // 覆盖 L130-L133：findAll 返回 2 个项目 → 循环迭代 2 次，各调用 getProjectPipeline
    // getProjectPipeline 内部 L53-L54 findById 命中 Optional.of 分支、L57-L65 组装
    @Test
    void branch_listAllPipelines_twoProjects_returnsTwoViews() {
        DramaProject p1 = project(1L, "项目一");
        DramaProject p2 = project(2L, "项目二");
        when(dramaProjectRepository.findAll()).thenReturn(List.of(p1, p2));

        when(dramaProjectRepository.findById(1L)).thenReturn(Optional.of(p1));
        when(dramaProjectRepository.findById(2L)).thenReturn(Optional.of(p2));
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(List.of());
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(2L)).thenReturn(List.of());

        List<Records.PipelineProjectView> result = pipelineService.listAllPipelines();

        assertEquals(2, result.size());
        assertEquals(1L, result.get(0).projectId());
        assertEquals("项目一", result.get(0).title());
        assertTrue(result.get(0).episodes().isEmpty());
        assertEquals(2L, result.get(1).projectId());
        assertEquals("项目二", result.get(1).title());
        assertTrue(result.get(1).episodes().isEmpty());
    }

    // 覆盖 L156 task.getStatus()==null → continue 分支
    // 覆盖 L160 PENDING 计数分支
    // 覆盖 L171-L173 finalCut empty → orElse("NONE")
    // 覆盖 L179 episode.getStatus()==null 三元 true 分支 → status 为 null
    @Test
    void branch_buildEpisodeView_nullTaskStatusSkipped_andNullEpisodeStatus() {
        Episode e = episode(10L, 1, "第一集", null);
        when(dramaProjectRepository.findById(1L)).thenReturn(Optional.of(project(1L, "测试项目")));
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(List.of(e));

        when(shotRepository.countByEpisodeId(10L)).thenReturn(0L);
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(List.of(
                task(1000L, null, null),
                task(1001L, VideoTaskStatus.PENDING, null)));
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(10L)).thenReturn(Optional.empty());

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(1L);

        assertEquals(1, view.episodes().size());
        Records.PipelineEpisodeView ev = view.episodes().get(0);
        assertEquals(10L, ev.episodeId());
        assertEquals(1, ev.episodeNo());
        assertEquals("第一集", ev.title());
        assertNull(ev.status());
        assertEquals(0L, ev.shotCount());
        assertEquals(1L, ev.pendingTasks());
        assertEquals(0L, ev.processingTasks());
        assertEquals(0L, ev.doneTasks());
        assertEquals(0L, ev.failedTasks());
        assertEquals("NONE", ev.finalCutStatus());
    }

    // 覆盖 L179 episode.getStatus()==null 三元 false 分支 → SCRIPTED.name()
    @Test
    void branch_buildEpisodeView_nonNullEpisodeStatus_usesName() {
        Episode e = episode(10L, 1, "第一集", EpisodeStatus.SCRIPTED);
        when(dramaProjectRepository.findById(1L)).thenReturn(Optional.of(project(1L, "测试项目")));
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(List.of(e));

        when(shotRepository.countByEpisodeId(10L)).thenReturn(0L);
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(List.of());
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(10L)).thenReturn(Optional.empty());

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(1L);

        assertEquals("SCRIPTED", view.episodes().get(0).status());
    }

    // 覆盖 L160-L163：PENDING/PROCESSING/DONE/FAILED 四个 case 各自计数分支
    // 覆盖 L171-L172 finalCut 命中 Optional.map → READY.name()
    @Test
    void branch_buildEpisodeView_allTaskStatuses_andReadyFinalCut() {
        Episode e = episode(10L, 2, "第二集", EpisodeStatus.SCRIPTED);
        when(dramaProjectRepository.findById(1L)).thenReturn(Optional.of(project(1L, "测试项目")));
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(List.of(e));

        when(shotRepository.countByEpisodeId(10L)).thenReturn(7L);
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(List.of(
                task(1000L, VideoTaskStatus.PENDING, null),
                task(1001L, VideoTaskStatus.PENDING, null),
                task(1002L, VideoTaskStatus.PROCESSING, null),
                task(1003L, VideoTaskStatus.DONE, null),
                task(1004L, VideoTaskStatus.FAILED, null)));

        FinalCut fc = new FinalCut();
        fc.setId(2000L);
        fc.setStatus(FinalCutStatus.READY);
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(10L)).thenReturn(Optional.of(fc));

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(1L);

        Records.PipelineEpisodeView ev = view.episodes().get(0);
        assertEquals(7L, ev.shotCount());
        assertEquals(2L, ev.pendingTasks());
        assertEquals(1L, ev.processingTasks());
        assertEquals(1L, ev.doneTasks());
        assertEquals(1L, ev.failedTasks());
        assertEquals("READY", ev.finalCutStatus());
    }

    // 覆盖 L171-L173 finalCut empty → orElse("NONE") 分支（独立再确认）
    @Test
    void branch_buildEpisodeView_emptyFinalCut_returnsNone() {
        Episode e = episode(10L, 1, "第一集", EpisodeStatus.SCRIPTED);
        when(dramaProjectRepository.findById(1L)).thenReturn(Optional.of(project(1L, "测试项目")));
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(List.of(e));

        when(shotRepository.countByEpisodeId(10L)).thenReturn(3L);
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(List.of());
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(10L)).thenReturn(Optional.empty());

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(1L);

        Records.PipelineEpisodeView ev = view.episodes().get(0);
        assertEquals(3L, ev.shotCount());
        assertEquals(0L, ev.pendingTasks());
        assertEquals(0L, ev.processingTasks());
        assertEquals(0L, ev.doneTasks());
        assertEquals(0L, ev.failedTasks());
        assertEquals("NONE", ev.finalCutStatus());
    }

    // 覆盖 L57-L63：episodes 多元素 → for 循环迭代 2 次，buildEpisodeView 被调用两次
    @Test
    void branch_getProjectPipeline_multipleEpisodes_iteratesAll() {
        DramaProject p = project(1L, "测试项目");
        when(dramaProjectRepository.findById(1L)).thenReturn(Optional.of(p));

        Episode e1 = episode(10L, 1, "第一集", EpisodeStatus.SCRIPTED);
        Episode e2 = episode(11L, 2, "第二集", EpisodeStatus.SCRIPTED);
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(List.of(e1, e2));

        when(shotRepository.countByEpisodeId(10L)).thenReturn(1L);
        when(shotRepository.countByEpisodeId(11L)).thenReturn(2L);
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(List.of());
        when(videoTaskRepository.findByEpisodeId(11L)).thenReturn(List.of());
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(10L)).thenReturn(Optional.empty());
        when(finalCutRepository.findFirstByEpisodeIdOrderByIdDesc(11L)).thenReturn(Optional.empty());

        Records.PipelineProjectView view = pipelineService.getProjectPipeline(1L);

        assertEquals(1L, view.projectId());
        assertEquals("测试项目", view.title());
        assertEquals(2, view.episodes().size());
        assertEquals(10L, view.episodes().get(0).episodeId());
        assertEquals(1L, view.episodes().get(0).shotCount());
        assertEquals(11L, view.episodes().get(1).episodeId());
        assertEquals(2L, view.episodes().get(1).shotCount());
    }

    // 覆盖 L53-L54：getProjectPipeline 项目不存在 → orElseThrow 抛 ResourceNotFoundException
    @Test
    void branch_getProjectPipeline_projectNotFound_throws() {
        when(dramaProjectRepository.findById(99L)).thenReturn(Optional.empty());

        assertThrows(ResourceNotFoundException.class,
                () -> pipelineService.getProjectPipeline(99L));
    }

    // L159 switch default 分支：VideoTaskStatus 枚举仅 PENDING/PROCESSING/DONE/FAILED，
    // 编译器穷尽所有常量，default 不可达，无法构造测试数据触发，跳过。

    // 覆盖 L113 shotCount==0 三元 true 分支在 getProductionStats 中的独立确认：
    // episode 存在但该 episode 下无 shot → shotCount 累加为 0
    @Test
    void branch_getProductionStats_episodeWithNoShots_zeroShotRate() {
        Episode e = episode(10L, 1, "第一集", EpisodeStatus.SCRIPTED);
        when(dramaProjectRepository.findById(1L)).thenReturn(Optional.of(project(1L, "测试项目")));
        when(episodeRepository.findByProjectIdOrderByEpisodeNoAsc(1L)).thenReturn(List.of(e));

        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(10L)).thenReturn(List.of());
        when(videoTaskRepository.findByEpisodeId(10L)).thenReturn(List.of(
                task(1000L, VideoTaskStatus.PENDING, null)));

        Records.ProductionStatsResponse resp = pipelineService.getProductionStats(1L);

        assertEquals(0L, resp.shotCount());
        assertEquals(0L, resp.shotsCompleted());
        assertEquals(0.0, resp.shotCompletionRate());
        assertEquals(0L, resp.tasksDone());
        assertEquals(0L, resp.tasksFailed());
        assertEquals(0.0, resp.taskSuccessRate());
        assertEquals(0L, resp.totalRenderSeconds());
    }
}
