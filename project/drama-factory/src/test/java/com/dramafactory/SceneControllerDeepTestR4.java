package com.dramafactory;

import com.dramafactory.dto.Records;
import com.dramafactory.service.EpisodeService;
import com.dramafactory.service.ProjectService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SceneControllerDeepTestR4 {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ProjectService projectService;

    @Autowired
    private EpisodeService episodeService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private Long newEpisode() {
        String suffix = String.valueOf(System.nanoTime());
        Records.ProjectResponse project = projectService.create(
                new Records.ProjectRequest("proj-" + suffix, null, null, null, null));
        Records.EpisodeResponse episode = episodeService.create(
                project.id(), new Records.EpisodeRequest(1, "ep-" + suffix, null, null, null));
        return episode.id();
    }

    private Long newScene(Long episodeId, int sceneNo, String location) throws Exception {
        Records.SceneRequest request = new Records.SceneRequest(sceneNo, location, null, null, null, null);
        String body = mockMvc.perform(post("/api/episodes/{episodeId}/scenes", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return objectMapper.readTree(body).get("id").asLong();
    }

    @Test
    void listByEpisode_emptyEpisode_returnsEmptyArray() throws Exception {
        Long episodeId = newEpisode();
        mockMvc.perform(get("/api/episodes/{episodeId}/scenes", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void create_valid_returns201() throws Exception {
        Long episodeId = newEpisode();
        Records.SceneRequest request = new Records.SceneRequest(1, "雨夜街道", null, null, null, null);
        mockMvc.perform(post("/api/episodes/{episodeId}/scenes", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.sceneNo").value(1))
                .andExpect(jsonPath("$.location").value("雨夜街道"));
    }

    @Test
    void create_missingSceneNo_returns400() throws Exception {
        Long episodeId = newEpisode();
        Records.SceneRequest request = new Records.SceneRequest(null, "雨夜街道", null, null, null, null);
        mockMvc.perform(post("/api/episodes/{episodeId}/scenes", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void create_unknownEpisode_returns404() throws Exception {
        Records.SceneRequest request = new Records.SceneRequest(1, "雨夜街道", null, null, null, null);
        mockMvc.perform(post("/api/episodes/{episodeId}/scenes", 999999999L)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isNotFound());
    }

    @Test
    void create_allFields_roundTrip() throws Exception {
        Long episodeId = newEpisode();
        Records.SceneRequest request = new Records.SceneRequest(
                7, "旧仓库", "深夜", "潮湿阴暗的仓库内部", "你到底是谁？", "cinematic wide shot, fog");
        mockMvc.perform(post("/api/episodes/{episodeId}/scenes", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.sceneNo").value(7))
                .andExpect(jsonPath("$.location").value("旧仓库"))
                .andExpect(jsonPath("$.timeOfDay").value("深夜"))
                .andExpect(jsonPath("$.description").value("潮湿阴暗的仓库内部"))
                .andExpect(jsonPath("$.dialogue").value("你到底是谁？"))
                .andExpect(jsonPath("$.prompt").value("cinematic wide shot, fog"));
    }

    @Test
    void update_valid_returns200() throws Exception {
        Long episodeId = newEpisode();
        Long sceneId = newScene(episodeId, 1, "雨夜街道");
        Records.SceneRequest request = new Records.SceneRequest(1, "晴天公园", null, null, null, null);
        mockMvc.perform(put("/api/scenes/{id}", sceneId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(sceneId))
                .andExpect(jsonPath("$.location").value("晴天公园"));
    }

    @Test
    void update_unknownId_returns404() throws Exception {
        Records.SceneRequest request = new Records.SceneRequest(1, "晴天公园", null, null, null, null);
        mockMvc.perform(put("/api/scenes/{id}", 999999999L)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isNotFound());
    }

    @Test
    void update_missingSceneNo_returns400() throws Exception {
        Long episodeId = newEpisode();
        Long sceneId = newScene(episodeId, 1, "雨夜街道");
        Records.SceneRequest request = new Records.SceneRequest(null, "晴天公园", null, null, null, null);
        mockMvc.perform(put("/api/scenes/{id}", sceneId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void delete_valid_returns204() throws Exception {
        Long episodeId = newEpisode();
        Long sceneId = newScene(episodeId, 1, "雨夜街道");
        mockMvc.perform(delete("/api/scenes/{id}", sceneId))
                .andExpect(status().isNoContent());
        mockMvc.perform(get("/api/episodes/{episodeId}/scenes", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void delete_unknownId_returns404() throws Exception {
        mockMvc.perform(delete("/api/scenes/{id}", 999999999L))
                .andExpect(status().isNotFound());
    }

    @Test
    void listByEpisode_multipleScenes_returnsAll() throws Exception {
        Long episodeId = newEpisode();
        newScene(episodeId, 1, "雨夜街道");
        newScene(episodeId, 2, "旧仓库");
        newScene(episodeId, 3, "天台");
        mockMvc.perform(get("/api/episodes/{episodeId}/scenes", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(3));
    }

    @Test
    void create_twice_sceneNoDuplicate_allowedOrNot() throws Exception {
        Long episodeId = newEpisode();
        Records.SceneRequest first = new Records.SceneRequest(1, "雨夜街道", null, null, null, null);
        mockMvc.perform(post("/api/episodes/{episodeId}/scenes", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(first)))
                .andExpect(status().isCreated());
        Records.SceneRequest second = new Records.SceneRequest(1, "旧仓库", null, null, null, null);
        mockMvc.perform(post("/api/episodes/{episodeId}/scenes", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(second)))
                .andExpect(status().isCreated());
    }

    @Test
    void create_nullOptionalFields_ok() throws Exception {
        Long episodeId = newEpisode();
        Records.SceneRequest request = new Records.SceneRequest(5, null, null, null, null, null);
        mockMvc.perform(post("/api/episodes/{episodeId}/scenes", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.sceneNo").value(5));
    }

    @Test
    void delete_thenGet_returnsEmpty() throws Exception {
        Long episodeId = newEpisode();
        Long first = newScene(episodeId, 1, "雨夜街道");
        newScene(episodeId, 2, "旧仓库");
        mockMvc.perform(delete("/api/scenes/{id}", first))
                .andExpect(status().isNoContent());
        mockMvc.perform(get("/api/episodes/{episodeId}/scenes", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1));
    }
}