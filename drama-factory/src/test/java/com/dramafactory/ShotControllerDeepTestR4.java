package com.dramafactory;

import com.dramafactory.controller.ShotController;
import com.dramafactory.dto.Records;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.ProjectStatus;
import com.dramafactory.service.EpisodeService;
import com.dramafactory.service.ProjectService;
import com.dramafactory.service.ScriptSplitterService;
import com.dramafactory.service.ShotService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ShotControllerDeepTestR4 {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private ProjectService projectService;

    @Autowired
    private EpisodeService episodeService;

    @Autowired
    private ShotService shotService;

    @MockBean
    private ScriptSplitterService scriptSplitterService;

    private Long createProject() {
        Records.ProjectRequest req = new Records.ProjectRequest(
                "proj-" + System.nanoTime(), null, null, ProjectStatus.DRAFT, null);
        Records.ProjectResponse resp = projectService.create(req);
        return resp.id();
    }

    private Long createEpisode(Long projectId) {
        Records.EpisodeRequest req = new Records.EpisodeRequest(
                1, "ep-" + System.nanoTime(), null, EpisodeStatus.DRAFT, null);
        Records.EpisodeResponse resp = episodeService.create(projectId, req);
        return resp.id();
    }

    private Long createEpisode() {
        return createEpisode(createProject());
    }

    private Long createShot(Long episodeId, int shotNo) {
        Records.ShotRequest req = new Records.ShotRequest(
                shotNo, null, null, "desc-" + System.nanoTime(), null, null, null);
        Records.ShotResponse resp = shotService.create(episodeId, req);
        return resp.id();
    }

    @Test
    void listShots_emptyEpisode_returnsEmptyArray() throws Exception {
        Long episodeId = createEpisode();
        mockMvc.perform(get("/api/episodes/{episodeId}/shots", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void createShot_valid_returns201() throws Exception {
        Long episodeId = createEpisode();
        Map<String, Object> body = new HashMap<>();
        body.put("shotNo", 1);
        body.put("description", "hello-" + System.nanoTime());
        MvcResult result = mockMvc.perform(post("/api/episodes/{episodeId}/shots", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNumber())
                .andExpect(jsonPath("$.shotNo").value(1))
                .andReturn();
        assertThat(result.getResponse().getContentAsString()).contains("\"shotNo\":1");
    }

    @Test
    void createShot_missingShotNo_returns400() throws Exception {
        Long episodeId = createEpisode();
        Map<String, Object> body = new HashMap<>();
        body.put("description", "no-shot-no-" + System.nanoTime());
        mockMvc.perform(post("/api/episodes/{episodeId}/shots", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createShot_unknownEpisode_returns404() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("shotNo", 1);
        body.put("description", "x-" + System.nanoTime());
        mockMvc.perform(post("/api/episodes/{episodeId}/shots", 999999999L)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isNotFound());
    }

    @Test
    void updateShot_valid_returns200() throws Exception {
        Long episodeId = createEpisode();
        Long shotId = createShot(episodeId, 1);
        String newDesc = "updated-" + System.nanoTime();
        Map<String, Object> body = new HashMap<>();
        body.put("shotNo", 1);
        body.put("description", newDesc);
        mockMvc.perform(put("/api/shots/{id}", shotId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(shotId))
                .andExpect(jsonPath("$.description").value(newDesc));
    }

    @Test
    void updateShot_unknownId_returns404() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("shotNo", 1);
        body.put("description", "x-" + System.nanoTime());
        mockMvc.perform(put("/api/shots/{id}", 999999999L)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isNotFound());
    }

    @Test
    void deleteShot_valid_returns204() throws Exception {
        Long episodeId = createEpisode();
        Long shotId = createShot(episodeId, 1);
        mockMvc.perform(delete("/api/shots/{id}", shotId))
                .andExpect(status().isNoContent());
        mockMvc.perform(get("/api/episodes/{episodeId}/shots", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void deleteShot_unknownId_returns404() throws Exception {
        mockMvc.perform(delete("/api/shots/{id}", 999999999L))
                .andExpect(status().isNotFound());
    }

    @Test
    void splitFromScript_mocked_returns201() throws Exception {
        Long episodeId = createEpisode();
        List<Records.ShotResponse> mocked = new ArrayList<>();
        mocked.add(new Records.ShotResponse(1L, episodeId, 1, null, null, null, null,
                "a-" + System.nanoTime(), null, null, null, null, null));
        mocked.add(new Records.ShotResponse(2L, episodeId, 2, null, null, null, null,
                "b-" + System.nanoTime(), null, null, null, null, null));
        when(scriptSplitterService.splitFromScript(eq(episodeId), anyString(), isNull(Long.class)))
                .thenReturn(mocked);

        Map<String, Object> body = new HashMap<>();
        body.put("scriptText", "script-" + System.nanoTime());
        mockMvc.perform(post("/api/episodes/{episodeId}/shots/from-script", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.length()").value(2));
    }

    @Test
    void splitFromScript_blankScript_returns400() throws Exception {
        Long episodeId = createEpisode();
        Map<String, Object> body = new HashMap<>();
        body.put("scriptText", "");
        mockMvc.perform(post("/api/episodes/{episodeId}/shots/from-script", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void replaceShots_mocked_returns201() throws Exception {
        Long episodeId = createEpisode();
        List<Records.ShotResponse> mocked = new ArrayList<>();
        mocked.add(new Records.ShotResponse(1L, episodeId, 1, null, null, null, null,
                "r-" + System.nanoTime(), null, null, null, null, null));
        when(scriptSplitterService.replaceShots(eq(episodeId), any()))
                .thenReturn(mocked);

        Map<String, Object> item = new HashMap<>();
        item.put("shotNo", 1);
        item.put("description", "batch-" + System.nanoTime());
        Map<String, Object> body = new HashMap<>();
        body.put("shots", Collections.singletonList(item));
        mockMvc.perform(post("/api/episodes/{episodeId}/shots/batch", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.length()").value(1));
    }

    @Test
    void replaceShots_nullShots_returns400() throws Exception {
        Long episodeId = createEpisode();
        Map<String, Object> body = new HashMap<>();
        body.put("shots", null);
        mockMvc.perform(post("/api/episodes/{episodeId}/shots/batch", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void reorderShots_valid_rewritesShotNoByIdOrder() throws Exception {
        Long episodeId = createEpisode();
        Long s1 = createShot(episodeId, 1);
        Long s2 = createShot(episodeId, 2);
        Long s3 = createShot(episodeId, 3);

        Map<String, Object> body = new HashMap<>();
        body.put("shotIds", Arrays.asList(s3, s2, s1));
        mockMvc.perform(post("/api/episodes/{episodeId}/shots/reorder", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(3))
                .andExpect(jsonPath("$[0].id").value(s3.intValue()))
                .andExpect(jsonPath("$[1].id").value(s2.intValue()))
                .andExpect(jsonPath("$[2].id").value(s1.intValue()))
                .andExpect(jsonPath("$[0].shotNo").value(1))
                .andExpect(jsonPath("$[2].shotNo").value(3));
    }

    @Test
    void listShots_afterCreate_returnsOrderedList() throws Exception {
        Long episodeId = createEpisode();
        createShot(episodeId, 2);
        createShot(episodeId, 1);
        mockMvc.perform(get("/api/episodes/{episodeId}/shots", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].shotNo").value(1))
                .andExpect(jsonPath("$[1].shotNo").value(2));
    }
}