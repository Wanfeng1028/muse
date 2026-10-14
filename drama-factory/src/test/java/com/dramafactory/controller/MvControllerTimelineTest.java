package com.dramafactory.controller;

import com.dramafactory.model.MvSong;
import com.dramafactory.service.MvService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvControllerTimelineTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private MvService mvService;

    @Test
    void composeReturnsDurationAndAudioUrl() throws Exception {
        MvSong song = new MvSong();
        song.setStatus("SUCCEEDED");
        song.setAudioUrl("http://audio/1.mp3");
        song.setDurationMs(12345);
        when(mvService.compose(anyLong(), any(), any())).thenReturn(song);

        mockMvc.perform(post("/api/mv/1/compose")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"providerId\":1,\"modelId\":\"m\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.durationMs").value(12345))
                .andExpect(jsonPath("$.audioUrl").value("http://audio/1.mp3"));
    }

    @Test
    void storyboardReturnsItemsArray() throws Exception {
        List<Map<String, String>> items = new ArrayList<>();
        Map<String, String> item = new HashMap<>();
        item.put("text", "hello");
        items.add(item);

        when(mvService.storyboard(anyLong())).thenReturn(items);

        mockMvc.perform(post("/api/mv/1/storyboard")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").isArray());
    }

    @Test
    void getReturnsTimelineJson() throws Exception {
        MvSong song = new MvSong();
        song.setTheme("t");
        song.setStatus("SUCCEEDED");
        song.setAudioUrl("http://audio/1.mp3");
        song.setDurationMs(1000);
        song.setTimelineJson("{\"totalMs\":1000}");
        song.setRunId(7L);
        when(mvService.getById(anyLong())).thenReturn(song);

        mockMvc.perform(get("/api/mv/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.timelineJson").exists());
    }

    @Test
    void composeWithoutLyricsReturnsBadRequest() throws Exception {
        when(mvService.compose(anyLong(), any(), any()))
                .thenThrow(new IllegalStateException("请先生成歌词"));

        mockMvc.perform(post("/api/mv/1/compose")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"providerId\":1,\"modelId\":\"m\"}"))
                .andExpect(status().isBadRequest());
    }
}
