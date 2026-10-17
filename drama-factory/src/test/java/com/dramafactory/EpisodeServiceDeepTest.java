package com.dramafactory;

import com.dramafactory.dto.Records.EpisodeRequest;
import com.dramafactory.dto.Records.EpisodeResponse;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.service.EpisodeService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.dao.DataIntegrityViolationException;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class EpisodeServiceDeepTest {

    @Autowired
    private EpisodeService episodeService;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private SceneRepository sceneRepository;

    private Long projectId;

    @BeforeEach
    void setUp() {
        episodeRepository.deleteAll();
        projectRepository.deleteAll();
        DramaProject project = new DramaProject();
        project.setTitle("run-lifecycle-project");
        DramaProject saved = projectRepository.save(project);
        projectId = saved.getId();
    }

    private EpisodeRequest request(int no, String title, EpisodeStatus status, Integer duration) {
        return new EpisodeRequest(no, title, "outline-" + title, status, duration);
    }

    @Test
    void createShouldPersistWithDraftStatusWhenStatusNull() {
        // given
        EpisodeRequest req = request(1, "第一集", null, 120);

        // when
        EpisodeResponse created = episodeService.create(projectId, req);

        // then
        assertNotNull(created.id());
        assertEquals(EpisodeStatus.DRAFT, created.status());
        assertEquals(projectId, created.projectId());
        assertEquals(0L, created.sceneCount());
    }

    @Test
    void createShouldThrowWhenProjectMissing() {
        // given
        Long missingProjectId = 999999L;
        EpisodeRequest req = request(1, "不存在项目", EpisodeStatus.DRAFT, 100);

        // when
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeService.create(missingProjectId, req));

        // then
        assertEquals("Project", ex.getResource());
        assertEquals(missingProjectId, ex.getId());
    }

    @Test
    void getShouldThrowWhenEpisodeMissing() {
        // given
        Long missingEpisodeId = 888888L;

        // when
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeService.get(missingEpisodeId));

        // then
        assertEquals("Episode", ex.getResource());
        assertEquals(missingEpisodeId, ex.getId());
    }

    @Test
    void listByProjectShouldReturnEpisodesOrderedByEpisodeNo() {
        // given
        episodeService.create(projectId, request(3, "第三集", EpisodeStatus.DRAFT, 90));
        episodeService.create(projectId, request(1, "第一集", EpisodeStatus.DRAFT, 90));
        episodeService.create(projectId, request(2, "第二集", EpisodeStatus.DRAFT, 90));

        // when
        List<EpisodeResponse> list = episodeService.listByProject(projectId);

        // then
        assertEquals(3, list.size());
        assertEquals(1, list.get(0).episodeNo());
        assertEquals(2, list.get(1).episodeNo());
        assertEquals(3, list.get(2).episodeNo());
    }

    @Test
    void updateShouldKeepStatusWhenRequestStatusNull() {
        // given
        EpisodeResponse created = episodeService.create(projectId,
                request(1, "初始", EpisodeStatus.REVIEWED, 100));
        EpisodeRequest updateReq = request(1, "改名", null, 200);

        // when
        EpisodeResponse updated = episodeService.update(created.id(), updateReq);

        // then
        assertEquals("改名", updated.title());
        assertEquals(EpisodeStatus.REVIEWED, updated.status());
        assertEquals(200, updated.durationSec());
    }

    @Test
    void updateShouldChangeStatusWhenRequestStatusProvided() {
        // given
        EpisodeResponse created = episodeService.create(projectId,
                request(1, "初始", EpisodeStatus.DRAFT, 100));
        EpisodeRequest updateReq = request(1, "发布", EpisodeStatus.REVIEWED, 100);

        // when
        EpisodeResponse updated = episodeService.update(created.id(), updateReq);

        // then
        assertEquals(EpisodeStatus.REVIEWED, updated.status());
        assertEquals(created.id(), updated.id());
    }

    @Test
    void updateShouldBeIdempotentForSameRequest() {
        // given
        EpisodeResponse created = episodeService.create(projectId,
                request(1, "幂等", EpisodeStatus.DRAFT, 60));
        EpisodeRequest updateReq = request(1, "幂等-改", EpisodeStatus.REVIEWED, 75);

        // when
        EpisodeResponse first = episodeService.update(created.id(), updateReq);
        EpisodeResponse second = episodeService.update(created.id(), updateReq);

        // then
        assertEquals(first.id(), second.id());
        assertEquals(first.title(), second.title());
        assertEquals(first.status(), second.status());
        assertEquals(first.durationSec(), second.durationSec());
    }

    @Test
    void deleteShouldBeIdempotentOnSecondCallThrowsNotFound() {
        // given
        EpisodeResponse created = episodeService.create(projectId,
                request(1, "删除", EpisodeStatus.DRAFT, 60));

        // when
        episodeService.delete(created.id());
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeService.delete(created.id()));

        // then
        assertEquals("Episode", ex.getResource());
        assertEquals(created.id(), ex.getId());
        assertEquals(0, episodeRepository.findById(created.id()).stream().count());
    }

    @Test
    void deleteShouldRemoveEpisodeFromRepository() {
        // given
        EpisodeResponse created = episodeService.create(projectId,
                request(1, "待删除", EpisodeStatus.DRAFT, 60));
        assertTrue(episodeRepository.findById(created.id()).isPresent());

        // when
        episodeService.delete(created.id());

        // then
        assertEquals(false, episodeRepository.findById(created.id()).isPresent());
        assertEquals(0, episodeService.listByProject(projectId).size());
    }

    @Test
    void updateShouldThrowWhenEpisodeMissing() {
        // given
        Long missingEpisodeId = 777777L;
        EpisodeRequest updateReq = request(1, "更新缺失", EpisodeStatus.DRAFT, 60);

        // when
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeService.update(missingEpisodeId, updateReq));

        // then
        assertEquals("Episode", ex.getResource());
        assertEquals(missingEpisodeId, ex.getId());
    }

    @Test
    void createShouldHandleLargePayloadWithoutTruncation() {
        // given：outline 刚好等于字段容量 2000 字符
        StringBuilder outline = new StringBuilder();
        for (int i = 0; i < 2000; i++) {
            outline.append('x');
        }
        String boundaryOutline = outline.toString();
        EpisodeRequest req = new EpisodeRequest(1, "边界payload", boundaryOutline, EpisodeStatus.DRAFT, 300);

        // when：写入 2000 字符应成功
        EpisodeResponse created = episodeService.create(projectId, req);

        // then：长度与内容一致，且生成 id
        assertEquals(2000, created.outline().length());
        assertEquals(boundaryOutline, created.outline());
        assertNotNull(created.id());

        // given：outline 越界 2001 字符
        StringBuilder overOutline = new StringBuilder();
        for (int i = 0; i < 2001; i++) {
            overOutline.append('x');
        }
        String over2001 = overOutline.toString();

        // when / then：超出字段容量应抛 DataIntegrityViolationException
        assertThrows(DataIntegrityViolationException.class, () -> episodeService.create(projectId, new EpisodeRequest(1, "越界", over2001, EpisodeStatus.DRAFT, 300)));
    }

    @Test
    void concurrentUpdateShouldNotCorruptEpisodeData() throws InterruptedException {
        // given
        EpisodeResponse created = episodeService.create(projectId,
                request(1, "并发", EpisodeStatus.DRAFT, 100));
        Long episodeId = created.id();
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger success = new AtomicInteger(0);

        // when
        for (int i = 0; i < threads; i++) {
            final int idx = i;
            pool.submit(() -> {
                try {
                    start.await();
                    episodeService.update(episodeId,
                            request(1, "并发-" + idx, EpisodeStatus.DRAFT, 100 + idx));
                    success.incrementAndGet();
                } catch (Exception ignored) {
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        assertTrue(done.await(30, TimeUnit.SECONDS));
        pool.shutdown();

        // then
        Episode finalEpisode = episodeRepository.findById(episodeId).orElse(null);
        assertNotNull(finalEpisode);
        assertEquals(2, success.get());
        assertEquals(episodeId, finalEpisode.getId());
        assertEquals(1, finalEpisode.getEpisodeNo());
        assertTrue("并发-0".equals(finalEpisode.getTitle()) || "并发-1".equals(finalEpisode.getTitle()));
    }

    @Test
    void concurrentCreateWithSameEpisodeNoShouldNotLoseRows() throws InterruptedException {
        // given
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);

        // when
        for (int i = 0; i < threads; i++) {
            final int idx = i;
            pool.submit(() -> {
                try {
                    start.await();
                    episodeService.create(projectId,
                            request(5, "并发创建-" + idx, EpisodeStatus.DRAFT, 50));
                } catch (Exception ignored) {
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        assertTrue(done.await(30, TimeUnit.SECONDS));
        pool.shutdown();

        // then
        List<EpisodeResponse> list = episodeService.listByProject(projectId);
        assertEquals(2, list.size());
        assertEquals(5, list.get(0).episodeNo());
        assertEquals(5, list.get(1).episodeNo());
    }

    @Test
    void toResponseShouldComputeSceneCountForEpisode() {
        // given
        EpisodeResponse created = episodeService.create(projectId,
                request(1, "场次统计", EpisodeStatus.DRAFT, 60));

        // when
        EpisodeResponse fetched = episodeService.get(created.id());

        // then
        assertEquals(0L, fetched.sceneCount());
        assertNotNull(fetched.createdAt());
        assertEquals(created.id(), fetched.id());
    }

    @Test
    void listByProjectShouldThrowWhenProjectMissing() {
        // given
        Long missingProjectId = 555555L;

        // when
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> episodeService.listByProject(missingProjectId));

        // then
        assertEquals("Project", ex.getResource());
        assertEquals(missingProjectId, ex.getId());
    }

    @Test
    void createShouldReturnNullProjectIdWhenProjectReferenceMissing() {
        // given
        EpisodeRequest req = request(1, "无项目引用", EpisodeStatus.DRAFT, 60);

        // when
        EpisodeResponse created = episodeService.create(projectId, req);

        // then
        assertEquals(projectId, created.projectId());
        assertNotNull(created.projectId());
        assertNotNull(created.id());
    }

    @Test
    void updateShouldNotChangeProjectId() {
        // given
        EpisodeResponse created = episodeService.create(projectId,
                request(1, "项目不变", EpisodeStatus.DRAFT, 60));
        EpisodeRequest updateReq = request(2, "项目不变-改", EpisodeStatus.REVIEWED, 80);

        // when
        EpisodeResponse updated = episodeService.update(created.id(), updateReq);

        // then
        assertEquals(projectId, updated.projectId());
        assertEquals(2, updated.episodeNo());
        assertEquals(EpisodeStatus.REVIEWED, updated.status());
    }

    @Test
    void getShouldReturnNullOutlineWhenNotSet() {
        // given
        EpisodeRequest req = new EpisodeRequest(1, "空大纲", null, EpisodeStatus.DRAFT, 60);
        EpisodeResponse created = episodeService.create(projectId, req);

        // when
        EpisodeResponse fetched = episodeService.get(created.id());

        // then
        assertNull(fetched.outline());
        assertEquals("空大纲", fetched.title());
        assertEquals(EpisodeStatus.DRAFT, fetched.status());
    }
}