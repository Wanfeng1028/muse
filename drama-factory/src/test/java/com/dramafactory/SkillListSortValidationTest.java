package com.dramafactory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class SkillListSortValidationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void bogusSortReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/api/skills").param("sort", "bogus"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void uppercasePopularSortReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/api/skills").param("sort", "POPULAR"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void emptySortReturnsOk() throws Exception {
        mockMvc.perform(get("/api/skills").param("sort", ""))
                .andExpect(status().isOk());
    }

    @Test
    void missingSortReturnsOk() throws Exception {
        mockMvc.perform(get("/api/skills"))
                .andExpect(status().isOk());
    }

    @Test
    void popularSortReturnsOk() throws Exception {
        mockMvc.perform(get("/api/skills").param("sort", "popular"))
                .andExpect(status().isOk());
    }

    @Test
    void ratingSortReturnsOk() throws Exception {
        mockMvc.perform(get("/api/skills").param("sort", "rating"))
                .andExpect(status().isOk());
    }

    @Test
    void newestSortReturnsOk() throws Exception {
        mockMvc.perform(get("/api/skills").param("sort", "newest"))
                .andExpect(status().isOk());
    }

    @Test
    void nameSortReturnsOk() throws Exception {
        mockMvc.perform(get("/api/skills").param("sort", "name"))
                .andExpect(status().isOk());
    }
}