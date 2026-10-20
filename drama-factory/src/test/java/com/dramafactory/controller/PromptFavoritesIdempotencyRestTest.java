package com.dramafactory.controller;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PromptFavoritesIdempotencyRestTest {

    private static final String TARGET = "yuai-deepseek-prompt";
    private static final String UNKNOWN = "no-such-id-zzz";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private long countInFavorites(String id) throws Exception {
        MvcResult result = mockMvc.perform(get("/api/prompts/favorites"))
                .andExpect(status().isOk())
                .andReturn();
        List<Map<String, Object>> favorites = objectMapper.readValue(
                result.getResponse().getContentAsString(), new TypeReference<List<Map<String, Object>>>() {});
        return favorites.stream().filter(item -> id.equals(item.get("id"))).count();
    }

    /**
     * 重复收藏同一提示词应幂等：每次都返回 200，收藏列表中只保留一条记录。
     */
    @Test
    void favoriteRepeatedKeepsSingleEntry() throws Exception {
        try {
            mockMvc.perform(delete("/api/prompts/" + TARGET + "/favorite")).andExpect(status().isOk());
            for (int i = 0; i < 3; i++) {
                mockMvc.perform(post("/api/prompts/" + TARGET + "/favorite"))
                        .andExpect(status().isOk());
            }
            Assertions.assertEquals(1, countInFavorites(TARGET), "重复收藏 3 次后收藏列表应只保留一条记录");
        } finally {
            mockMvc.perform(delete("/api/prompts/" + TARGET + "/favorite"));
        }
    }

    /**
     * 重复取消收藏应幂等：每次都返回 200，收藏列表中不再包含该记录。
     */
    @Test
    void unfavoriteRepeatedStaysIdempotent() throws Exception {
        try {
            mockMvc.perform(post("/api/prompts/" + TARGET + "/favorite")).andExpect(status().isOk());
            mockMvc.perform(delete("/api/prompts/" + TARGET + "/favorite")).andExpect(status().isOk());
            mockMvc.perform(delete("/api/prompts/" + TARGET + "/favorite")).andExpect(status().isOk());
            Assertions.assertEquals(0, countInFavorites(TARGET), "重复取消收藏后收藏列表应不再包含该记录");
        } finally {
            mockMvc.perform(delete("/api/prompts/" + TARGET + "/favorite"));
        }
    }

    /**
     * 20 路并发收藏同一提示词应全部返回 200，且收藏列表中只保留一条记录。
     */
    @Test
    void favoriteConcurrentKeepsSingleEntry() throws Exception {
        int threads = 20;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger okCount = new AtomicInteger();
        try {
            mockMvc.perform(delete("/api/prompts/" + TARGET + "/favorite")).andExpect(status().isOk());
            for (int i = 0; i < threads; i++) {
                pool.submit(() -> {
                    ready.countDown();
                    try {
                        start.await(10, TimeUnit.SECONDS);
                        int code = mockMvc.perform(post("/api/prompts/" + TARGET + "/favorite"))
                                .andReturn().getResponse().getStatus();
                        if (code == 200) {
                            okCount.incrementAndGet();
                        }
                    } catch (Exception e) {
                        throw new RuntimeException(e);
                    }
                    return null;
                });
            }
            Assertions.assertTrue(ready.await(10, TimeUnit.SECONDS), "线程未能就绪");
            start.countDown();
            pool.shutdown();
            Assertions.assertTrue(pool.awaitTermination(30, TimeUnit.SECONDS), "并发收藏未在 30 秒内完成");
            Assertions.assertEquals(threads, okCount.get(), "20 路并发收藏应全部返回 200");
            Assertions.assertEquals(1, countInFavorites(TARGET), "并发收藏后收藏列表应只保留一条记录");
        } finally {
            pool.shutdownNow();
            mockMvc.perform(delete("/api/prompts/" + TARGET + "/favorite"));
        }
    }

    /**
     * 收藏不存在的提示词应返回 404。
     */
    @Test
    void favoriteUnknownIdReturns404() throws Exception {
        mockMvc.perform(post("/api/prompts/" + UNKNOWN + "/favorite"))
                .andExpect(status().isNotFound());
    }

    /**
     * 取消收藏不存在的提示词应返回 404。
     */
    @Test
    void unfavoriteUnknownIdReturns404() throws Exception {
        mockMvc.perform(delete("/api/prompts/" + UNKNOWN + "/favorite"))
                .andExpect(status().isNotFound());
    }
}
