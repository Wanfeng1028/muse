package com.dramafactory;

import com.dramafactory.controller.VideoTaskController;
import com.dramafactory.dto.Records;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.service.VideoTaskService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.LocalDateTime;
import java.util.List;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class VideoTaskControllerDeepTestR4 {

    private MockMvc buildMockMvc(VideoTaskService videoTaskService) {
        return MockMvcBuilders.standaloneSetup(new VideoTaskController(videoTaskService)).build();
    }

    private Records.VideoTaskResponse task(Long id, Long shotId) {
        return new Records.VideoTaskResponse(
                id,
                shotId,
                "mock",
                "provider-task-1",
                VideoTaskStatus.PENDING,
                "等待中",
                2,
                null,
                Boolean.FALSE,
                null,
                null,
                LocalDateTime.of(2024, 1, 1, 0, 0),
                LocalDateTime.of(2024, 1, 1, 0, 0),
                null
        );
    }

    @Test
    void submitForShot_createdTrue_returns201() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        Records.VideoTaskResponse response = task(100L, 7L);
        when(service.submit(7L)).thenReturn(new Records.SubmitOutcome(response, true));
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(post("/api/shots/7/video-tasks").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(100));
    }

    @Test
    void submitForShot_createdFalse_returns200() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        Records.VideoTaskResponse response = task(100L, 7L);
        when(service.submit(7L)).thenReturn(new Records.SubmitOutcome(response, false));
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(post("/api/shots/7/video-tasks").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(100));
    }

    @Test
    void submitForShot_verifyCalledOnce() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        Records.VideoTaskResponse response = task(100L, 7L);
        when(service.submit(7L)).thenReturn(new Records.SubmitOutcome(response, true));
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(post("/api/shots/7/video-tasks").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated());

        verify(service, times(1)).submit(7L);
    }

    @Test
    void submitAllForEpisode_returns200List() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        List<Records.VideoTaskResponse> responses = List.of(task(1L, 7L), task(2L, 8L));
        when(service.submitAllForEpisode(3L)).thenReturn(responses);
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(post("/api/episodes/3/video-tasks/submit-all").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].id").value(1))
                .andExpect(jsonPath("$[1].id").value(2));
    }

    @Test
    void submitAllForEpisode_empty_returnsEmptyArray() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        when(service.submitAllForEpisode(3L)).thenReturn(List.of());
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(post("/api/episodes/3/video-tasks/submit-all").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void listByShot_returns200() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        when(service.listByShot(7L)).thenReturn(List.of(task(1L, 7L)));
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(get("/api/shots/7/video-tasks"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].shotId").value(7));
    }

    @Test
    void listByShot_empty_returnsEmptyArray() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        when(service.listByShot(7L)).thenReturn(List.of());
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(get("/api/shots/7/video-tasks"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void get_returns200() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        when(service.get(9L)).thenReturn(task(9L, 7L));
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(get("/api/video-tasks/9"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(9));
    }

    @Test
    void retry_returns200() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        when(service.retry(9L)).thenReturn(task(9L, 7L));
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(post("/api/video-tasks/9/retry").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(9));

        verify(service, times(1)).retry(9L);
    }

    @Test
    void submitForShot_taskFields_roundTrip() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        Records.VideoTaskResponse response = task(100L, 7L);
        when(service.submit(7L)).thenReturn(new Records.SubmitOutcome(response, true));
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(post("/api/shots/7/video-tasks").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.provider").value("mock"))
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.attempts").value(2));
    }

    @Test
    void get_wrongMethod_returns405() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(post("/api/video-tasks/9").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void submitForShot_nonNumericId_returns400() throws Exception {
        VideoTaskService service = mock(VideoTaskService.class);
        MockMvc mockMvc = buildMockMvc(service);

        mockMvc.perform(post("/api/shots/abc/video-tasks").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }
}