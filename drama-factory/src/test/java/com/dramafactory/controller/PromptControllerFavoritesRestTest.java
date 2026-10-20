package com.dramafactory.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PromptControllerFavoritesRestTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void favoritesDtoShape() throws Exception {
        mockMvc.perform(delete("/api/prompts/yuai-deepseek-prompt/favorite"))
                .andExpect(status().isOk());

        mockMvc.perform(post("/api/prompts/yuai-deepseek-prompt/favorite"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/prompts/favorites"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").exists())
                .andExpect(jsonPath("$[0].title").exists())
                .andExpect(jsonPath("$[0].source").exists())
                .andExpect(jsonPath("$[0].path").exists())
                .andExpect(jsonPath("$[0].summary").exists());

        mockMvc.perform(delete("/api/prompts/yuai-deepseek-prompt/favorite"))
                .andExpect(status().isOk());
    }

    @Test
    void favoriteUnknownId_Detail404Consistency() throws Exception {
        mockMvc.perform(delete("/api/prompts/yuai-deepseek-prompt/favorite"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/prompts/no-such-id-zzz"))
                .andExpect(status().isNotFound());

        mockMvc.perform(post("/api/prompts/no-such-id-zzz/favorite"))
                .andExpect(status().isNotFound());
    }
}