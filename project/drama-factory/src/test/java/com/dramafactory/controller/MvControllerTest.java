package com.dramafactory.controller;

import com.dramafactory.service.MvLyricsService;
import com.dramafactory.service.MvService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * MvController MockMvc 测试。
 */
@SpringBootTest
@AutoConfigureMockMvc
class MvControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private MvService mvService;

    @MockBean
    private MvLyricsService mvLyricsService;

    private MvLyricsService.LyricsResult fixedLyrics() {
        return new MvLyricsService.LyricsResult(
                List.of(new MvLyricsService.LyricSection("verse1", "测试歌词", "欢快", 10)),
                "测试歌", 0, 0);
    }

    @Test
    void createBlankThemeReturns400() throws Exception {
        mockMvc.perform(post("/api/mv")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"theme\":\"\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createAndGetReturns200() throws Exception {
        String body = mockMvc.perform(post("/api/mv")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"theme\":\"测试主题\",\"mood\":\"欢快\",\"style\":\"流行\"}"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        JsonNode root = objectMapper.readTree(body);
        long id = root.path("id").asLong();
        assert id > 0;

        mockMvc.perform(get("/api/mv/" + id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.theme").value("测试主题"));
    }

    @Test
    void lyricsEndpointReturns200() throws Exception {
        when(mvLyricsService.generate(anyString(), any(), any())).thenReturn(fixedLyrics());
        when(mvLyricsService.toJson(any())).thenReturn("{\"title\":\"测试歌\",\"sections\":[{\"name\":\"verse1\",\"lyrics\":\"测试歌词\",\"mood\":\"欢快\",\"estSeconds\":10}]}");

        Long songId = mvService.create("接口作词", null, null);

        mockMvc.perform(post("/api/mv/" + songId + "/lyrics"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"));
    }

    @Test
    void videoNotFoundReturns404() throws Exception {
        Long songId = mvService.create("无成片", null, null);

        mockMvc.perform(get("/api/mv/" + songId + "/video"))
                .andExpect(status().isNotFound());
    }

    @Test
    void lyricsNotFoundReturns404() throws Exception {
        mockMvc.perform(post("/api/mv/999999/lyrics"))
                .andExpect(status().isNotFound());
    }
}
