package com.dramafactory.playbook;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/**
 * 风格手册控制器测试。
 */
@SpringBootTest
@AutoConfigureMockMvc
class StylePlaybookControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void listPlaybooks() throws Exception {
        mockMvc.perform(get("/api/style-playbooks"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(5));
    }

    @Test
    void getPlaybookByName() throws Exception {
        mockMvc.perform(get("/api/style-playbooks/anime-ghibli"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Anime Ghibli"))
                .andExpect(jsonPath("$.palette.background").value("#0A0A1A"));
    }

    @Test
    void getPlaybookNotFound() throws Exception {
        mockMvc.perform(get("/api/style-playbooks/nope"))
                .andExpect(status().isNotFound());
    }
}
