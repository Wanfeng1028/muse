package com.dramafactory.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 视频任务提交接口限流的集成测试。
 *
 * <p>通过 properties 覆盖 {@code videoSubmit} 限流器为「每 10 秒最多 2 次」，
 * 然后对同一分镜连续发起 3 次提交请求，验证第 3 次返回 429 且带 Retry-After 头。</p>
 */
@SpringBootTest(properties = {
        "resilience4j.ratelimiter.instances.videoSubmit.limit-for-period=2",
        "resilience4j.ratelimiter.instances.videoSubmit.limit-refresh-period=10s",
        "resilience4j.ratelimiter.instances.videoSubmit.timeout-duration=0s"
})
@AutoConfigureMockMvc
class VideoTaskControllerRateLimitTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private Long shotId;

    /**
     * 准备数据：项目 → 剧集 → 分镜，并解析出 shotId。
     */
    @BeforeEach
    void setUp() throws Exception {
        // 1. 创建项目
        MvcResult projectResult = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"限流测试\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        Long projectId = readId(projectResult);

        // 2. 创建剧集
        MvcResult episodeResult = mockMvc.perform(post("/api/projects/" + projectId + "/episodes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"episodeNo\":1}"))
                .andExpect(status().isCreated())
                .andReturn();
        Long episodeId = readId(episodeResult);

        // 3. 创建分镜
        MvcResult shotResult = mockMvc.perform(post("/api/episodes/" + episodeId + "/shots")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"shotNo\":1}"))
                .andExpect(status().isCreated())
                .andReturn();
        this.shotId = readId(shotResult);
    }

    /**
     * 连续 3 次提交：前 2 次成功（201/200），第 3 次被限流返回 429 且带 Retry-After。
     */
    @Test
    void shouldRateLimitAfterQuotaExhausted() throws Exception {
        String url = "/api/shots/" + shotId + "/video-tasks";

        // 第 1 次：创建成功
        mockMvc.perform(post(url))
                .andExpect(status().isCreated());

        // 第 2 次：幂等命中，返回 200
        mockMvc.perform(post(url))
                .andExpect(status().isOk());

        // 第 3 次：超出配额，返回 429，并带 Retry-After 头
        mockMvc.perform(post(url))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().exists("Retry-After"));
    }

    /**
     * 从 MockMvc 返回的 JSON 中读取 id 字段。
     */
    private Long readId(MvcResult result) throws Exception {
        JsonNode node = objectMapper.readTree(result.getResponse().getContentAsString());
        return node.get("id").asLong();
    }
}
