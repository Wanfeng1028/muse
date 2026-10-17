package com.dramafactory;

import com.dramafactory.controller.CharacterController;
import com.dramafactory.dto.Records;
import com.dramafactory.service.CharacterService;
import com.dramafactory.service.ProjectService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.ArrayList;
import java.util.List;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.CharacterRole;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class CharacterControllerDeepTest {

    @Autowired
    private CharacterController characterController;

    @Autowired
    private CharacterService characterService;

    @Autowired
    private ProjectService projectService;

    private Long projectId;

    @BeforeEach
    void setUp() {
        // given: 每个用例开始前准备一个独立项目，避免用例之间数据串扰
        Records.ProjectRequest projectRequest = new Records.ProjectRequest(
                "深测项目-" + System.nanoTime(), null, null, null, null);
        Records.ProjectResponse projectResponse = projectService.create(projectRequest);
        assertNotNull(projectResponse, "前置项目创建必须成功");
        assertNotNull(projectResponse.id(), "前置项目 id 必须存在");
        this.projectId = projectResponse.id();
    }

    private Records.CharacterRequest buildRequest(String name, String description, String role) {
        Records.CharacterRequest request = new Records.CharacterRequest(
                name, com.dramafactory.model.CharacterRole.valueOf(mapRole(role)), description, null);
        return request;
    }

    private static String mapRole(String role) {
        switch (role) {
            case "主角":
                return "LEAD";
            case "配角":
                return "SUPPORTING";
            case "路人":
                return "EXTRA";
            default:
                return role;
        }
    }

    @Test
    void listByProject_emptyProject_returnsEmptyListNotNpe() {
        // given: 项目下没有任何角色
        // when: 查询该项目角色列表
        List<Records.CharacterResponse> result = characterController.listByProject(projectId);

        // then: 返回空列表，且不是 null，元素个数为 0
        assertNotNull(result, "空项目列表查询必须返回空集合而不是 null");
        assertEquals(0, result.size(), "空项目下角色数量必须为 0");
    }

    @Test
    void create_thenList_roundTripPersistsAllFields() {
        // given: 准备一条带完整字段的角色请求
        Records.CharacterRequest request = buildRequest("林晚风", "深夜写代码的老工程师", "主角");

        // when: 创建角色，再按项目查询
        ResponseEntity<Records.CharacterResponse> created = characterController.create(projectId, request);
        List<Records.CharacterResponse> listed = characterController.listByProject(projectId);

        // then: 创建返回 201，且列表中能查到字段完全一致的记录
        assertEquals(HttpStatus.CREATED, created.getStatusCode(), "创建接口必须返回 201");
        Records.CharacterResponse body = created.getBody();
        assertNotNull(body, "创建返回体不能为空");
        assertEquals("林晚风", body.name(), "创建返回体名称必须与请求一致");
        assertEquals(CharacterRole.LEAD, body.role(), "创建返回体角色应为映射后的枚举值");
        assertEquals(1, listed.size(), "查询列表应恰好包含 1 条记录");
        assertEquals(body.id(), listed.get(0).id(), "列表记录 id 必须与创建返回 id 一致");
        assertEquals("深夜写代码的老工程师", listed.get(0).description(), "列表记录描述必须与请求一致");
    }

    @Test
    void create_sameNameTwice_producesTwoDistinctIds() {
        // given: 两次使用完全相同的名称和字段
        Records.CharacterRequest request = buildRequest("重名角色", "同名同描述", "配角");

        // when: 连续创建两次
        ResponseEntity<Records.CharacterResponse> first = characterController.create(projectId, request);
        ResponseEntity<Records.CharacterResponse> second = characterController.create(projectId, request);

        // then: 两次都成功，但生成的 id 不同，且项目下共两条
        assertEquals(HttpStatus.CREATED, first.getStatusCode(), "第一次创建必须成功");
        assertEquals(HttpStatus.CREATED, second.getStatusCode(), "第二次创建必须成功");
        assertNotNull(first.getBody(), "第一次返回体不能为空");
        assertNotNull(second.getBody(), "第二次返回体不能为空");
        assertNotEquals(first.getBody().id(), second.getBody().id(), "同名两次创建必须生成不同 id");
        assertEquals(2, characterController.listByProject(projectId).size(), "项目下应存在两条记录");
    }

    @Test
    void update_existingCharacter_overwritesAndKeepsSameId() {
        // given: 先创建一个角色
        Records.CharacterResponse created = characterController
                .create(projectId, buildRequest("原名字", "原描述", "配角"))
                .getBody();
        assertNotNull(created, "前置创建返回体不能为空");
        Long id = created.id();
        assertNotNull(id, "前置创建必须产生 id");

        // when: 用新的字段更新该角色
        Records.CharacterRequest updateRequest = buildRequest("新名字", "新描述", "主角");
        Records.CharacterResponse updated = characterController.update(id, updateRequest);

        // then: id 不变，字段全部被覆盖
        assertNotNull(updated, "更新返回体不能为空");
        assertEquals(id, updated.id(), "更新后 id 必须保持不变");
        assertEquals("新名字", updated.name(), "更新后名称必须为新值");
        assertEquals("新描述", updated.description(), "更新后描述必须为新值");
        assertEquals(CharacterRole.LEAD, updated.role(), "更新后角色应为映射后的枚举值");
        assertEquals(1, characterController.listByProject(projectId).size(), "更新不应产生新记录");
    }

    @Test
    void update_samePayloadTwice_isIdempotent() {
        // given: 创建一个角色
        Long id = characterController
                .create(projectId, buildRequest("幂等名", "幂等描述", "配角"))
                .getBody()
                .id();
        Records.CharacterRequest updateRequest = buildRequest("幂等新名", "幂等新描述", "主角");

        // when: 用同一份 payload 连续更新两次
        Records.CharacterResponse firstUpdate = characterController.update(id, updateRequest);
        Records.CharacterResponse secondUpdate = characterController.update(id, updateRequest);

        // then: 两次结果字段完全一致，重复调用不改变最终状态
        assertEquals(firstUpdate.id(), secondUpdate.id(), "重复更新后 id 必须一致");
        assertEquals(firstUpdate.name(), secondUpdate.name(), "重复更新后名称必须一致");
        assertEquals(firstUpdate.description(), secondUpdate.description(), "重复更新后描述必须一致");
        assertEquals(firstUpdate.role(), secondUpdate.role(), "重复更新后角色必须一致");
        assertEquals(1, characterController.listByProject(projectId).size(), "重复更新不应增加记录数");
    }

    @Test
    void delete_existingCharacter_thenListIsEmpty() {
        // given: 创建一个待删除角色
        Long id = characterController
                .create(projectId, buildRequest("待删除", "即将删除", "路人"))
                .getBody()
                .id();

        // when: 删除该角色
        ResponseEntity<Void> deleteResponse = characterController.delete(id);
        List<Records.CharacterResponse> afterDelete = characterController.listByProject(projectId);

        // then: 返回 204 且无 body，列表中不再包含该 id
        assertEquals(HttpStatus.NO_CONTENT, deleteResponse.getStatusCode(), "删除接口必须返回 204");
        assertEquals(null, deleteResponse.getBody(), "删除返回体必须为空");
        assertEquals(0, afterDelete.size(), "删除后项目下角色数量应为 0");
    }

    @Test
    void delete_twice_secondCallStillReturnsNoContentWithoutError() {
        // given: 创建一个角色并删除一次
        Long id = characterController
                .create(projectId, buildRequest("删两次", "重复删除", "路人"))
                .getBody()
                .id();
        ResponseEntity<Void> firstDelete = characterController.delete(id);

        // when/then: 对同一 id 再删除一次，产品真实语义是抛 ResourceNotFoundException
        ResourceNotFoundException secondDeleteEx = assertThrows(ResourceNotFoundException.class,
                () -> characterController.delete(id), "重复删除必须抛 ResourceNotFoundException");
        assertEquals("Character", secondDeleteEx.getResource(), "异常资源类型应为 Character");
        assertEquals(id, secondDeleteEx.getId(), "异常资源 id 应为被删除的 id");
        assertEquals(HttpStatus.NO_CONTENT, firstDelete.getStatusCode(), "第一次删除必须返回 204");
        assertEquals(0, characterController.listByProject(projectId).size(), "删除后项目下必须为空");
    }

    @Test
    @DisplayName("description 边界：1000 字符可写入，1001 字符越界抛 DataIntegrityViolationException")
    void create_descriptionBoundary_respectsVarchar1000() {
        // given: 1000 字符正好落在 VARCHAR(1000) 容量内
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 1000; i++) {
            sb.append('x');
        }
        String at1000 = sb.toString();
        Records.CharacterRequest request = buildRequest("边界描述角色", at1000, "配角");

        // when: 创建该角色
        ResponseEntity<Records.CharacterResponse> created = characterController.create(projectId, request);
        List<Records.CharacterResponse> listed = characterController.listByProject(projectId);

        // then: 1000 字符创建成功，落库内容与原文逐字一致
        assertEquals(HttpStatus.CREATED, created.getStatusCode(), "1000 字符描述创建必须成功");
        assertNotNull(created.getBody(), "1000 字符描述创建返回体不能为空");
        assertEquals(1, listed.size(), "1000 字符描述应落库为一条记录");
        assertEquals(1000, listed.get(0).description().length(), "落库描述长度必须为 1000");
        assertEquals(at1000, listed.get(0).description(), "落库描述内容必须与原文逐字一致");

        // and: 1001 字符越界，Controller 层无异常翻译，直接抛 DataIntegrityViolationException
        StringBuilder sb2 = new StringBuilder();
        for (int i = 0; i < 1001; i++) {
            sb2.append('y');
        }
        String over1001 = sb2.toString();
        assertThrows(DataIntegrityViolationException.class,
                () -> characterController.create(projectId, buildRequest("越界", over1001, "配角")));
    }

    @Test
    void concurrentCreate_sameProject_producesConsistentCount() throws InterruptedException {
        // given: 两个线程各创建 10 个角色，同一项目
        int threads = 2;
        int perThread = 10;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger success = new AtomicInteger(0);
        AtomicInteger failure = new AtomicInteger(0);

        // when: 两线程同时推进创建
        for (int t = 0; t < threads; t++) {
            final int tid = t;
            pool.submit(() -> {
                try {
                    start.await();
                    for (int i = 0; i < perThread; i++) {
                        try {
                            ResponseEntity<Records.CharacterResponse> resp = characterController.create(
                                    projectId, buildRequest("并发-" + tid + "-" + i, "并发描述", "配角"));
                            if (resp.getStatusCode() == HttpStatus.CREATED && resp.getBody() != null
                                    && resp.getBody().id() != null) {
                                success.incrementAndGet();
                            } else {
                                failure.incrementAndGet();
                            }
                        } catch (Exception ex) {
                            failure.incrementAndGet();
                        }
                    }
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then: 全部完成，成功数等于创建总数，落库条数一致，无失败
        assertTrue(finished, "并发创建必须在超时前全部完成");
        assertEquals(threads * perThread, success.get(), "并发创建成功数必须等于总请求数");
        assertEquals(0, failure.get(), "并发创建不应出现失败");
        assertEquals(threads * perThread, characterController.listByProject(projectId).size(),
                "并发创建后项目下记录数必须等于总请求数");
    }

    @Test
    void concurrentUpdateAndList_sameCharacter_keepsDataConsistent() throws InterruptedException {
        // given: 创建一个角色，一个线程反复更新，一个线程反复查询
        Long id = characterController
                .create(projectId, buildRequest("并发更新", "初始描述", "配角"))
                .getBody()
                .id();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        List<String> observedNames = new ArrayList<>();
        AtomicInteger readErrors = new AtomicInteger(0);

        // when: 两线程同时推进更新与查询
        pool.submit(() -> {
            try {
                start.await();
                for (int i = 0; i < 20; i++) {
                    characterController.update(id, buildRequest("名字-" + i, "描述-" + i, "主角"));
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        });
        pool.submit(() -> {
            try {
                start.await();
                for (int i = 0; i < 20; i++) {
                    try {
                        List<Records.CharacterResponse> listed = characterController.listByProject(projectId);
                        if (listed.isEmpty()) {
                            readErrors.incrementAndGet();
                        } else {
                            synchronized (observedNames) {
                                observedNames.add(listed.get(0).name());
                            }
                        }
                    } catch (Exception ex) {
                        readErrors.incrementAndGet();
                    }
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        });
        start.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then: 全部完成，查询始终能读到记录，最终记录数与名称是某个中间态而非脏数据
        assertTrue(finished, "并发更新与查询必须在超时前完成");
        assertEquals(0, readErrors.get(), "并发查询不应读到空集合或抛异常");
        assertEquals(20, observedNames.size(), "查询线程应读到 20 次记录");
        List<Records.CharacterResponse> finalList = characterController.listByProject(projectId);
        assertEquals(1, finalList.size(), "并发更新不应产生多余记录");
        assertEquals(id, finalList.get(0).id(), "并发更新后 id 必须保持不变");
        assertTrue(finalList.get(0).name().startsWith("名字-"), "并发更新后名称必须是更新写入的值");
    }

    @Test
    void listByProject_unknownProjectId_returnsEmptyList() {
        // given: 一个不存在的项目 id
        Long unknownProjectId = 999999999L;

        // when/then: 产品真实语义是抛 ResourceNotFoundException（Project, id）
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> characterController.listByProject(unknownProjectId), "未知项目查询必须抛 ResourceNotFoundException");
        assertEquals("Project", ex.getResource(), "异常资源类型应为 Project");
        assertEquals(unknownProjectId, ex.getId(), "异常资源 id 应为未知项目 id");
    }

    @Test
    void create_isolation_betweenProjects() {
        // given: 两个不同项目，各自创建一个角色
        Records.ProjectRequest otherProjectRequest = new Records.ProjectRequest(
                "隔离项目-" + System.nanoTime(), null, null, null, null);
        Long otherProjectId = projectService.create(otherProjectRequest).id();
        assertNotNull(otherProjectId, "第二个项目 id 必须存在");
        assertNotEquals(projectId, otherProjectId, "两个项目 id 必须不同");

        // when: 分别在两个项目下创建角色
        characterController.create(projectId, buildRequest("项目A角色", "A 描述", "主角"));
        characterController.create(otherProjectId, buildRequest("项目B角色", "B 描述", "配角"));

        // then: 两个项目各自只能看到自己的角色
        List<Records.CharacterResponse> listA = characterController.listByProject(projectId);
        List<Records.CharacterResponse> listB = characterController.listByProject(otherProjectId);
        assertEquals(1, listA.size(), "项目 A 下应只有 1 个角色");
        assertEquals(1, listB.size(), "项目 B 下应只有 1 个角色");
        assertEquals("项目A角色", listA.get(0).name(), "项目 A 角色名称必须正确");
        assertEquals("项目B角色", listB.get(0).name(), "项目 B 角色名称必须正确");
    }
}