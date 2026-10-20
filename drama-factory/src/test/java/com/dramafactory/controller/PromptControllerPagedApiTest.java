package com.dramafactory.controller;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;
import java.nio.charset.StandardCharsets;

import static org.hamcrest.Matchers.greaterThan;
import static org.hamcrest.Matchers.greaterThanOrEqualTo;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PromptControllerPagedApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    /**
     * 默认分页查询应返回完整分页字段且内容非空。
     */
    @Test
    void pageDefaultReturnsAllPagingFields() throws Exception {
        // given: 无查询参数
        // when: 请求默认分页接口
        mockMvc.perform(get("/api/prompts/page"))
                // then: 返回 200，包含五个分页字段，content 非空，totalElements 大于 0，totalPages 大于等于 1
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").isArray())
                .andExpect(jsonPath("$.content").isNotEmpty())
                .andExpect(jsonPath("$.page").exists())
                .andExpect(jsonPath("$.size").exists())
                .andExpect(jsonPath("$.totalElements").exists())
                .andExpect(jsonPath("$.totalPages").exists())
                .andExpect(jsonPath("$.totalElements").value(greaterThan(0)))
                .andExpect(jsonPath("$.totalPages").value(greaterThanOrEqualTo(1)));
    }

    /**
     * 越界页码应返回空内容但总数仍为正。
     */
    @Test
    void pageOutOfRangeReturnsEmptyContentButPositiveTotal() throws Exception {
        // given: 页码越界
        // when: 请求分页接口
        mockMvc.perform(get("/api/prompts/page").param("page", "9999").param("size", "20"))
                // then: 返回 200，content 为空数组，totalElements 大于 0
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").isArray())
                .andExpect(jsonPath("$.content").isEmpty())
                .andExpect(jsonPath("$.totalElements").value(greaterThan(0)));
    }

    /**
     * 非法分页参数应被规范化为合法值。
     */
    @Test
    void pageNegativeAndSizeZeroNormalized() throws Exception {
        // given: 非法分页参数
        // when: 请求分页接口
        mockMvc.perform(get("/api/prompts/page").param("page", "-1").param("size", "0"))
                // then: 返回 200，page 大于等于 0，size 大于等于 1，content 为数组
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(greaterThanOrEqualTo(0)))
                .andExpect(jsonPath("$.size").value(greaterThanOrEqualTo(1)))
                .andExpect(jsonPath("$.content").isArray());
    }

    /**
     * 标签接口应返回数组且包含根目录。
     */
    @Test
    void tagsReturnsArrayContainingRoot() throws Exception {
        // given: 无
        // when: 请求标签接口
        MvcResult result = mockMvc.perform(get("/api/prompts/tags"))
                // then: 返回 200 且为 JSON 数组
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andReturn();
        List<String> tags = objectMapper.readValue(new String(result.getResponse().getContentAsByteArray(), StandardCharsets.UTF_8), new TypeReference<List<String>>() {});
        Assertions.assertTrue(tags.contains("根目录"), "标签列表应包含根目录");
    }

    /**
     * 重复收藏应幂等返回 200。
     */
    @Test
    void favoriteTwiceIsIdempotent() throws Exception {
        // given: 目标提示词存在
        // when: 连续两次收藏
        try {
            mockMvc.perform(post("/api/prompts/yuai-deepseek-prompt/favorite"))
                    // then: 第一次返回 200
                    .andExpect(status().isOk());
            mockMvc.perform(post("/api/prompts/yuai-deepseek-prompt/favorite"))
                    // then: 第二次仍返回 200
                    .andExpect(status().isOk());
        } finally {
            // 清理收藏状态
            mockMvc.perform(delete("/api/prompts/yuai-deepseek-prompt/favorite"));
        }
    }

    /**
     * 收藏未知 id 应返回 404。
     */
    @Test
    void favoriteUnknownIdReturns404() throws Exception {
        // given: 不存在的 id
        // when: 请求收藏接口
        mockMvc.perform(post("/api/prompts/no-such-id/favorite"))
                // then: 返回 404
                .andExpect(status().isNotFound());
    }

    /**
     * 未收藏时取消收藏应幂等返回 200。
     */
    @Test
    void unfavoriteNotFavoritedReturns200() throws Exception {
        // given: 先执行一次取消收藏确保未收藏状态
        mockMvc.perform(delete("/api/prompts/yuai-deepseek-prompt/favorite"));
        // when: 再次取消收藏
        mockMvc.perform(delete("/api/prompts/yuai-deepseek-prompt/favorite"))
                // then: 返回 200
                .andExpect(status().isOk());
    }

    /**
     * 收藏后收藏列表应包含对应项。
     */
    @Test
    void favoritesContainsAfterFavorite() throws Exception {
        // given: 目标提示词存在
        // when: 收藏后查询收藏列表
        try {
            mockMvc.perform(post("/api/prompts/yuai-deepseek-prompt/favorite"))
                    // then: 收藏成功返回 200
                    .andExpect(status().isOk());
            MvcResult result = mockMvc.perform(get("/api/prompts/favorites"))
                    // then: 返回 200 且为数组
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$").isArray())
                    .andReturn();
            List<Map<String, Object>> favorites = objectMapper.readValue(result.getResponse().getContentAsString(), new TypeReference<List<Map<String, Object>>>() {});
            boolean found = favorites.stream().anyMatch(item -> "yuai-deepseek-prompt".equals(item.get("id")));
            Assertions.assertTrue(found, "收藏列表应包含 yuai-deepseek-prompt");
        } finally {
            // 清理收藏状态
            mockMvc.perform(delete("/api/prompts/yuai-deepseek-prompt/favorite"));
        }
    }

    /**
     * 标签精确路径不应被 id 模板路由吞掉。
     */
    @Test
    void tagsNotSwallowedByIdRoute() throws Exception {
        // given: 无
        // when: 请求标签接口
        mockMvc.perform(get("/api/prompts/tags"))
                // then: 返回 200 而非 404
                .andExpect(status().isOk());
    }
}