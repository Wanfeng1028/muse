package com.dramafactory;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.ReviewItem;
import com.dramafactory.model.ReviewKind;
import com.dramafactory.model.ReviewStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ReviewItemRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.EpisodeStatusFlowService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class EpisodeStatusFlowServiceDeepTest {

    @Autowired
    private EpisodeStatusFlowService episodeStatusFlowService;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private ReviewItemRepository reviewItemRepository;

    @BeforeEach
    void cleanDatabase() {
        videoTaskRepository.deleteAll();
        shotRepository.deleteAll();
        episodeRepository.deleteAll();
    }

    private Episode createEpisode(EpisodeStatus status) {
        DramaProject p = new DramaProject();
        p.setTitle("测试项目");
        DramaProject savedProject = projectRepository.save(p);

        Episode episode = new Episode();
        episode.setStatus(status);
        episode.setProject(savedProject);
        episode.setEpisodeNo(1);
        return episodeRepository.save(episode);
    }

    /** v3.0 K 章：QC 通过写 REVIEWED 的前提是剧本审核已 APPROVED。 */
    private void approveScript(Episode episode) {
        ReviewItem item = new ReviewItem();
        item.setEpisode(episode);
        item.setKind(ReviewKind.SCRIPT);
        item.setStatus(ReviewStatus.APPROVED);
        reviewItemRepository.save(item);
    }

    private Shot createShot(Long episodeId, int shotNo) {
        Episode episode = episodeRepository.findById(episodeId).orElseThrow();
        Shot shot = new Shot();
        shot.setEpisode(episode);
        shot.setShotNo(shotNo);
        return shotRepository.save(shot);
    }

    private VideoTask createTask(Long shotId, VideoTaskStatus status) {
        Shot shot = shotRepository.findById(shotId).orElseThrow();
        VideoTask task = new VideoTask();
        task.setShot(shot);
        task.setStatus(status);
        return videoTaskRepository.save(task);
    }

    @Test
    void refreshAfterTaskDone_allShotsDone_draftToGenerated() {
        // given: 一个 DRAFT 剧集，两个分镜，各自最新任务都是 DONE
        Episode episode = createEpisode(EpisodeStatus.DRAFT);
        Shot shot1 = createShot(episode.getId(), 1);
        Shot shot2 = createShot(episode.getId(), 2);
        createTask(shot1.getId(), VideoTaskStatus.DONE);
        createTask(shot2.getId(), VideoTaskStatus.DONE);

        // when: 刷新剧集状态
        episodeStatusFlowService.refreshAfterTaskDone(episode.getId());

        // then: 状态推进到 GENERATED
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.GENERATED, reloaded.getStatus());
        assertEquals(2, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size());
    }

    @Test
    void refreshAfterTaskDone_allShotsDone_scriptedToGenerated() {
        // given: 一个 SCRIPTED 剧集，一个分镜，任务 DONE
        Episode episode = createEpisode(EpisodeStatus.SCRIPTED);
        Shot shot = createShot(episode.getId(), 1);
        createTask(shot.getId(), VideoTaskStatus.DONE);

        // when
        episodeStatusFlowService.refreshAfterTaskDone(episode.getId());

        // then
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.GENERATED, reloaded.getStatus());
        assertEquals(VideoTaskStatus.DONE,
                videoTaskRepository.findFirstByShotIdOrderByIdDesc(shot.getId()).orElseThrow().getStatus());
    }

    @Test
    void refreshAfterTaskDone_oneShotNotDone_keepsOriginalStatus() {
        // given: DRAFT 剧集，两个分镜，一个 DONE 一个 RUNNING
        Episode episode = createEpisode(EpisodeStatus.DRAFT);
        Shot shot1 = createShot(episode.getId(), 1);
        Shot shot2 = createShot(episode.getId(), 2);
        createTask(shot1.getId(), VideoTaskStatus.DONE);
        createTask(shot2.getId(), VideoTaskStatus.PROCESSING);

        // when
        episodeStatusFlowService.refreshAfterTaskDone(episode.getId());

        // then: 状态保持 DRAFT
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.DRAFT, reloaded.getStatus());
        assertEquals(2, videoTaskRepository.findAll().size());
    }

    @Test
    void refreshAfterTaskDone_noShots_noChange() {
        // given: DRAFT 剧集，没有分镜
        Episode episode = createEpisode(EpisodeStatus.DRAFT);

        // when
        episodeStatusFlowService.refreshAfterTaskDone(episode.getId());

        // then: 状态不动，也没有分镜
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.DRAFT, reloaded.getStatus());
        assertTrue(shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).isEmpty());
    }

    @Test
    void refreshAfterTaskDone_alreadyReviewed_skipsAdvance() {
        // given: REVIEWED 剧集，分镜任务全部 DONE
        Episode episode = createEpisode(EpisodeStatus.REVIEWED);
        Shot shot = createShot(episode.getId(), 1);
        createTask(shot.getId(), VideoTaskStatus.DONE);

        // when
        episodeStatusFlowService.refreshAfterTaskDone(episode.getId());

        // then: 状态保持 REVIEWED，不被覆盖
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.REVIEWED, reloaded.getStatus());
        assertEquals(1, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size());
    }

    @Test
    void refreshAfterTaskDone_onlyLatestTaskCounts() {
        // given: DRAFT 剧集，分镜有旧 DONE 任务和更新的 RUNNING 任务
        Episode episode = createEpisode(EpisodeStatus.DRAFT);
        Shot shot = createShot(episode.getId(), 1);
        createTask(shot.getId(), VideoTaskStatus.DONE);
        createTask(shot.getId(), VideoTaskStatus.PROCESSING);

        // when
        episodeStatusFlowService.refreshAfterTaskDone(episode.getId());

        // then: 最新任务 PROCESSING，不推进
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.DRAFT, reloaded.getStatus());
        assertEquals(2, videoTaskRepository.findAll().size());
    }

    @Test
    void refreshAfterTaskDone_episodeNotFound_throwsResourceNotFound() {
        // given: 不存在的剧集 ID
        Long missingId = 999999L;

        // when
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeStatusFlowService.refreshAfterTaskDone(missingId));

        // then
        assertNotNull(ex.getMessage());
        assertFalse(ex.getMessage().isEmpty());
    }

    @Test
    void refreshAfterTaskDone_calledTwice_idempotent() {
        // given: SCRIPTED 剧集，任务 DONE
        Episode episode = createEpisode(EpisodeStatus.SCRIPTED);
        Shot shot = createShot(episode.getId(), 1);
        createTask(shot.getId(), VideoTaskStatus.DONE);

        // when: 连续调用两次
        episodeStatusFlowService.refreshAfterTaskDone(episode.getId());
        episodeStatusFlowService.refreshAfterTaskDone(episode.getId());

        // then: 结果一致，仍是 GENERATED，任务数量不变
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.GENERATED, reloaded.getStatus());
        assertEquals(1, videoTaskRepository.findAll().size());
    }

    @Test
    void markQcApproved_draftToReviewed() {
        // given: DRAFT 剧集
        Episode episode = createEpisode(EpisodeStatus.DRAFT);
        approveScript(episode);

        // when
        episodeStatusFlowService.markQcApproved(episode.getId());

        // then
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.REVIEWED, reloaded.getStatus());
        assertEquals(1, episodeRepository.findAll().size());
    }

    @Test
    void markQcApproved_calledTwice_idempotent() {
        // given: SCRIPTED 剧集
        Episode episode = createEpisode(EpisodeStatus.SCRIPTED);
        approveScript(episode);

        // when: 连续两次通过
        episodeStatusFlowService.markQcApproved(episode.getId());
        episodeStatusFlowService.markQcApproved(episode.getId());

        // then
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.REVIEWED, reloaded.getStatus());
        assertEquals(1, episodeRepository.findAll().size());
    }

    @Test
    void markQcApproved_episodeNotFound_throwsResourceNotFound() {
        // given
        Long missingId = 888888L;

        // when
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeStatusFlowService.markQcApproved(missingId));

        // then
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().contains("888888"));
    }

    @Test
    void markQcRejected_generatedBackToScripted() {
        // given: GENERATED 剧集
        Episode episode = createEpisode(EpisodeStatus.GENERATED);

        // when
        episodeStatusFlowService.markQcRejected(episode.getId(), "画面质量不达标");

        // then
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus());
        assertEquals(1, episodeRepository.findAll().size());
    }

    @Test
    void markQcRejected_calledTwice_idempotent() {
        // given: REVIEWED 剧集
        Episode episode = createEpisode(EpisodeStatus.REVIEWED);

        // when: 连续两次打回
        episodeStatusFlowService.markQcRejected(episode.getId(), "第一次打回");
        episodeStatusFlowService.markQcRejected(episode.getId(), "第二次打回");

        // then
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus());
        assertEquals(1, episodeRepository.findAll().size());
    }

    @Test
    void markQcRejected_nullReason_stillTransitions() {
        // given: GENERATED 剧集
        Episode episode = createEpisode(EpisodeStatus.GENERATED);

        // when: 原因为 null
        episodeStatusFlowService.markQcRejected(episode.getId(), null);

        // then: 状态仍打回到 SCRIPTED
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus());
        assertEquals(1, episodeRepository.findAll().size());
    }

    @Test
    void markQcRejected_episodeNotFound_throwsResourceNotFound() {
        // given
        Long missingId = 777777L;

        // when
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeStatusFlowService.markQcRejected(missingId, "找不到"));

        // then
        assertNotNull(ex.getMessage());
        assertTrue(ex.getMessage().contains("777777"));
    }

    @Test
    void concurrent_refreshAfterTaskDone_twoThreadsSameRun_noCorruption() throws InterruptedException {
        // given: SCRIPTED 剧集，一个分镜任务 DONE
        Episode episode = createEpisode(EpisodeStatus.SCRIPTED);
        Shot shot = createShot(episode.getId(), 1);
        createTask(shot.getId(), VideoTaskStatus.DONE);

        int threadCount = 2;
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneGate = new CountDownLatch(threadCount);
        AtomicInteger successCount = new AtomicInteger(0);
        AtomicInteger failureCount = new AtomicInteger(0);

        // when: 两线程同时推进同一剧集
        for (int i = 0; i < threadCount; i++) {
            executor.submit(() -> {
                try {
                    startGate.await();
                    episodeStatusFlowService.refreshAfterTaskDone(episode.getId());
                    successCount.incrementAndGet();
                } catch (Exception e) {
                    failureCount.incrementAndGet();
                } finally {
                    doneGate.countDown();
                }
            });
        }
        startGate.countDown();
        boolean finished = doneGate.await(30, TimeUnit.SECONDS);
        executor.shutdown();

        // then: 两个线程都成功返回，剧集最终状态合法且分镜未被破坏
        assertTrue(finished);
        assertEquals(2, successCount.get());
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.GENERATED, reloaded.getStatus());
        assertEquals(1, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size());
    }

    @Test
    void concurrent_markQcApprovedAndRejected_finalStateIsLegal() throws InterruptedException {
        // given: GENERATED 剧集
        Episode episode = createEpisode(EpisodeStatus.GENERATED);

        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneGate = new CountDownLatch(2);
        AtomicInteger successCount = new AtomicInteger(0);

        // when: 一个线程通过，一个线程打回，同时执行
        executor.submit(() -> {
            try {
                startGate.await();
                episodeStatusFlowService.markQcApproved(episode.getId());
                successCount.incrementAndGet();
            } catch (Exception ignored) {
            } finally {
                doneGate.countDown();
            }
        });
        executor.submit(() -> {
            try {
                startGate.await();
                episodeStatusFlowService.markQcRejected(episode.getId(), "并发打回");
                successCount.incrementAndGet();
            } catch (Exception ignored) {
            } finally {
                doneGate.countDown();
            }
        });
        startGate.countDown();
        boolean finished = doneGate.await(30, TimeUnit.SECONDS);
        executor.shutdown();

        // then: 两个操作都成功，最终状态是 REVIEWED 或 SCRIPTED 之一，不出现非法状态
        assertTrue(finished);
        assertEquals(2, successCount.get());
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertTrue(reloaded.getStatus() == EpisodeStatus.REVIEWED
                || reloaded.getStatus() == EpisodeStatus.SCRIPTED);
    }

    @Test
    void largePayload_manyShotsAllDone_promotesOnce() {
        // given: SCRIPTED 剧集，200 个分镜全部 DONE
        Episode episode = createEpisode(EpisodeStatus.SCRIPTED);
        List<Shot> shots = new ArrayList<>();
        for (int i = 1; i <= 200; i++) {
            Shot shot = createShot(episode.getId(), i);
            shots.add(shot);
            createTask(shot.getId(), VideoTaskStatus.DONE);
        }

        // when
        episodeStatusFlowService.refreshAfterTaskDone(episode.getId());

        // then: 状态推进，分镜数量完整
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.GENERATED, reloaded.getStatus());
        assertEquals(200, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size());
        assertEquals(200, videoTaskRepository.findAll().size());
    }

    @Test
    void illegalTransition_draftDirectlyToReviewed_thenRejectedReturnsScripted() {
        // given: DRAFT 剧集，未经过 GENERATED 直接质检通过
        Episode episode = createEpisode(EpisodeStatus.DRAFT);
        approveScript(episode);

        // when: 先通过，再打回
        episodeStatusFlowService.markQcApproved(episode.getId());
        Episode afterApprove = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.REVIEWED, afterApprove.getStatus());

        episodeStatusFlowService.markQcRejected(episode.getId(), "发现严重问题");

        // then: 最终回到 SCRIPTED，返工流程成立
        Episode finalEpisode = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, finalEpisode.getStatus());
        assertEquals(1, episodeRepository.findAll().size());
    }
}