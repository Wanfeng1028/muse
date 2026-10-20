package com.dramafactory.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PromptLibraryPagingEdgeRestTest {

    private static final String NO_MATCH_QUERY = "zzz-no-such-keyword-zzz";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private JsonNode getPage(String queryString) throws Exception {
        MvcResult result = mockMvc.perform(get("/api/prompts/page" + queryString))
                .andExpect(status().isOk())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString());
    }

    /**
     * 空结果集的第一页应返回 200，totalElements/totalPages 均为 0，content 为空数组。
     */
    @Test
    void emptyResultFirstPage() throws Exception {
        // given: 无任何记录匹配的关键词
        // when: 请求第一页
        JsonNode page = getPage("?q=" + NO_MATCH_QUERY + "&page=0&size=20");
        // then: 200，计数为 0，内容为空
        Assertions.assertEquals(0, page.get("totalElements").asLong());
        Assertions.assertEquals(0, page.get("totalPages").asInt());
        Assertions.assertTrue(page.get("content").isArray() && page.get("content").isEmpty());
    }

    /**
     * 空结果集的越界页不应报错，同样返回空内容。
     */
    @Test
    void emptyResultSecondPage() throws Exception {
        // given: 无任何记录匹配的关键词
        // when: 请求第二页
        JsonNode page = getPage("?q=" + NO_MATCH_QUERY + "&page=1&size=20");
        // then: 200，内容为空，totalElements 仍为 0
        Assertions.assertEquals(0, page.get("totalElements").asLong());
        Assertions.assertTrue(page.get("content").isEmpty());
    }

    /**
     * 最后一页为 partial 时应只返回剩余的 1 条记录。
     */
    @Test
    void lastPagePartialContent() throws Exception {
        // given: 先查出总数
        JsonNode first = getPage("");
        long total = first.get("totalElements").asLong();
        Assertions.assertTrue(total >= 2, "需要至少 2 条真实数据才能构造 partial 尾页");
        // when: 每页 total-1 条，请求第 2 页
        JsonNode page = getPage("?page=1&size=" + (total - 1));
        // then: 200，只剩 1 条，页码回显 1
        Assertions.assertEquals(1, page.get("content").size());
        Assertions.assertEquals(1, page.get("page").asInt());
        Assertions.assertEquals(total, page.get("totalElements").asLong());
    }

    /**
     * size=1 时每页只有 1 条，totalPages 应等于 totalElements。
     */
    @Test
    void firstPageSizeOne() throws Exception {
        // given: size 取最小合法值 1
        // when: 请求第一页
        JsonNode page = getPage("?page=0&size=1");
        // then: 200，content 长度为 1，totalPages 等于 totalElements
        Assertions.assertEquals(1, page.get("content").size());
        Assertions.assertEquals(page.get("totalElements").asLong(), page.get("totalPages").asLong());
    }

    /**
     * 未知的 tag 应返回空内容而非报错。
     */
    @Test
    void unknownTagReturnsEmpty() throws Exception {
        // given: 不存在的来源分类
        // when: 按该 tag 分页查询
        JsonNode page = getPage("?tag=no-such-tag-zzz");
        // then: 200，内容为空
        Assertions.assertEquals(0, page.get("totalElements").asLong());
        Assertions.assertTrue(page.get("content").isEmpty());
    }

    /**
     * q 传空字符串应与不传 q 行为一致。
     */
    @Test
    void emptyQueryBehavesLikeNoQuery() throws Exception {
        // given: 空字符串查询与无查询参数
        // when: 分别请求
        JsonNode withEmpty = getPage("?q=");
        JsonNode without = getPage("");
        // then: totalElements 相等
        Assertions.assertEquals(without.get("totalElements").asLong(), withEmpty.get("totalElements").asLong());
    }

    /**
     * q 传全空格应被 trim 后视为空查询，不报错且总数大于 0。
     */
    @Test
    void blankQueryIsTreatedAsEmpty() throws Exception {
        // given: 全空格关键词
        // when: 请求分页接口
        MvcResult result = mockMvc.perform(get("/api/prompts/page").param("q", "   "))
                .andExpect(status().isOk())
                .andReturn();
        JsonNode page = objectMapper.readTree(result.getResponse().getContentAsString());
        // then: 200，总数大于 0
        Assertions.assertTrue(page.get("totalElements").asLong() > 0);
    }

    /**
     * 超长关键词不应抛异常，返回空内容。
     */
    @Test
    void veryLongQueryReturnsEmpty() throws Exception {
        // given: 500 个 z 组成的关键词
        // when: 请求分页接口
        JsonNode page = getPage("?q=" + "z".repeat(500));
        // then: 200，内容为空
        Assertions.assertTrue(page.get("content").isEmpty());
    }

    /**
     * 中英混合关键词不应报错。
     */
    @Test
    void mixedLanguageQuery() throws Exception {
        // given: 中英混合关键词
        // when: 请求分页接口
        mockMvc.perform(get("/api/prompts/page").param("q", "deepseek 提示词"))
                // then: 200，content 为数组
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").isArray());
    }

    /**
     * 非数字 page 应返回 400（Spring 类型转换失败）。
     */
    @Test
    void nonNumericPageReturns400() throws Exception {
        // given: page 传非数字
        // when: 请求分页接口
        mockMvc.perform(get("/api/prompts/page").param("page", "abc"))
                // then: 400
                .andExpect(status().isBadRequest());
    }

    /**
     * 非数字 size 应返回 400（Spring 类型转换失败）。
     */
    @Test
    void nonNumericSizeReturns400() throws Exception {
        // given: size 传非数字
        // when: 请求分页接口
        mockMvc.perform(get("/api/prompts/page").param("size", "abc"))
                // then: 400
                .andExpect(status().isBadRequest());
    }
}
