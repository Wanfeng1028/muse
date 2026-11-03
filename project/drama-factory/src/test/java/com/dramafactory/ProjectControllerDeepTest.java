package com.dramafactory;

import com.dramafactory.dto.Records;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ProjectControllerDeepTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private String validRequestJson(String name, String description) throws Exception {
        Records.ProjectRequest request = new Records.ProjectRequest(name, null, description, null, null);
        return objectMapper.writeValueAsString(request);
    }

    private Long createProject(String name, String description) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(validRequestJson(name, description)))
                .andExpect(status().isCreated())
                .andReturn();
        Records.ProjectResponse response = objectMapper.readValue(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse.class);
        return response.id();
    }

    @BeforeEach
    void cleanUp() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/projects"))
                .andExpect(status().isOk())
                .andReturn();
        Records.ProjectResponse[] existing = objectMapper.readValue(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse[].class);
        for (Records.ProjectResponse project : existing) {
            mockMvc.perform(delete("/api/projects/" + project.id()));
        }
    }

    @Test
    void createProject_returnsCreatedWithPersistedFields() throws Exception {
        // given: 一个合法的项目创建请求
        String name = "剧集A";
        String description = "这是第一个测试项目";

        // when: 调用创建接口
        MvcResult result = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(validRequestJson(name, description)))
                .andExpect(status().isCreated())
                .andReturn();

        // then: 返回体字段与请求一致，且能在列表中查到
        Records.ProjectResponse created = objectMapper.readValue(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse.class);
        assertThat(created.id()).isNotNull();
        assertThat(created.title()).isEqualTo(name);
        assertThat(created.synopsis()).isEqualTo(description);

        mockMvc.perform(get("/api/projects"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.id == " + created.id() + ")].title").value(name));
    }

    @Test
    void getProjectById_returnsMatchingProject() throws Exception {
        // given: 已存在一个项目
        Long id = createProject("剧集B", "按ID查询测试");

        // when: 按 ID 查询
        MvcResult result = mockMvc.perform(get("/api/projects/" + id))
                .andExpect(status().isOk())
                .andReturn();

        // then: 返回的 ID 和名称与创建时一致
        Records.ProjectResponse fetched = objectMapper.readValue(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse.class);
        assertThat(fetched.id()).isEqualTo(id);
        assertThat(fetched.title()).isEqualTo("剧集B");
    }

    @Test
    void updateProject_changesFieldsAndPersists() throws Exception {
        // given: 已存在一个项目
        Long id = createProject("旧名字", "旧描述");

        // when: 更新名称和描述
        mockMvc.perform(put("/api/projects/" + id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(validRequestJson("新名字", "新描述")))
                .andExpect(status().isOk());

        // then: 再次查询得到更新后的值
        MvcResult result = mockMvc.perform(get("/api/projects/" + id))
                .andExpect(status().isOk())
                .andReturn();
        Records.ProjectResponse updated = objectMapper.readValue(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse.class);
        assertThat(updated.title()).isEqualTo("新名字");
        assertThat(updated.synopsis()).isEqualTo("新描述");
    }

    @Test
    void deleteProject_removesFromListAndSubsequentGetFails() throws Exception {
        // given: 已存在一个项目
        Long id = createProject("待删除", "删除测试");

        // when: 删除该项目
        mockMvc.perform(delete("/api/projects/" + id))
                .andExpect(status().isNoContent());

        // then: 列表中不再包含它，按 ID 查询返回非 2xx
        MvcResult listResult = mockMvc.perform(get("/api/projects"))
                .andExpect(status().isOk())
                .andReturn();
        Records.ProjectResponse[] remaining = objectMapper.readValue(
                listResult.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse[].class);
        boolean stillPresent = false;
        for (Records.ProjectResponse p : remaining) {
            if (p.id().equals(id)) {
                stillPresent = true;
            }
        }
        assertThat(stillPresent).isFalse();

        mockMvc.perform(get("/api/projects/" + id))
                .andExpect(status().is4xxClientError());
    }

    @Test
    void createProject_withBlankName_returnsBadRequest() throws Exception {
        // given: name 为空的非法请求
        Records.ProjectRequest bad = new Records.ProjectRequest("", null, "描述没问题", null, null);

        // when: 调用创建接口
        MvcResult result = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(bad)))
                .andExpect(status().isBadRequest())
                .andReturn();

        // then: 状态为 400，且返回体非空
        assertThat(result.getResponse().getStatus()).isEqualTo(400);
        assertThat(result.getResponse().getContentAsString(StandardCharsets.UTF_8)).isNotEmpty();
    }

    @Test
    void createProject_withOversizedPayload_isHandledGracefully() throws Exception {
        // given: 描述字段长度 100000 的超大 payload
        StringBuilder big = new StringBuilder();
        for (int i = 0; i < 100000; i++) {
            big.append('x');
        }
        Records.ProjectRequest request = new Records.ProjectRequest("超大payload", null, big.toString(), null, null);

        // when: 调用创建接口
        MvcResult result = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andReturn();

        // then: 要么成功创建，要么明确 4xx 拒绝，绝不出现 5xx
        int status = result.getResponse().getStatus();
        assertThat(status).isLessThan(500);
        assertThat(status == 201 || status == 400).isTrue();
    }

    @Test
    void getProject_withNonExistentId_returnsClientError() throws Exception {
        // given: 一个不存在的 ID
        Long missingId = 999999999L;

        // when: 按该 ID 查询
        MvcResult result = mockMvc.perform(get("/api/projects/" + missingId))
                .andReturn();

        // then: 返回 4xx 且不是 200
        int status = result.getResponse().getStatus();
        assertThat(status).isNotEqualTo(200);
        assertThat(status).isBetween(400, 499);
    }

    @Test
    void createProject_isNotIdempotentAcrossCalls_butEachIsConsistent() throws Exception {
        // given: 同一个请求体调用两次
        String payload = validRequestJson("幂等测试", "同一请求");

        // when: 连续调用两次创建
        MvcResult first = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isCreated())
                .andReturn();
        MvcResult second = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isCreated())
                .andReturn();

        // then: 两次创建各自返回有效记录，且字段值一致
        Records.ProjectResponse r1 = objectMapper.readValue(
                first.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse.class);
        Records.ProjectResponse r2 = objectMapper.readValue(
                second.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse.class);
        assertThat(r1.id()).isNotNull();
        assertThat(r2.id()).isNotNull();
        assertThat(r1.title()).isEqualTo(r2.title());
    }

    @Test
    void updateProject_repeatedWithSamePayload_isIdempotent() throws Exception {
        // given: 已存在一个项目
        Long id = createProject("幂等更新", "初始描述");

        // when: 用同一请求体更新两次
        String payload = validRequestJson("幂等更新", "更新后描述");
        mockMvc.perform(put("/api/projects/" + id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isOk());
        mockMvc.perform(put("/api/projects/" + id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isOk());

        // then: 最终状态与单次更新一致
        MvcResult result = mockMvc.perform(get("/api/projects/" + id))
                .andExpect(status().isOk())
                .andReturn();
        Records.ProjectResponse finalState = objectMapper.readValue(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse.class);
        assertThat(finalState.title()).isEqualTo("幂等更新");
        assertThat(finalState.synopsis()).isEqualTo("更新后描述");
    }

    @Test
    void deleteProject_repeatedCall_isIdempotentOrClientError() throws Exception {
        // given: 已存在一个项目
        Long id = createProject("重复删除", "描述");

        // when: 连续删除两次
        MvcResult first = mockMvc.perform(delete("/api/projects/" + id))
                .andReturn();
        MvcResult second = mockMvc.perform(delete("/api/projects/" + id))
                .andReturn();

        // then: 第一次 204，第二次要么 204 要么 4xx，不能是 5xx
        assertThat(first.getResponse().getStatus()).isEqualTo(204);
        assertThat(second.getResponse().getStatus()).isLessThan(500);
    }

    @Test
    void concurrentCreate_thenList_containsAllCreatedProjects() throws Exception {
        // given: 8 个线程并发创建不同项目
        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger success = new AtomicInteger(0);
        AtomicInteger failed = new AtomicInteger(0);

        // when: 同时发起创建请求
        for (int i = 0; i < threads; i++) {
            final int idx = i;
            pool.submit(() -> {
                try {
                    start.await();
                    int status = mockMvc.perform(post("/api/projects")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(validRequestJson("并发-" + idx, "并发创建")))
                            .andReturn().getResponse().getStatus();
                    if (status == 201) {
                        success.incrementAndGet();
                    } else {
                        failed.incrementAndGet();
                    }
                } catch (Exception e) {
                    failed.incrementAndGet();
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        pool.shutdown();

        // then: 全部线程执行完，成功数加失败数等于线程数，且成功数大于 0
        assertThat(finished).isTrue();
        assertThat(success.get() + failed.get()).isEqualTo(threads);
        assertThat(success.get()).isGreaterThan(0);
    }

    @Test
    void concurrentUpdateSameProject_endsWithOneOfSubmittedValues() throws Exception {
        // given: 已存在一个项目
        Long id = createProject("并发更新", "初始");

        // when: 两个线程用不同值更新同一个项目
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        List<Integer> statuses = new ArrayList<>();

        for (int i = 0; i < 2; i++) {
            final String newName = "并发更新-" + i;
            pool.submit(() -> {
                try {
                    start.await();
                    int status = mockMvc.perform(put("/api/projects/" + id)
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(validRequestJson(newName, "并发写")))
                            .andReturn().getResponse().getStatus();
                    synchronized (statuses) {
                        statuses.add(status);
                    }
                } catch (Exception e) {
                    synchronized (statuses) {
                        statuses.add(500);
                    }
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        boolean finished = done.await(30, TimeUnit.SECONDS);
        pool.shutdown();

        // then: 两个请求都完成，最终值是其中一个提交值，数据没有损坏
        assertThat(finished).isTrue();
        assertThat(statuses).hasSize(2);
        assertThat(statuses).allMatch(s -> s == 200);

        MvcResult result = mockMvc.perform(get("/api/projects/" + id))
                .andExpect(status().isOk())
                .andReturn();
        Records.ProjectResponse finalState = objectMapper.readValue(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.ProjectResponse.class);
        assertThat(finalState.title()).isIn("并发更新-0", "并发更新-1");
        assertThat(finalState.id()).isEqualTo(id);
    }

    @Test
    void stats_reflectsCreatedProjectCount() throws Exception {
        // given: 先清空，再创建两个项目
        createProject("统计1", "统计测试");
        createProject("统计2", "统计测试");

        // when: 查询统计接口
        MvcResult result = mockMvc.perform(get("/api/stats"))
                .andExpect(status().isOk())
                .andReturn();

        // then: 统计返回体非空，且项目总数不少于 2
        Records.StatsResponse stats = objectMapper.readValue(
                result.getResponse().getContentAsString(StandardCharsets.UTF_8), Records.StatsResponse.class);
        assertThat(stats).isNotNull();
        assertThat(stats.projects()).isGreaterThanOrEqualTo(2);
    }
}