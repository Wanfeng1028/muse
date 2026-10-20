package com.dramafactory.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.hamcrest.Matchers.greaterThan;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PromptControllerLegacyApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    /**
     * 无参请求提示词列表应返回 200 且为非空 JSON 数组。
     */
    @Test
    void listWithoutQueryReturnsNonEmptyArray() throws Exception {
        // given
        // when
        mockMvc.perform(get("/api/prompts"))
                // then
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.length()").value(greaterThan(0)));
    }

    /**
     * 按关键字搜索提示词，返回的每一项标题或摘要都应包含该关键字。
     */
    @Test
    void searchKeywordMatchesTitleOrSummary() throws Exception {
        // given
        String keyword = "雨爱";
        // when
        String content = mockMvc.perform(get("/api/prompts").param("q", keyword))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andReturn()
                .getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
        // then
        JsonNode array = objectMapper.readTree(content);
        assertTrue(array.isArray(), "响应应为 JSON 数组");
        assertTrue(array.size() > 0, "搜索结果至少应包含 1 条");
        for (JsonNode item : array) {
            String title = item.path("title").asText("");
            String summary = item.path("summary").asText("");
            assertTrue(title.contains(keyword) || summary.contains(keyword),
                    "title 或 summary 应包含关键字：" + title + " / " + summary);
        }
    }

    /**
     * 搜索不存在的关键字应返回 200 且为空 JSON 数组。
     */
    @Test
    void searchNoMatchReturnsEmptyArray() throws Exception {
        // given
        // when
        mockMvc.perform(get("/api/prompts").param("q", "zzzz-no-such-word"))
                // then
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.length()").value(0));
    }

    /**
     * 查询已知提示词详情应返回 200，标题正确且 content 非空。
     */
    @Test
    void getKnownPromptReturnsDetailWithCorrectTitle() throws Exception {
        // given
        // when
        mockMvc.perform(get("/api/prompts/yuai-deepseek-prompt"))
                // then
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("DeepSeek 做《雨爱》MV 的提示词（部分转录）"))
                .andExpect(jsonPath("$.content").isNotEmpty());
    }

    /**
     * 查询不存在的提示词 id 应返回 404。
     */
    @Test
    void getUnknownPromptReturns404() throws Exception {
        // given
        // when
        mockMvc.perform(get("/api/prompts/no-such-id"))
                // then
                .andExpect(status().isNotFound());
    }

    /**
     * 含双下划线的提示词 id 应被路径变量正确接收并返回对应详情。
     */
    @Test
    void promptIdWithDoubleUnderscoreRoutesCorrectly() throws Exception {
        // given
        // when
        mockMvc.perform(get("/api/prompts/opus-video-prompts__prompts__01-inference-startup-launch"))
                // then
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("推理创业公司发布视频"));
    }
}