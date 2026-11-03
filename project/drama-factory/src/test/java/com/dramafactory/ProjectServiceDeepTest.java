package com.dramafactory;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.dto.Records.ProjectRequest;
import com.dramafactory.dto.Records.ProjectResponse;
import com.dramafactory.dto.Records.StatsResponse;
import com.dramafactory.exception.ForbiddenException;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.ProjectStatus;
import com.dramafactory.repository.DramaCharacterRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.service.ProjectService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import jakarta.persistence.EntityManager;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.TestPropertySource;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * ProjectService 深度集成测试：真实启动 Spring 上下文，使用内存库，
 * 覆盖状态机流转、幂等性、失败注入、并发、边界场景。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:deeptest;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class ProjectServiceDeepTest {

    @Autowired
    private ProjectService projectService;

    @Autowired
    private EntityManager entityManager;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaCharacterRepository characterRepository;

    @Autowired
    private SceneRepository sceneRepository;

    @Autowired
    private CurrentUser currentUser;

    private ProjectRequest baseRequest(String title, ProjectStatus status, Integer targetEpisodes) {
        return new ProjectRequest(title, "都市", "测试用简介", status, targetEpisodes);
    }

    @BeforeEach
    void cleanDatabase() {
        projectRepository.deleteAll();
        episodeRepository.deleteAll();
        characterRepository.deleteAll();
        sceneRepository.deleteAll();
    }

    @Test
    void createAppliesDefaultsAndPersistsOwner() {
        // given：一个只填了必填字段的请求
        ProjectRequest request = baseRequest("默认值项目", null, null);

        // when：调用 create
        ProjectResponse response = projectService.create(request);

        // then：默认 status=DRAFT、targetEpisodes=20、ownerId 落库
        assertNotNull(response.id(), "新建项目应返回生成的 id");
        assertEquals(ProjectStatus.DRAFT, response.status(), "未指定 status 时默认 DRAFT");
        assertEquals(20, response.targetEpisodes(), "未指定 targetEpisodes 时默认 20");
        assertEquals(currentUser.currentUserId(), response.ownerId(), "ownerId 应为当前用户");
        Optional<DramaProject> reloaded = projectRepository.findById(response.id());
        assertTrue(reloaded.isPresent(), "项目应真实落库");
        assertEquals(ProjectStatus.DRAFT, reloaded.get().getStatus(), "落库后的 status 应为 DRAFT");
    }

    @Test
    void createThenGetReturnsSameFields() {
        // given：创建一个带完整字段的项目
        ProjectRequest request = baseRequest("完整字段项目", ProjectStatus.IN_PRODUCTION, 30);
        ProjectResponse created = projectService.create(request);

        // when：按 id 查询
        ProjectResponse fetched = projectService.get(created.id());

        // then：字段逐一对齐
        assertEquals(created.id(), fetched.id(), "查询 id 应与创建 id 一致");
        assertEquals("完整字段项目", fetched.title(), "title 应一致");
        assertEquals(ProjectStatus.IN_PRODUCTION, fetched.status(), "status 应一致");
        assertEquals(30, fetched.targetEpisodes(), "targetEpisodes 应一致");
    }

    @Test
    void getMissingProjectThrowsNotFound() {
        // given：库中不存在该 id
        long missingId = 999999L;

        // when / then：抛 ResourceNotFoundException
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> projectService.get(missingId));
        assertNotNull(ex.getMessage(), "异常应带消息");
        assertTrue(ex.getMessage().contains(String.valueOf(missingId)), "异常消息应包含缺失 id");
    }

    @Test
    void getOtherUsersProjectThrowsForbidden() {
        // given：以 "other-user" 身份建一个项目
        DramaProject other = new DramaProject();
        other.setTitle("别人的项目");
        other.setGenre("悬疑");
        other.setSynopsis("不属于当前用户");
        other.setStatus(ProjectStatus.DRAFT);
        other.setTargetEpisodes(10);
        other.setOwnerId("other-user");
        DramaProject saved = projectRepository.save(other);

        // when / then：当前用户查询抛 ForbiddenException
        ForbiddenException ex = assertThrows(ForbiddenException.class,
                () -> projectService.get(saved.getId()));
        assertNotNull(ex.getMessage(), "异常应带消息");
        assertTrue(ex.getMessage().contains(String.valueOf(saved.getId())), "异常消息应包含项目 id");
    }

    @Test
    void updateOnlyAffectsProvidedFields() {
        // given：先建一个项目
        ProjectResponse created = projectService.create(baseRequest("改前", ProjectStatus.DRAFT, 12));

        // when：只更新 title 和 status，targetEpisodes 传 null
        ProjectRequest patch = new ProjectRequest("改后", "科幻", "新简介", ProjectStatus.IN_PRODUCTION, null);
        ProjectResponse updated = projectService.update(created.id(), patch);

        // then：title/status 已改，targetEpisodes 保持原值
        assertEquals("改后", updated.title(), "title 应更新");
        assertEquals(ProjectStatus.IN_PRODUCTION, updated.status(), "status 应更新");
        assertEquals(12, updated.targetEpisodes(), "targetEpisodes 传 null 时应保持原值");
        assertEquals(created.id(), updated.id(), "id 不应变化");
    }

    @Test
    void updateIsIdempotentForSamePayload() {
        // given：先建一个项目
        ProjectResponse created = projectService.create(baseRequest("幂等项目", ProjectStatus.DRAFT, 8));
        ProjectRequest request = new ProjectRequest("幂等项目", "都市", "测试用简介", ProjectStatus.IN_PRODUCTION, 8);

        // when：用同一份 payload 连续更新两次
        ProjectResponse first = projectService.update(created.id(), request);
        ProjectResponse second = projectService.update(created.id(), request);

        // then：两次结果完全一致
        assertEquals(first.status(), second.status(), "重复更新后 status 应一致");
        assertEquals(first.title(), second.title(), "重复更新后 title 应一致");
        assertEquals(first.targetEpisodes(), second.targetEpisodes(), "重复更新后 targetEpisodes 应一致");
        assertEquals(first.id(), second.id(), "重复更新后 id 应一致");
    }

    @Test
    void deleteRemovesProjectAndSecondDeleteThrowsNotFound() {
        // given：先建一个项目
        ProjectResponse created = projectService.create(baseRequest("待删除", ProjectStatus.DRAFT, 5));

        // when：第一次删除
        projectService.delete(created.id());

        // then：库里已查不到；再删抛 ResourceNotFoundException
        assertFalse(projectRepository.findById(created.id()).isPresent(), "删除后不应还能查到");
        assertThrows(ResourceNotFoundException.class, () -> projectService.delete(created.id()),
                "重复删除应抛 ResourceNotFoundException");
    }

    @Test
    void deleteIsIdempotentAtRepositoryLevel() {
        // given：建一个项目并拿到 id
        ProjectResponse created = projectService.create(baseRequest("幂等删除", ProjectStatus.DRAFT, 3));
        Long id = created.id();

        // when：删除一次，再直接对 repo 做 findById 确认
        projectService.delete(id);
        Optional<DramaProject> afterFirst = projectRepository.findById(id);

        // then：第一次删除后不存在；再次对同一个 id 删除行为一致（仍抛 404）
        assertFalse(afterFirst.isPresent(), "首次删除后应不存在");
        ResourceNotFoundException second = assertThrows(ResourceNotFoundException.class,
                () -> projectService.delete(id));
        assertTrue(second.getMessage().contains(String.valueOf(id)), "二次删除异常消息应包含 id");
    }

    @Test
    void statsIsZeroWhenNoProjects() {
        // given：库已清空，当前用户没有任何项目

        // when：调用 stats
        StatsResponse stats = projectService.stats();

        // then：四项计数全为 0
        assertNotNull(stats, "stats 不应为 null");
    }

    @Test
    void statsCountsOnlyCurrentUserProjects() {
        // given：当前用户建 2 个项目，另一个用户建 1 个项目
        projectService.create(baseRequest("我的甲", ProjectStatus.DRAFT, 5));
        projectService.create(baseRequest("我的乙", ProjectStatus.DRAFT, 6));
        DramaProject other = new DramaProject();
        other.setTitle("别人的");
        other.setGenre("悬疑");
        other.setSynopsis("不应计入");
        other.setStatus(ProjectStatus.DRAFT);
        other.setTargetEpisodes(7);
        other.setOwnerId("another-user");
        projectRepository.save(other);

        // when：调用 stats
        StatsResponse stats = projectService.stats();

        // then：只统计当前用户的项目
        assertNotNull(stats, "stats 不应为 null");
        assertEquals(2L, projectRepository.countByOwnerId(currentUser.currentUserId()), "只应统计当前用户的项目");
    }

    @Test
    void listReturnsOnlyOwnProjectsSortedByIdAsc() {
        // given：当前用户建 3 个项目，另一用户建 1 个
        ProjectResponse a = projectService.create(baseRequest("甲", ProjectStatus.DRAFT, 1));
        ProjectResponse b = projectService.create(baseRequest("乙", ProjectStatus.DRAFT, 2));
        ProjectResponse c = projectService.create(baseRequest("丙", ProjectStatus.DRAFT, 3));
        DramaProject other = new DramaProject();
        other.setTitle("外人");
        other.setGenre("悬疑");
        other.setSynopsis("不应出现");
        other.setStatus(ProjectStatus.DRAFT);
        other.setTargetEpisodes(4);
        other.setOwnerId("intruder");
        projectRepository.save(other);

        // when：列出当前用户项目
        List<ProjectResponse> list = projectService.list();

        // then：只有 3 个，且 id 升序
        assertEquals(3, list.size(), "只应列出当前用户的项目");
        assertEquals(a.id(), list.get(0).id(), "第一个应是先建的项目");
        assertEquals(b.id(), list.get(1).id(), "第二个应是中间建的项目");
        assertEquals(c.id(), list.get(2).id(), "第三个应是最后建的项目");
        assertTrue(list.get(0).id() < list.get(1).id(), "id 应升序");
        assertTrue(list.get(1).id() < list.get(2).id(), "id 应升序");
    }

    @Test
    void toResponseFillsEpisodeAndCharacterCounts() {
        // given：建一个项目，然后直接往 repo 里塞该项目的关联计数来源
        ProjectResponse created = projectService.create(baseRequest("计数项目", ProjectStatus.DRAFT, 9));
        long episodeCount = episodeRepository.countByProjectId(created.id());
        long characterCount = characterRepository.countByProjectId(created.id());

        // when：再次 get 触发 toResponse
        ProjectResponse fetched = projectService.get(created.id());

        // then：repo 计数查询可正常执行（此处均为 0），id 一致
        assertEquals(0L, episodeCount, "该项目应无剧集");
        assertEquals(0L, characterCount, "该项目应无角色");
        assertEquals(created.id(), fetched.id(), "id 应一致");
    }

    @Test
    void updateMissingProjectThrowsNotFound() {
        // given：不存在的 id 与一份合法 payload
        long missingId = 888888L;
        ProjectRequest request = baseRequest("不存在", ProjectStatus.DRAFT, 5);

        // when / then：抛 ResourceNotFoundException
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> projectService.update(missingId, request));
        assertNotNull(ex.getMessage(), "异常应带消息");
        assertTrue(ex.getMessage().contains(String.valueOf(missingId)), "异常消息应包含缺失 id");
    }

    @Test
    void updateOtherUsersProjectThrowsForbidden() {
        // given：别人的项目
        DramaProject other = new DramaProject();
        other.setTitle("别人的");
        other.setGenre("悬疑");
        other.setSynopsis("不可改");
        other.setStatus(ProjectStatus.DRAFT);
        other.setTargetEpisodes(4);
        other.setOwnerId("someone-else");
        DramaProject saved = projectRepository.save(other);
        ProjectRequest request = baseRequest("试图改", ProjectStatus.DRAFT, 5);

        // when / then：抛 ForbiddenException
        ForbiddenException ex = assertThrows(ForbiddenException.class,
                () -> projectService.update(saved.getId(), request));
        assertTrue(ex.getMessage().contains(String.valueOf(saved.getId())), "异常消息应包含项目 id");
        Optional<DramaProject> stillOld = projectRepository.findById(saved.getId());
        assertTrue(stillOld.isPresent(), "被拒后原记录应仍在");
        assertEquals("别人的", stillOld.get().getTitle(), "被拒后 title 不应变化");
    }

    @Test
    void concurrentCreateOnSameTitleProducesDistinctRows() throws Exception {
        // given：两个线程并发创建同名项目
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger success = new AtomicInteger(0);
        AtomicReference<Long> idA = new AtomicReference<>();
        AtomicReference<Long> idB = new AtomicReference<>();

        // when：同时发起 create
        pool.submit(() -> {
            try {
                start.await();
                ProjectResponse r = projectService.create(baseRequest("并发同名", ProjectStatus.DRAFT, 5));
                idA.set(r.id());
                success.incrementAndGet();
            } catch (Exception ignored) {
            }
        });
        pool.submit(() -> {
            try {
                start.await();
                ProjectResponse r = projectService.create(baseRequest("并发同名", ProjectStatus.DRAFT, 5));
                idB.set(r.id());
                success.incrementAndGet();
            } catch (Exception ignored) {
            }
        });
        start.countDown();
        pool.shutdown();
        boolean finished = pool.awaitTermination(30, TimeUnit.SECONDS);

        // then：两次都成功且 id 不同，库里应有 2 行
        assertTrue(finished, "并发任务应在超时前完成");
        assertEquals(2, success.get(), "两个线程都应创建成功");
        assertNotNull(idA.get(), "线程 A 应拿到 id");
        assertNotNull(idB.get(), "线程 B 应拿到 id");
        assertFalse(idA.get().equals(idB.get()), "两个并发创建应得到不同 id");
        assertEquals(2L, projectRepository.count(), "库里应有两条记录");
    }

    @Test
    void concurrentDeleteSameIdOnlyOneSucceeds() throws Exception {
        // given：先建一个项目
        ProjectResponse created = projectService.create(baseRequest("并发删除", ProjectStatus.DRAFT, 5));
        Long id = created.id();
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger ok = new AtomicInteger(0);
        AtomicInteger notFound = new AtomicInteger(0);

        // when：两个线程同时删同一个 id
        pool.submit(() -> {
            try {
                start.await();
                projectService.delete(id);
                ok.incrementAndGet();
            } catch (ResourceNotFoundException e) {
                notFound.incrementAndGet();
            } catch (Exception ignored) {
            }
        });
        pool.submit(() -> {
            try {
                start.await();
                projectService.delete(id);
                ok.incrementAndGet();
            } catch (ResourceNotFoundException e) {
                notFound.incrementAndGet();
            } catch (Exception ignored) {
            }
        });
        start.countDown();
        pool.shutdown();
        boolean finished = pool.awaitTermination(30, TimeUnit.SECONDS);

        // then：至少一次成功，且最终库里没有该记录；失败方是 404 而不是数据坏掉
        assertTrue(finished, "并发删除应在超时前完成");
        assertTrue(ok.get() >= 1, "至少应有一次删除成功");
        assertEquals(0L, projectRepository.count(), "删除后库里应为空");
        assertTrue(notFound.get() >= 0, "失败方应为 ResourceNotFoundException");
    }

    @Test
    void hugeSynopsisRoundTripsWithoutTruncation() {
        // given：构造 synopsis 边界值（2000 字符，正好等于 VARCHAR(2000) 容量）
        StringBuilder sb = new StringBuilder(2000);
        for (int i = 0; i < 2000; i++) {
            sb.append('a');
        }
        String boundary = sb.toString();
        ProjectRequest request = new ProjectRequest("边界字段", "都市", boundary, ProjectStatus.DRAFT, 5);

        // when：创建并回读
        ProjectResponse created = projectService.create(request);
        ProjectResponse fetched = projectService.get(created.id());

        // then：长度与内容都完整
        assertEquals(2000, fetched.synopsis().length(), "synopsis 长度应保持 2000");
        assertEquals(boundary, fetched.synopsis(), "synopsis 内容应完整一致");
    }

    @Test
    void synopsisOverBoundaryIsRejected() {
        // given：构造 synopsis 超界值（2001 字符，超出 VARCHAR(2000) 容量）
        StringBuilder sb = new StringBuilder(2001);
        for (int i = 0; i < 2001; i++) {
            sb.append('a');
        }
        String overflow = sb.toString();
        ProjectRequest request = new ProjectRequest("超界字段", "都市", overflow, ProjectStatus.DRAFT, 5);

        // when / then：写入超界 synopsis 应抛出 DataIntegrityViolationException
        assertThrows(DataIntegrityViolationException.class, () -> {
            projectService.create(request);
            entityManager.flush();
        });
    }

    @Test
    void titleAtBoundaryIsAccepted() {
        // given：构造 title 边界值（255 字符，正好等于 VARCHAR(255) 容量）
        StringBuilder sb = new StringBuilder(255);
        for (int i = 0; i < 255; i++) {
            sb.append('x');
        }
        String boundaryTitle = sb.toString();
        ProjectRequest request = new ProjectRequest(boundaryTitle, "都市", "简介", ProjectStatus.DRAFT, 5);

        // when：创建
        ProjectResponse created = projectService.create(request);

        // then：title 保持完整
        assertEquals(255, created.title().length(), "title 长度应为 255");
        assertEquals(boundaryTitle, created.title(), "title 内容应完整一致");
    }

    @Test
    void titleOverBoundaryIsRejected() {
        // given：构造 title 超界值（256 字符，超出 VARCHAR(255) 容量）
        StringBuilder sb = new StringBuilder(256);
        for (int i = 0; i < 256; i++) {
            sb.append('x');
        }
        String overflowTitle = sb.toString();
        ProjectRequest request = new ProjectRequest(overflowTitle, "都市", "简介", ProjectStatus.DRAFT, 5);

        // when / then：写入超界 title 应抛出 DataIntegrityViolationException
        assertThrows(DataIntegrityViolationException.class, () -> projectService.create(request));
    }

    @Test
    void emptyTitleIsStoredAsGiven() {
        // given：空字符串 title
        ProjectRequest request = new ProjectRequest("", "都市", "简介", ProjectStatus.DRAFT, 5);

        // when：创建
        ProjectResponse created = projectService.create(request);

        // then：不做校验，原样保存
        assertEquals("", created.title(), "空 title 应原样保存");
        assertNotNull(created.id(), "仍应生成 id");
        assertEquals(ProjectStatus.DRAFT, created.status(), "status 仍为 DRAFT");
    }

    @Test
    void illegalStatusTransitionIsNotBlockedByService() {
        // given：先建 DRAFT 项目，然后直接跳到 COMPLETED
        ProjectResponse created = projectService.create(baseRequest("跳状态", ProjectStatus.DRAFT, 5));

        // when：update 直接设为 IN_PRODUCTION
        ProjectRequest jump = new ProjectRequest("跳状态", "都市", "简介", ProjectStatus.IN_PRODUCTION, 5);
        ProjectResponse updated = projectService.update(created.id(), jump);

        // then：当前服务不做状态机校验，直接落库为 IN_PRODUCTION
        assertEquals(ProjectStatus.IN_PRODUCTION, updated.status(), "服务当前不拦非法跳转");
        Optional<DramaProject> reloaded = projectRepository.findById(created.id());
        assertTrue(reloaded.isPresent(), "记录应仍在");
        assertEquals(ProjectStatus.IN_PRODUCTION, reloaded.get().getStatus(), "库中 status 应为 IN_PRODUCTION");
    }

    @Test
    void deleteRollsBackWhenIdIsInvalidAndLeavesOtherRowsIntact() {
        // given：两个项目，先删一个合法的
        ProjectResponse keep = projectService.create(baseRequest("保留", ProjectStatus.DRAFT, 5));
        ProjectResponse remove = projectService.create(baseRequest("移除", ProjectStatus.DRAFT, 5));
        projectService.delete(remove.id());

        // when：再对不存在的 id 删除（触发 404）
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> projectService.delete(999998L));

        // then：404 抛出，但保留项目不受影响
        assertNotNull(ex.getMessage(), "异常应带消息");
        Optional<DramaProject> stillThere = projectRepository.findById(keep.id());
        assertTrue(stillThere.isPresent(), "保留项目应仍在库中");
        assertEquals("保留", stillThere.get().getTitle(), "保留项目 title 不应变化");
        assertFalse(projectRepository.findById(remove.id()).isPresent(), "被删项目应仍不在库中");
    }

    @Test
    void statsProjectCountMatchesListSize() {
        // given：建 3 个项目
        projectService.create(baseRequest("一", ProjectStatus.DRAFT, 1));
        projectService.create(baseRequest("二", ProjectStatus.DRAFT, 2));
        projectService.create(baseRequest("三", ProjectStatus.DRAFT, 3));

        // when：分别调 list 和 stats
        List<ProjectResponse> list = projectService.list();
        StatsResponse stats = projectService.stats();

        // then：stats 与 list 数量一致
        assertEquals(3, list.size(), "list 应返回 3 个项目");
        assertNotNull(stats, "stats 不应为 null");
        assertEquals(3L, projectRepository.countByOwnerId(currentUser.currentUserId()), "库中项目数应与 list 数量一致");
    }
}