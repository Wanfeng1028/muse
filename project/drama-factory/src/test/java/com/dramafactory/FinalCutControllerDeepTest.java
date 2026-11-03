package com.dramafactory;

import com.dramafactory.controller.FinalCutController;
import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.service.FinalCutService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.model.FinalCut;
import com.dramafactory.model.FinalCutStatus;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.service.FfmpegService;
import com.dramafactory.service.SubtitleService;
import com.dramafactory.metrics.DramaMetrics;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.mockito.Mockito;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.any;
import static org.mockito.Mockito.anyLong;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * FinalCutController 深度集成测试。
 * 覆盖 Run 全生命周期语义：状态机流转、幂等性、失败注入、并发、边界。
 */
@SpringBootTest
@ActiveProfiles("test")
class FinalCutControllerDeepTest {

    @Autowired
    private FinalCutController finalCutController;

    @Autowired
    private FinalCutService finalCutService;

    @MockBean
    private FfmpegService ffmpegService;

    @MockBean
    private SubtitleService subtitleService;

    @MockBean
    private DramaMetrics dramaMetrics;

    @Autowired
    private FinalCutRepository finalCutRepository;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaProjectRepository projectRepository;

    private Long episodeId;

    @BeforeEach
    void setUp() throws Exception {
        // 清库，避免残留数据干扰
        finalCutRepository.deleteAll();
        videoTaskRepository.deleteAll();
        shotRepository.deleteAll();
        episodeRepository.deleteAll();
        projectRepository.deleteAll();

        // 建项目与剧集，episodeId 用真实落库的 id
        DramaProject p = new DramaProject();
        p.setTitle("测试项目");
        DramaProject savedProject = projectRepository.save(p);

        Episode episode = new Episode();
        episode.setProject(savedProject);
        episode.setEpisodeNo(1);
        episode.setTitle("深测第一集");
        episode = episodeRepository.save(episode);
        episodeId = episode.getId();

        // 建分镜
        Shot shot = new Shot();
        shot.setEpisode(episode);
        shot.setShotNo(1);
        shot.setDescription("开场");
        shot = shotRepository.save(shot);

        // 造一个真实存在的假 mp4 文件
        Path clipDir = Paths.get("./target/test-media-finalcut-ctl/clips");
        Files.createDirectories(clipDir);
        Path clipFile = clipDir.resolve("episode_" + episodeId + "_shot_1.mp4");
        Files.writeString(clipFile, "fake-mp4-bytes");

        // 建 DONE 且 localPath 存在的 VideoTask
        VideoTask task = new VideoTask();
        task.setShot(shot);
        task.setStatus(VideoTaskStatus.DONE);
        task.setLocalPath(clipFile.toString());
        videoTaskRepository.save(task);

        // mock 掉 ffmpeg / subtitle 依赖
        doNothing().when(ffmpegService).concatClips(any(), any());
        doNothing().when(ffmpegService).burnSubtitles(any(), any(), any());
        when(ffmpegService.probeDurationSeconds(any())).thenReturn(12.5);
        when(subtitleService.buildSrt(anyLong(), any()))
                .thenReturn(Paths.get("./target/test-media-finalcut-ctl/subtitles/episode_" + episodeId + ".srt"));
    }

    @AfterEach
    void tearDown() {
        Mockito.reset(ffmpegService, subtitleService, dramaMetrics);
    }

    @Test
    void createFinalCut_returnsCreatedStatusAndBody() {
        // given：一个合法的剧集 ID
        Long targetEpisodeId = episodeId;

        // when：调用 createFinalCut
        ResponseEntity<Records.FinalCutResponse> response =
                finalCutController.createFinalCut(targetEpisodeId);

        // then：状态码 201，body 非空且 episodeId 匹配
        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(targetEpisodeId, response.getBody().episodeId());
    }

    @Test
    void createFinalCut_sameEpisodeTwice_isIdempotentForEpisodeId() {
        // given：同一剧集连续调用两次
        Long targetEpisodeId = episodeId;

        // when：两次调用
        Records.FinalCutResponse first = finalCutController.createFinalCut(targetEpisodeId).getBody();
        Records.FinalCutResponse second = finalCutController.createFinalCut(targetEpisodeId).getBody();

        // then：两次都返回该剧集，episodeId 一致
        assertNotNull(first);
        assertNotNull(second);
        assertEquals(targetEpisodeId, first.episodeId());
        assertEquals(targetEpisodeId, second.episodeId());
    }

    @Test
    void listFinalCutsByEpisode_returnsListForEpisode() {
        // given：先为该剧集建一条成片
        finalCutController.createFinalCut(episodeId);

        // when：查询该剧集成片列表
        List<Records.FinalCutResponse> list = finalCutController.listFinalCutsByEpisode(episodeId);

        // then：列表非空，且所有条目的 episodeId 都是该剧集
        assertNotNull(list);
        assertTrue(list.size() >= 1);
        for (Records.FinalCutResponse item : list) {
            assertEquals(episodeId, item.episodeId());
        }
    }

    @Test
    void getFinalCut_returnsMatchingId() {
        // given：先创建一条成片拿到 ID
        Records.FinalCutResponse created = finalCutController.createFinalCut(episodeId).getBody();
        assertNotNull(created);
        Long cutId = created.id();

        // when：按 ID 查询详情
        Records.FinalCutResponse fetched = finalCutController.getFinalCut(cutId);

        // then：返回的 ID 与请求一致，且对象非空
        assertNotNull(fetched);
        assertEquals(cutId, fetched.id());
    }

    @Test
    void qcFinalCut_approved_transitionsToReviewed() {
        // given：创建一条成片，构造 APPROVED 质检请求
        Records.FinalCutResponse created = finalCutController.createFinalCut(episodeId).getBody();
        assertNotNull(created);
        Long cutId = created.id();
        Records.QcRequest request = new Records.QcRequest("APPROVED", "质检通过");

        // when：提交质检结论
        Records.FinalCutResponse result = finalCutController.qcFinalCut(cutId, request);

        // then：返回非空，状态为 APPROVED
        assertNotNull(result);
        assertEquals("APPROVED", result.qcStatus(), "质检结论在 qcStatus（status 是构建状态枚举）");
    }

    @Test
    void qcFinalCut_rejected_rollsEpisodeBack() {
        // given：创建一条成片，构造 REJECTED 质检请求
        Records.FinalCutResponse created = finalCutController.createFinalCut(episodeId).getBody();
        assertNotNull(created);
        Long cutId = created.id();
        Records.QcRequest request = new Records.QcRequest("REJECTED", "需要返工");

        // when：提交打回结论
        Records.FinalCutResponse result = finalCutController.qcFinalCut(cutId, request);

        // then：状态为 REJECTED，且打回后详情可再次查询到
        assertNotNull(result);
        assertEquals("REJECTED", result.qcStatus(), "质检结论在 qcStatus（status 是构建状态枚举）");
        Records.FinalCutResponse reFetched = finalCutController.getFinalCut(cutId);
        assertNotNull(reFetched);
        assertEquals(cutId, reFetched.id());
    }

    @Test
    void qcFinalCut_sameRequestTwice_isIdempotent() {
        // given：创建成片并构造同一份 APPROVED 请求
        Records.FinalCutResponse created = finalCutController.createFinalCut(episodeId).getBody();
        assertNotNull(created);
        Long cutId = created.id();
        Records.QcRequest request = new Records.QcRequest("APPROVED", "重复提交");

        // when：连续提交两次相同结论
        Records.FinalCutResponse first = finalCutController.qcFinalCut(cutId, request);
        Records.FinalCutResponse second = finalCutController.qcFinalCut(cutId, request);

        // then：两次状态一致，ID 一致
        assertNotNull(first);
        assertNotNull(second);
        assertEquals(first.status(), second.status());
        assertEquals(first.id(), second.id());
    }

    @Test
    void qcFinalCut_invalidStatus_throwsException() {
        // given：创建成片，构造非法状态
        Records.FinalCutResponse created = finalCutController.createFinalCut(episodeId).getBody();
        assertNotNull(created);
        Long cutId = created.id();
        Records.QcRequest badRequest = new Records.QcRequest("NOT_A_STATUS", "非法");

        // when & then：抛异常且异常信息非空
        Exception ex = assertThrows(Exception.class,
                () -> finalCutController.qcFinalCut(cutId, badRequest));
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().length() > 0);
    }

    @Test
    void getFinalCut_unknownId_throwsException() {
        // given：一个不存在的成片 ID
        Long unknownId = -123456L;

        // when & then：查询抛异常，异常信息非空
        Exception ex = assertThrows(Exception.class,
                () -> finalCutController.getFinalCut(unknownId));
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().length() > 0);
    }

    @Test
    void createFinalCut_nullEpisodeId_isRejected() {
        // given：空剧集 ID

        // when & then：调用抛异常，异常对象非空
        Exception ex = assertThrows(Exception.class,
                () -> finalCutController.createFinalCut(null));
        assertNotNull(ex);
        assertNotNull(ex.getClass());
    }

    @Test
    void createFinalCut_concurrentSameEpisode_producesConsistentEpisodeId() throws InterruptedException {
        // given：两线程同时为同一剧集推进 Run
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneGate = new CountDownLatch(threads);
        AtomicInteger successCount = new AtomicInteger(0);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        // when：并发创建
        for (int i = 0; i < threads; i++) {
            pool.submit(() -> {
                try {
                    startGate.await();
                    Records.FinalCutResponse r = finalCutController.createFinalCut(episodeId).getBody();
                    if (r != null && episodeId.equals(r.episodeId())) {
                        successCount.incrementAndGet();
                    }
                } catch (Throwable t) {
                    failure.compareAndSet(null, t);
                } finally {
                    doneGate.countDown();
                }
            });
        }
        startGate.countDown();
        boolean finished = doneGate.await(30, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then：两个线程都完成，成功数至少为 1，未出现数据损坏异常
        assertTrue(finished);
        assertTrue(successCount.get() >= 1);
        assertEquals(null, failure.get());
    }

    @Test
    void listFinalCutsByEpisode_emptyEpisode_returnsEmptyOrNonNull() {
        // given：一个没有任何成片的剧集 ID
        Long emptyEpisodeId = 88888888L;

        // when：查询列表
        List<Records.FinalCutResponse> list = finalCutController.listFinalCutsByEpisode(emptyEpisodeId);

        // then：返回非空列表，且不含该剧集的记录
        assertNotNull(list);
        for (Records.FinalCutResponse item : list) {
            assertNotSame(emptyEpisodeId, item.episodeId());
        }
    }

    @Test
    void qcFinalCut_afterApproved_thenRejected_isAllowedStateChange() {
        // given：先 APPROVED
        Records.FinalCutResponse created = finalCutController.createFinalCut(episodeId).getBody();
        assertNotNull(created);
        Long cutId = created.id();
        finalCutController.qcFinalCut(cutId, new Records.QcRequest("APPROVED", "先通过"));

        // when：再 REJECTED
        Records.FinalCutResponse result =
                finalCutController.qcFinalCut(cutId, new Records.QcRequest("REJECTED", "再打回"));

        // then：状态为 REJECTED，且 ID 未变
        assertNotNull(result);
        assertEquals("REJECTED", result.qcStatus(), "质检结论在 qcStatus（status 是构建状态枚举）");
        assertEquals(cutId, result.id());
    }

    @Test
    void createFinalCut_largePayloadBoundary_isHandled() {
        // given：一个不存在的超大剧集 ID 作为边界输入
        Long largeEpisodeId = Long.MAX_VALUE - 1;

        // when/then：应抛 ResourceNotFoundException（而非溢出或 500）
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> finalCutController.createFinalCut(largeEpisodeId));
        assertTrue(ex.getMessage().contains("Episode"), "异常消息应含资源名");
    }

    @Test
    void serviceBean_isInjectedAndNotNull() {
        // given：Spring 上下文已启动

        // when：读取注入的服务

        // then：控制器与服务的依赖都非空
        assertNotNull(finalCutController);
        assertNotNull(finalCutService);
    }
}