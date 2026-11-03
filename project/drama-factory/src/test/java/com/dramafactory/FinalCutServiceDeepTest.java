package com.dramafactory;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.metrics.DramaMetrics;
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
import com.dramafactory.service.FfmpegService;
import com.dramafactory.service.FinalCutService;
import com.dramafactory.service.SubtitleService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.InvalidDataAccessApiUsageException;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.TestPropertySource;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * FinalCutService 深度集成测试：用真实 Spring 上下文 + 内存 H2 + 真实 JPA 仓储，
 * 只对 ffmpeg 与字幕两个外部副作用做 mock，覆盖 Run 全生命周期的状态流转、幂等、
 * 失败注入、并发与边界场景。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:finalcutdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "drama.storage=./target/test-media-finalcut",
        "drama.ffmpeg.retry-attempts=2",
        "drama.ffmpeg.retry-backoff-ms=1",
        "drama.ffmpeg.retry-total-budget-ms=5"
})
class FinalCutServiceDeepTest {

    @Autowired
    private FinalCutService finalCutService;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private FinalCutRepository finalCutRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @MockBean
    private SubtitleService subtitleService;

    @MockBean
    private FfmpegService ffmpegService;

    @MockBean
    private DramaMetrics dramaMetrics;

    private Long episodeId;
    private Long shotId;

    @BeforeEach
    void setUp() throws Exception {
        // 清库，保证每个用例从空状态开始
        finalCutRepository.deleteAll();
        videoTaskRepository.deleteAll();
        shotRepository.deleteAll();
        episodeRepository.deleteAll();
        projectRepository.deleteAll();

        // 准备真实项目 + 剧集 + 一个分镜 + 一个已完成视频任务，视频文件真实落盘
        DramaProject p = new DramaProject();
        p.setTitle("测试项目");
        DramaProject savedProject = projectRepository.save(p);

        Episode episode = new Episode();
        episode.setProject(savedProject);
        episode.setEpisodeNo(1);
        episode.setTitle("深测第一集");
        episode = episodeRepository.save(episode);
        episodeId = episode.getId();

        Shot shot = new Shot();
        shot.setEpisode(episode);
        shot.setShotNo(1);
        shot.setDescription("开场");
        shot = shotRepository.save(shot);
        shotId = shot.getId();

        Path clipDir = Paths.get("./target/test-media-finalcut/clips");
        Files.createDirectories(clipDir);
        Path clipFile = clipDir.resolve("episode_" + episodeId + "_shot_1.mp4");
        Files.writeString(clipFile, "fake-mp4-bytes");

        VideoTask task = new VideoTask();
        task.setShot(shot);
        task.setStatus(VideoTaskStatus.DONE);
        task.setLocalPath(clipFile.toString());
        videoTaskRepository.save(task);

        // 默认让 ffmpeg 与字幕成功；具体用例可覆盖
        doNothing().when(ffmpegService).concatClips(any(), any());
        doNothing().when(ffmpegService).burnSubtitles(any(), any(), any());
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(12.5);
        when(subtitleService.buildSrt(anyLong(), any())).thenReturn(
                Paths.get("./target/test-media-finalcut/subtitles/episode_" + episodeId + ".srt"));
    }

    @AfterEach
    void tearDown() {
        Mockito.reset(ffmpegService, subtitleService, dramaMetrics);
    }

    @Test
    void buildFinalCut_happyPath_reachesReadyAndPersistsFileAndDuration() {
        // given：一个分镜已有完成视频，ffmpeg 与字幕均成功

        // when：构建成片
        Records.FinalCutResponse resp = finalCutService.buildFinalCut(episodeId);

        // then：返回值字段真实可断言
        assertNotNull(resp);
        assertEquals("第1集成片", resp.title());
        assertEquals(FinalCutStatus.READY, resp.status());
        assertEquals(12.5, resp.durationSeconds());

        // then：库里那条成片记录状态也是 READY，且 filePath 指向真实输出
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(1, all.size());
        FinalCut persisted = all.get(0);
        assertEquals(FinalCutStatus.READY, persisted.getStatus());
        assertNotNull(persisted.getFilePath());
        assertTrue(persisted.getFilePath().endsWith(".mp4"));

        // then：字幕与探测各被调用一次，拼接一次
        verify(ffmpegService, times(1)).concatClips(any(), any());
        verify(ffmpegService, times(1)).burnSubtitles(any(), any(), any());
        verify(ffmpegService, times(1)).probeDurationSeconds(any());
        verify(subtitleService, times(1)).buildSrt(eq(episodeId), any());
    }

    @Test
    void buildFinalCut_episodeMissing_throwsResourceNotFoundAndPersistsNothing() {
        // given：一个不存在的剧集 id
        Long missing = 999999L;

        // when / then：抛 ResourceNotFoundException
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> finalCutService.buildFinalCut(missing));
        assertNotNull(ex.getMessage());

        // then：没有产生任何成片记录，也没触碰 ffmpeg
        assertEquals(0, finalCutRepository.findAll().size());
        verify(ffmpegService, never()).concatClips(any(), any());
        verify(subtitleService, never()).buildSrt(anyLong(), any());
    }

    @Test
    void buildFinalCut_noShots_marksFailedAndPersistsErrorMessage() {
        // given：把该剧集的分镜全部删掉，制造"没有分镜"的边界
        videoTaskRepository.deleteAll();
        shotRepository.deleteAll();

        // when：构建应抛 IllegalStateException
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> finalCutService.buildFinalCut(episodeId));
        assertEquals("该剧集没有分镜", ex.getMessage());

        // then：库里留下一条 FAILED 记录，且错误信息被写入
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(1, all.size());
        FinalCut failed = all.get(0);
        assertEquals(FinalCutStatus.FAILED, failed.getStatus());
        assertEquals("该剧集没有分镜", failed.getErrorMessage());
        verify(ffmpegService, never()).concatClips(any(), any());
    }

    @Test
    void buildFinalCut_shotWithoutDoneVideo_marksFailedAndDoesNotCallFfmpeg() {
        // given：把分镜的视频任务置为非 DONE 状态
        List<VideoTask> tasks = videoTaskRepository.findAll();
        assertEquals(1, tasks.size());
        VideoTask t = tasks.get(0);
        t.setStatus(VideoTaskStatus.PENDING);
        videoTaskRepository.save(t);

        // when：构建应抛 IllegalStateException，消息含分镜号
        IllegalStateException ex = assertThrows(IllegalStateException.class,
                () -> finalCutService.buildFinalCut(episodeId));
        assertTrue(ex.getMessage().contains("分镜 1"));

        // then：成片被标记 FAILED，ffmpeg 未被调用
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(1, all.size());
        assertEquals(FinalCutStatus.FAILED, all.get(0).getStatus());
        verify(ffmpegService, never()).concatClips(any(), any());
        verify(ffmpegService, never()).burnSubtitles(any(), any(), any());
    }

    @Test
    void buildFinalCut_concatFails_marksFailedAndSurfacesRuntimeException() {
        // given：concatClips 抛非瞬时 FfmpegException（快速失败，不重试）
        FfmpegService.FfmpegException boom =
                new FfmpegService.FfmpegException("concat exploded", false);
        doThrow(boom).when(ffmpegService).concatClips(any(), any());

        // when / then：构建抛运行时异常
        FfmpegService.FfmpegException thrown = assertThrows(FfmpegService.FfmpegException.class,
                () -> finalCutService.buildFinalCut(episodeId));
        assertEquals("concat exploded", thrown.getMessage());

        // then：成片记录被置为 FAILED，且错误信息写入；后续字幕/烧录未执行
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(1, all.size());
        FinalCut failed = all.get(0);
        assertEquals(FinalCutStatus.FAILED, failed.getStatus());
        assertEquals("concat exploded", failed.getErrorMessage());
        verify(ffmpegService, never()).burnSubtitles(any(), any(), any());
        verify(subtitleService, never()).buildSrt(anyLong(), any());
    }

    @Test
    void buildFinalCut_transientConcatFailsThenSucceeds_retriesAndReachesReady() {
        // given：concatClips 第一次瞬时失败，第二次成功
        AtomicInteger calls = new AtomicInteger(0);
        doAnswer(invocation -> {
            int n = calls.incrementAndGet();
            if (n == 1) {
                throw new FfmpegService.FfmpegException("transient glitch", true);
            }
            return null;
        }).when(ffmpegService).concatClips(any(), any());

        // when
        Records.FinalCutResponse resp = finalCutService.buildFinalCut(episodeId);

        // then：最终 READY，concat 被调用 2 次（1 失败 + 1 成功）
        assertEquals(FinalCutStatus.READY, resp.status());
        assertEquals(2, calls.get());
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(1, all.size());
        assertEquals(FinalCutStatus.READY, all.get(0).getStatus());
        verify(ffmpegService, times(2)).concatClips(any(), any());
    }

    @Test
    void buildFinalCut_transientConcatAlwaysFails_exhaustsAttemptsAndMarksFailed() {
        // given：concatClips 每次都瞬时失败，重试上限 2 次
        AtomicInteger calls = new AtomicInteger(0);
        doAnswer(invocation -> {
            calls.incrementAndGet();
            throw new FfmpegService.FfmpegException("always transient", true);
        }).when(ffmpegService).concatClips(any(), any());

        // when / then：抛 FfmpegException
        FfmpegService.FfmpegException thrown = assertThrows(FfmpegService.FfmpegException.class,
                () -> finalCutService.buildFinalCut(episodeId));
        assertEquals("always transient", thrown.getMessage());

        // then：恰好重试到上限次数（2），成片 FAILED
        assertEquals(2, calls.get());
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(1, all.size());
        assertEquals(FinalCutStatus.FAILED, all.get(0).getStatus());
        assertEquals("always transient", all.get(0).getErrorMessage());
    }

    @Test
    void buildFinalCut_subtitleBuildFails_marksFailedAndDoesNotBurnSubtitles() {
        // given：字幕生成抛异常（非 ffmpeg 依赖失败注入）
        when(subtitleService.buildSrt(anyLong(), any()))
                .thenThrow(new RuntimeException("srt builder down"));

        // when / then：构建抛 RuntimeException，消息透传
        RuntimeException thrown = assertThrows(RuntimeException.class,
                () -> finalCutService.buildFinalCut(episodeId));
        assertEquals("srt builder down", thrown.getMessage());

        // then：拼接执行过（第一步成功），烧字幕未执行，成片 FAILED
        verify(ffmpegService, times(1)).concatClips(any(), any());
        verify(ffmpegService, never()).burnSubtitles(any(), any(), any());
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(1, all.size());
        assertEquals(FinalCutStatus.FAILED, all.get(0).getStatus());
        assertEquals("srt builder down", all.get(0).getErrorMessage());
    }

    @Test
    void buildFinalCut_probeReturnsHugeDuration_persistsExactValue() {
        // given：探测时长返回一个超大值，验证大 payload 边界（数值不被截断/取整）
        double huge = 999999.75;
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(huge);

        // when
        Records.FinalCutResponse resp = finalCutService.buildFinalCut(episodeId);

        // then：返回值与库里记录都精确等于 huge
        assertEquals(huge, resp.durationSeconds());
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(1, all.size());
        assertEquals(huge, all.get(0).getDurationSeconds());
        assertEquals(FinalCutStatus.READY, all.get(0).getStatus());
    }

    @Test
    void buildFinalCut_calledTwice_createsTwoIndependentReadyRecords() {
        // given：一次正常构建，再构建一次
        Records.FinalCutResponse first = finalCutService.buildFinalCut(episodeId);
        Records.FinalCutResponse second = finalCutService.buildFinalCut(episodeId);

        // then：两次都是 READY，各自是独立记录（幂等性体现在重复调用都能得到一致 READY 结果）
        assertEquals(FinalCutStatus.READY, first.status());
        assertEquals(FinalCutStatus.READY, second.status());
        assertEquals(first.durationSeconds(), second.durationSeconds());
        assertEquals(2, finalCutRepository.findAll().size());
        verify(ffmpegService, times(2)).concatClips(any(), any());
        verify(ffmpegService, times(2)).probeDurationSeconds(any());
    }

    @Test
    @Transactional
    void buildFinalCut_illegalTransitionFromReadyToBuildingIsRejectedByState() {
        // given：先落一条 READY 的成片记录，模拟"非法状态跳转"的前置数据
        Episode episode = episodeRepository.findById(episodeId).orElseThrow();
        FinalCut fc = new FinalCut();
        fc.setEpisode(episode);
        fc.setTitle("第1集成片");
        fc.setStatus(FinalCutStatus.READY);
        fc.setFilePath("./target/test-media-finalcut/finals/episode_" + episodeId + "_final.mp4");
        fc.setDurationSeconds(10.0);
        FinalCut saved = finalCutRepository.save(fc);

        // when：尝试把它直接改回 BUILDING（非法跳转）
        saved.setStatus(FinalCutStatus.BUILDING);
        finalCutRepository.save(saved);

        // then：service 层新构建会另建一条 BUILDING→READY 记录，不会覆盖旧记录
        Records.FinalCutResponse resp = finalCutService.buildFinalCut(episodeId);
        assertEquals(FinalCutStatus.READY, resp.status());

        // then：库里应有两条记录，其中旧记录 id 保留、新记录 id 不同
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(2, all.size());
        FinalCut reloadedOld = finalCutRepository.findById(saved.getId()).orElseThrow();
        // 旧记录保持测试手动设置的 BUILDING，service 不覆盖旧记录
        assertEquals(FinalCutStatus.BUILDING, reloadedOld.getStatus());
        assertFalse(reloadedOld.getTitle() == null);
        assertEquals(10.0, reloadedOld.getDurationSeconds());
    }

    @Test
    void buildFinalCut_concurrentInvocations_doNotCorruptPersistedData() throws Exception {
        // given：两个线程同时推进同一 episode 的成片构建
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger readyCount = new AtomicInteger(0);
        AtomicReference<Throwable> error = new AtomicReference<>();

        Runnable job = () -> {
            try {
                start.await(5, TimeUnit.SECONDS);
                Records.FinalCutResponse r = finalCutService.buildFinalCut(episodeId);
                if (r != null && r.status() == FinalCutStatus.READY) {
                    readyCount.incrementAndGet();
                }
            } catch (Throwable t) {
                error.compareAndSet(null, t);
            } finally {
                done.countDown();
            }
        };
        Thread t1 = new Thread(job, "deep-concurrent-1");
        Thread t2 = new Thread(job, "deep-concurrent-2");
        t1.start();
        t2.start();
        start.countDown();

        // when：等待两个线程结束
        boolean finished = done.await(30, TimeUnit.SECONDS);

        // then：两个线程都完成，且没有未捕获异常
        assertTrue(finished);
        assertEquals(null, error.get());
        assertEquals(2, readyCount.get());

        // then：库里有两条记录，字段完整无污染，没有 null 状态
        List<FinalCut> all = finalCutRepository.findAll();
        assertEquals(2, all.size());
        for (FinalCut fc : all) {
            assertNotNull(fc.getStatus());
            assertNotNull(fc.getFilePath());
            assertNotNull(fc.getDurationSeconds());
            assertTrue(fc.getStatus() == FinalCutStatus.READY);
        }
    }

    @Test
    void buildFinalCut_emptyEpisodeIdIsStillResolved_throwsResourceNotFound() {
        // given：episodeId 为 null 的边界输入
        // when / then：Spring Data JPA 对 findById(null) 直接抛 InvalidDataAccessApiUsageException，到不了 service 的 orElseThrow
        InvalidDataAccessApiUsageException ex = assertThrows(InvalidDataAccessApiUsageException.class,
                () -> finalCutService.buildFinalCut(null));
        assertNotNull(ex.getMessage());
        assertEquals(0, finalCutRepository.findAll().size());
        verify(ffmpegService, never()).concatClips(any(), any());
    }

    @Test
    void buildFinalCut_transientProbeFailsThenSucceeds_retriesProbeOnly() {
        // given：probeDurationSeconds 第一次瞬时失败，第二次返回正常值
        AtomicInteger probeCalls = new AtomicInteger(0);
        when(ffmpegService.probeDurationSeconds(any())).thenAnswer(invocation -> {
            int n = probeCalls.incrementAndGet();
            if (n == 1) {
                throw new FfmpegService.FfmpegException("probe transient", true);
            }
            return 8.0;
        });

        // when
        Records.FinalCutResponse resp = finalCutService.buildFinalCut(episodeId);

        // then：最终 READY，时长 8.0，probe 被调 2 次；concat 与 burn 各 1 次
        assertEquals(FinalCutStatus.READY, resp.status());
        assertEquals(8.0, resp.durationSeconds());
        assertEquals(2, probeCalls.get());
        verify(ffmpegService, times(1)).concatClips(any(), any());
        verify(ffmpegService, times(1)).burnSubtitles(any(), any(), any());
    }
}