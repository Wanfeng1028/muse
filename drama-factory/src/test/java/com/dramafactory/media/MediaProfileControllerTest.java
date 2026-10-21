package com.dramafactory.media;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 媒体预设控制器的集成测试。
 */
@SpringBootTest
@AutoConfigureMockMvc
class MediaProfileControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void list_returnsAllProfiles() throws Exception {
        mockMvc.perform(get("/api/media-profiles"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(9));
    }

    @Test
    void list_withPlatform_returnsFiltered() throws Exception {
        mockMvc.perform(get("/api/media-profiles").param("platform", "instagram"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2));
    }

    @Test
    void get_tiktok_returnsProfile() throws Exception {
        mockMvc.perform(get("/api/media-profiles/tiktok"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.width").value(1080))
                .andExpect(jsonPath("$.height").value(1920));
    }

    @Test
    void get_unknown_returns404() throws Exception {
        mockMvc.perform(get("/api/media-profiles/nope"))
                .andExpect(status().isNotFound());
    }
}
