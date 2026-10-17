package com.dramafactory;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.repository.DramaCharacterRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.ShotService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ShotServiceDeepTest {

    @Autowired
    private ShotService shotService;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private SceneRepository sceneRepository;

    @Autowired
    private DramaCharacterRepository characterRepository;

    private Long episodeId;

    @BeforeEach
    void setUp() {
        videoTaskRepository.deleteAll();
        shotRepository.deleteAll();
        sceneRepository.deleteAll();
        characterRepository.deleteAll();
        episodeRepository.deleteAll();
        projectRepository.deleteAll();

        DramaProject p = new DramaProject();
        p.setTitle("测试项目");
        DramaProject savedProject = projectRepository.save(p);

        Episode episode = new Episode();
        episode.setTitle("测试剧集");
        episode.setProject(savedProject);
        episode.setEpisodeNo(1);
        Episode saved = episodeRepository.save(episode);
        episodeId = saved.getId();
    }

    private Records.ShotRequest sampleRequest(int shotNo) {
        return new Records.ShotRequest(
                shotNo,
                ShotSize.TE_XIE,
                CameraMove.GU_DING,
                "第 " + shotNo + " 个分镜描述",
                5,
                "台词 " + shotNo,
                "视频提示词 " + shotNo
        );
    }

    @Test
    void createShotThenGetReturnsSameData() {
        // given: 一个已存在的剧集和一条分镜请求
        Records.ShotRequest req = sampleRequest(1);

        // when: 调用 create 创建分镜，再调用 get 查询
        Records.ShotResponse created = shotService.create(episodeId, req);
        Records.ShotResponse fetched = shotService.get(created.id());

        // then: 两次返回的字段一致，且非空
        assertAll(
                () -> assertNotNull(created.id(), "创建后应返回 id"),
                () -> assertEquals(created.id(), fetched.id(), "get 返回的 id 应与创建一致"),
                () -> assertEquals(1, fetched.shotNo(), "分镜号应为 1"),
                () -> assertEquals("第 1 个分镜描述", fetched.description(), "描述应一致"),
                () -> assertEquals(5, fetched.durationSeconds(), "时长应一致")
        );
    }

    @Test
    void createForMissingEpisodeThrowsResourceNotFound() {
        // given: 一个不存在的剧集 id
        Long missingEpisodeId = 999999L;
        Records.ShotRequest req = sampleRequest(1);

        // when: 调用 create
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> shotService.create(missingEpisodeId, req));

        // then: 异常携带正确资源名，并且没有落库
        assertAll(
                () -> assertEquals("Episode", ex.getResource(), "资源名应为 Episode"),
                () -> assertEquals(missingEpisodeId, ex.getId(), "资源 id 应一致"),
                () -> assertEquals(0, shotRepository.count(), "不应写入任何分镜")
        );
    }

    @Test
    void listByEpisodeReturnsShotsOrderedByShotNo() {
        // given: 同一剧集下乱序创建 3 条分镜
        shotService.create(episodeId, sampleRequest(3));
        shotService.create(episodeId, sampleRequest(1));
        shotService.create(episodeId, sampleRequest(2));

        // when: 按剧集查询列表
        List<Records.ShotResponse> list = shotService.listByEpisode(episodeId);

        // then: 数量为 3，且分镜号升序
        assertAll(
                () -> assertEquals(3, list.size(), "应返回 3 条分镜"),
                () -> assertEquals(1, list.get(0).shotNo(), "第 1 条应为分镜号 1"),
                () -> assertEquals(2, list.get(1).shotNo(), "第 2 条应为分镜号 2"),
                () -> assertEquals(3, list.get(2).shotNo(), "第 3 条应为分镜号 3")
        );
    }

    @Test
    void getForMissingShotThrowsResourceNotFound() {
        // given: 一个不存在的分镜 id
        Long missingShotId = 888888L;

        // when: 调用 get
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> shotService.get(missingShotId));

        // then: 异常信息指向 Shot 资源
        assertAll(
                () -> assertEquals("Shot", ex.getResource(), "资源名应为 Shot"),
                () -> assertEquals(missingShotId, ex.getId(), "资源 id 应一致")
        );
    }

    @Test
    void updateChangesAllEditableFields() {
        // given: 先创建一条分镜
        Records.ShotResponse created = shotService.create(episodeId, sampleRequest(1));
        Records.ShotRequest updated = new Records.ShotRequest(
                1,
                ShotSize.QUAN_JING,
                CameraMove.YAO,
                "改过的描述",
                12,
                "改过的台词",
                "改过的提示词"
        );

        // when: 调用 update
        Records.ShotResponse result = shotService.update(created.id(), updated);

        // then: 数据库与返回体都已更新
        Shot fromDb = shotRepository.findById(created.id()).orElseThrow();
        assertAll(
                () -> assertEquals(ShotSize.QUAN_JING, result.shotSize(), "返回体画面大小应更新"),
                () -> assertEquals(CameraMove.YAO, result.cameraMove(), "返回体运镜应更新"),
                () -> assertEquals("改过的描述", fromDb.getDescription(), "数据库描述应更新"),
                () -> assertEquals(12, fromDb.getDurationSeconds(), "数据库时长应更新"),
                () -> assertEquals("改过的提示词", fromDb.getVideoPrompt(), "数据库提示词应更新")
        );
    }

    @Test
    void updateMissingShotThrowsAndLeavesNothingChanged() {
        // given: 先创建一条分镜，再准备一个不存在的 id
        Records.ShotResponse created = shotService.create(episodeId, sampleRequest(1));
        Long missingShotId = 777777L;

        // when: 对不存在的 id 调用 update
        assertThrows(ResourceNotFoundException.class,
                () -> shotService.update(missingShotId, sampleRequest(9)));

        // then: 原分镜保持不变，且总数仍为 1
        Shot original = shotRepository.findById(created.id()).orElseThrow();
        assertAll(
                () -> assertEquals(1, original.getShotNo(), "原分镜号不应被改动"),
                () -> assertEquals("第 1 个分镜描述", original.getDescription(), "原描述不应被改动"),
                () -> assertEquals(1, shotRepository.count(), "分镜总数应保持为 1")
        );
    }

    @Test
    void deleteRemovesShotAndSecondDeleteThrows() {
        // given: 创建一条分镜
        Records.ShotResponse created = shotService.create(episodeId, sampleRequest(1));

        // when: 第一次删除，然后再删一次
        shotService.delete(created.id());
        boolean existsAfterFirst = shotRepository.existsById(created.id());
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> shotService.delete(created.id()));

        // then: 第一次删除生效，第二次抛 ResourceNotFound
        assertAll(
                () -> assertFalse(existsAfterFirst, "第一次删除后记录应不存在"),
                () -> assertEquals("Shot", ex.getResource(), "第二次删除异常资源名应为 Shot"),
                () -> assertEquals(created.id(), ex.getId(), "异常资源 id 应一致")
        );
    }

    @Test
    void reorderAssignsSequentialShotNoFollowingGivenOrder() {
        // given: 创建 3 条分镜
        Records.ShotResponse a = shotService.create(episodeId, sampleRequest(1));
        Records.ShotResponse b = shotService.create(episodeId, sampleRequest(2));
        Records.ShotResponse c = shotService.create(episodeId, sampleRequest(3));

        // when: 按 c, a, b 的顺序重排
        shotService.reorder(episodeId, List.of(c.id(), a.id(), b.id()));

        // then: 分镜号按传入顺序变为 1,2,3
        Shot shotC = shotRepository.findById(c.id()).orElseThrow();
        Shot shotA = shotRepository.findById(a.id()).orElseThrow();
        Shot shotB = shotRepository.findById(b.id()).orElseThrow();
        assertAll(
                () -> assertEquals(1, shotC.getShotNo(), "c 应为 1"),
                () -> assertEquals(2, shotA.getShotNo(), "a 应为 2"),
                () -> assertEquals(3, shotB.getShotNo(), "b 应为 3")
        );
    }

    @Test
    void reorderWithEmptyOrNullListDoesNothing() {
        // given: 创建 2 条分镜，记录当前顺序
        Records.ShotResponse a = shotService.create(episodeId, sampleRequest(1));
        Records.ShotResponse b = shotService.create(episodeId, sampleRequest(2));

        // when: 分别传入空列表和 null
        shotService.reorder(episodeId, List.of());
        shotService.reorder(episodeId, null);

        // then: 分镜号保持原样
        Shot shotA = shotRepository.findById(a.id()).orElseThrow();
        Shot shotB = shotRepository.findById(b.id()).orElseThrow();
        assertAll(
                () -> assertEquals(1, shotA.getShotNo(), "a 应仍为 1"),
                () -> assertEquals(2, shotB.getShotNo(), "b 应仍为 2")
        );
    }

    @Test
    void reorderWithShotFromOtherEpisodeThrowsAndRollsBack() {
        // given: 当前剧集有 2 条分镜，另建一个剧集并放入 1 条分镜
        Records.ShotResponse a = shotService.create(episodeId, sampleRequest(1));
        Records.ShotResponse b = shotService.create(episodeId, sampleRequest(2));

        DramaProject otherProject = new DramaProject();
        otherProject.setTitle("另一个项目");
        otherProject = projectRepository.save(otherProject);
        Episode otherEpisode = new Episode();
        otherEpisode.setTitle("另一个剧集");
        otherEpisode.setProject(otherProject);
        otherEpisode.setEpisodeNo(2);
        Episode savedOther = episodeRepository.save(otherEpisode);
        Records.ShotResponse foreign = shotService.create(savedOther.getId(), sampleRequest(1));

        // when: 把外来分镜混进当前剧集的重排
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> shotService.reorder(episodeId, List.of(a.id(), foreign.id())));

        // then: 抛异常，且事务回滚后原分镜号未变
        Shot shotA = shotRepository.findById(a.id()).orElseThrow();
        Shot shotB = shotRepository.findById(b.id()).orElseThrow();
        assertAll(
                () -> assertTrue(ex.getMessage().contains("不属于剧集"), "异常信息应说明归属错误"),
                () -> assertEquals(1, shotA.getShotNo(), "a 应保持 1"),
                () -> assertEquals(2, shotB.getShotNo(), "b 应保持 2")
        );
    }

    @Test
    void reorderWithMissingIdThrowsIllegalArgument() {
        // given: 创建 1 条分镜，准备一个不存在的 id
        Records.ShotResponse a = shotService.create(episodeId, sampleRequest(1));
        Long missingShotId = 666666L;

        // when: 传入包含不存在 id 的列表
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> shotService.reorder(episodeId, List.of(a.id(), missingShotId)));

        // then: 异常信息指出存在无效 id，且原分镜号未变
        Shot shotA = shotRepository.findById(a.id()).orElseThrow();
        assertAll(
                () -> assertEquals("存在无效的分镜 id", ex.getMessage(), "异常信息应一致"),
                () -> assertEquals(1, shotA.getShotNo(), "a 应保持 1")
        );
    }

    @Test
    void createWithLargePayloadStoresFullText() {
        // given: 大 payload（长度 3600 的描述与提示词，在 VARCHAR(2000) 列限内）
        String bigDescription = "描".repeat(1800);
        String bigPrompt = "词".repeat(1800);
        Records.ShotRequest req = new Records.ShotRequest(
                1,
                ShotSize.ZHONG_JING,
                CameraMove.TUI,
                bigDescription,
                30,
                "一句台词",
                bigPrompt
        );

        // when: 创建后从数据库读取
        Records.ShotResponse created = shotService.create(episodeId, req);
        Shot fromDb = shotRepository.findById(created.id()).orElseThrow();

        // then: 大字段完整保存，长度一致
        assertAll(
                () -> assertEquals(1800, fromDb.getDescription().length(), "描述长度应为 1800"),
                () -> assertEquals(1800, fromDb.getVideoPrompt().length(), "提示词长度应为 1800"),
                () -> assertEquals(bigDescription, fromDb.getDescription(), "描述内容应完全一致")
        );
    }

    @Test
    void createIsIdempotentWhenSameRequestSentTwice() {
        // given: 同一个剧集下的同一条请求
        Records.ShotRequest req = sampleRequest(1);

        // when: 连续调用两次 create
        Records.ShotResponse first = shotService.create(episodeId, req);
        Records.ShotResponse second = shotService.create(episodeId, req);

        // then: 两次都是新记录，id 不同但字段一致，总数为 2
        assertAll(
                () -> assertNotNull(first.id(), "第一次应有 id"),
                () -> assertNotNull(second.id(), "第二次应有 id"),
                () -> assertTrue(!first.id().equals(second.id()), "两次应生成不同记录"),
                () -> assertEquals(first.description(), second.description(), "字段应一致"),
                () -> assertEquals(2, shotRepository.count(), "应存在 2 条分镜")
        );
    }

    @Test
    void updateIsIdempotentWhenSameRequestSentTwice() {
        // given: 创建一条分镜，准备同一份更新请求
        Records.ShotResponse created = shotService.create(episodeId, sampleRequest(1));
        Records.ShotRequest updated = new Records.ShotRequest(
                1,
                ShotSize.QUAN_JING,
                CameraMove.YAO,
                "稳定描述",
                9,
                "稳定台词",
                "稳定提示词"
        );

        // when: 连续调用两次 update
        Records.ShotResponse first = shotService.update(created.id(), updated);
        Records.ShotResponse second = shotService.update(created.id(), updated);

        // then: 两次结果完全一致，数据库只有 1 条记录
        assertAll(
                () -> assertEquals(first.description(), second.description(), "两次描述应一致"),
                () -> assertEquals(first.durationSeconds(), second.durationSeconds(), "两次时长应一致"),
                () -> assertEquals(first.cameraMove(), second.cameraMove(), "两次运镜应一致"),
                () -> assertEquals(1, shotRepository.count(), "仍应只有 1 条分镜")
        );
    }

    @Test
    void deleteIsIdempotentWhenSecondCallThrowsResourceNotFound() {
        // given: 创建一条分镜
        Records.ShotResponse created = shotService.create(episodeId, sampleRequest(1));

        // when: 删除一次，再删除一次
        shotService.delete(created.id());
        ResourceNotFoundException firstRepeat = assertThrows(ResourceNotFoundException.class,
                () -> shotService.delete(created.id()));
        ResourceNotFoundException secondRepeat = assertThrows(ResourceNotFoundException.class,
                () -> shotService.delete(created.id()));

        // then: 两次重复删除抛出同样类型和同样资源信息
        assertAll(
                () -> assertEquals(firstRepeat.getResource(), secondRepeat.getResource(), "资源名应一致"),
                () -> assertEquals(firstRepeat.getId(), secondRepeat.getId(), "资源 id 应一致"),
                () -> assertEquals(0, shotRepository.count(), "应无剩余分镜")
        );
    }

    @Test
    void illegalStateTransitionFromDeleteToUpdateThrows() {
        // given: 创建一条分镜并删除
        Records.ShotResponse created = shotService.create(episodeId, sampleRequest(1));
        shotService.delete(created.id());

        // when: 对已删除的分镜执行 update
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> shotService.update(created.id(), sampleRequest(5)));

        // then: 抛出资源不存在，且数据库仍为空
        assertAll(
                () -> assertEquals("Shot", ex.getResource(), "资源名应为 Shot"),
                () -> assertEquals(created.id(), ex.getId(), "资源 id 应一致"),
                () -> assertEquals(0, shotRepository.count(), "数据库中不应有记录")
        );
    }

    @Test
    void listByEpisodeForUnknownEpisodeReturnsEmptyList() {
        // given: 一个不存在的剧集 id
        Long missingEpisodeId = 555555L;

        // when: 查询该剧集下的分镜
        List<Records.ShotResponse> list = shotService.listByEpisode(missingEpisodeId);

        // then: 返回空列表，且不影响已有数据
        assertAll(
                () -> assertNotNull(list, "返回值不应为 null"),
                () -> assertTrue(list.isEmpty(), "应为空列表"),
                () -> assertEquals(0, shotRepository.count(), "数据库中不应有分镜")
        );
    }

    @Test
    void concurrentCreateOnSameEpisodeKeepsDataConsistent() throws Exception {
        // given: 两个线程并发向同一剧集创建分镜
        int threadCount = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threadCount);
        CountDownLatch ready = new CountDownLatch(threadCount);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger successCount = new AtomicInteger(0);

        // when: 同时启动两个创建任务
        for (int i = 0; i < threadCount; i++) {
            final int shotNo = i + 1;
            pool.submit(() -> {
                ready.countDown();
                try {
                    start.await();
                    shotService.create(episodeId, sampleRequest(shotNo));
                    successCount.incrementAndGet();
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                }
            });
        }
        ready.await(5, TimeUnit.SECONDS);
        start.countDown();
        pool.shutdown();
        boolean finished = pool.awaitTermination(30, TimeUnit.SECONDS);

        // then: 两个线程都成功，数据库中有 2 条记录
        assertAll(
                () -> assertTrue(finished, "线程池应在 30 秒内结束"),
                () -> assertEquals(2, successCount.get(), "两个线程都应成功创建"),
                () -> assertEquals(2, shotRepository.count(), "数据库中应有 2 条分镜")
        );
    }

    @Test
    void concurrentUpdateOnSameShotKeepsSingleRow() throws Exception {
        // given: 先创建一条分镜，两个线程并发更新它
        Records.ShotResponse created = shotService.create(episodeId, sampleRequest(1));
        int threadCount = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threadCount);
        CountDownLatch ready = new CountDownLatch(threadCount);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger successCount = new AtomicInteger(0);

        // when: 同时启动两个更新任务
        for (int i = 0; i < threadCount; i++) {
            final int marker = i + 100;
            pool.submit(() -> {
                ready.countDown();
                try {
                    start.await();
                    Records.ShotRequest req = new Records.ShotRequest(
                            1,
                            ShotSize.ZHONG_JING,
                            CameraMove.GU_DING,
                            "并发描述-" + marker,
                            marker,
                            "并发台词-" + marker,
                            "并发提示词-" + marker
                    );
                    shotService.update(created.id(), req);
                    successCount.incrementAndGet();
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                }
            });
        }
        ready.await(5, TimeUnit.SECONDS);
        start.countDown();
        pool.shutdown();
        boolean finished = pool.awaitTermination(30, TimeUnit.SECONDS);

        // then: 两个线程都执行，但数据库中始终只有 1 条记录且字段完整
        Shot fromDb = shotRepository.findById(created.id()).orElseThrow();
        assertAll(
                () -> assertTrue(finished, "线程池应在 30 秒内结束"),
                () -> assertEquals(2, successCount.get(), "两个更新线程都应完成"),
                () -> assertEquals(1, shotRepository.count(), "更新不应产生新记录"),
                () -> assertNotNull(fromDb.getDescription(), "描述字段不应为 null"),
                () -> assertTrue(fromDb.getDescription().startsWith("并发描述-"), "描述应是并发写入的值")
        );
    }

    @Test
    void concurrentReorderAndListKeepsShotNumbersValid() throws Exception {
        // given: 创建 3 条分镜，一个线程重排，另一个线程反复读取列表
        Records.ShotResponse a = shotService.create(episodeId, sampleRequest(1));
        Records.ShotResponse b = shotService.create(episodeId, sampleRequest(2));
        Records.ShotResponse c = shotService.create(episodeId, sampleRequest(3));
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger listReads = new AtomicInteger(0);

        // when: 并发执行重排与列表查询
        pool.submit(() -> {
            try {
                start.await();
                shotService.reorder(episodeId, List.of(c.id(), a.id(), b.id()));
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
        });
        pool.submit(() -> {
            try {
                start.await();
                for (int i = 0; i < 5; i++) {
                    List<Records.ShotResponse> list = shotService.listByEpisode(episodeId);
                    if (list.size() == 3) {
                        listReads.incrementAndGet();
                    }
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
        });
        start.countDown();
        pool.shutdown();
        boolean finished = pool.awaitTermination(30, TimeUnit.SECONDS);

        // then: 线程正常结束，最终分镜号按重排顺序落定
        Shot shotC = shotRepository.findById(c.id()).orElseThrow();
        Shot shotA = shotRepository.findById(a.id()).orElseThrow();
        Shot shotB = shotRepository.findById(b.id()).orElseThrow();
        assertAll(
                () -> assertTrue(finished, "线程池应在 30 秒内结束"),
                () -> assertEquals(5, listReads.get(), "5 次读取都应拿到 3 条记录"),
                () -> assertEquals(1, shotC.getShotNo(), "c 应为 1"),
                () -> assertEquals(2, shotA.getShotNo(), "a 应为 2"),
                () -> assertEquals(3, shotB.getShotNo(), "b 应为 3"),
                () -> assertEquals(3, shotRepository.count(), "分镜总数应为 3")
        );
    }

    @Test
    void createThenDeleteThenRecreateProducesDistinctId() {
        // given: 先创建一条分镜并删除
        Records.ShotResponse first = shotService.create(episodeId, sampleRequest(1));
        shotService.delete(first.id());
        Optional<Shot> afterDelete = shotRepository.findById(first.id());

        // when: 再次创建同样请求
        Records.ShotResponse second = shotService.create(episodeId, sampleRequest(1));

        // then: 旧 id 不存在，新 id 不同，数据库只有新记录
        assertAll(
                () -> assertFalse(afterDelete.isPresent(), "删除后旧 id 应查不到"),
                () -> assertTrue(!first.id().equals(second.id()), "重建应生成新 id"),
                () -> assertEquals(1, shotRepository.count(), "数据库应只有 1 条新记录"),
                () -> assertEquals("第 1 个分镜描述", second.description(), "新记录字段应正确")
        );
    }
}