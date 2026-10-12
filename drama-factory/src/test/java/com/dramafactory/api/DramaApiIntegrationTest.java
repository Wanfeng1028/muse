package com.dramafactory.api;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.Map;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.greaterThan;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class DramaApiIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void fullFlow() throws Exception {
        // 1) GET /api/health -> 200, status=ok
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));

        // 2) POST /api/projects -> 201, title=逆袭千金, 取 id
        Map<String, Object> createProject = new HashMap<>();
        createProject.put("title", "逆袭千金");
        createProject.put("genre", "都市");
        createProject.put("synopsis", "被退婚的千金逆袭复仇");
        createProject.put("targetEpisodes", 20);

        MvcResult createProjectResult = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createProject)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("逆袭千金"))
                .andReturn();

        JsonNode projectNode = objectMapper.readTree(createProjectResult.getResponse().getContentAsString());
        long projectId = projectNode.get("id").asLong();

        // 3) POST /api/projects 缺 title -> 400
        Map<String, Object> invalidProject = new HashMap<>();
        invalidProject.put("genre", "都市");

        mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(invalidProject)))
                .andExpect(status().isBadRequest());

        // 4) GET /api/projects/999999 -> 404
        mockMvc.perform(get("/api/projects/999999"))
                .andExpect(status().isNotFound());

        // 5) GET /api/projects/{id} -> episodeCount=0
        mockMvc.perform(get("/api/projects/{id}", projectId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.episodeCount").value(0));

        // 6) POST /api/projects/{id}/episodes -> 201, 取 episodeId
        Map<String, Object> createEpisode = new HashMap<>();
        createEpisode.put("episodeNo", 1);
        createEpisode.put("title", "退婚之夜");
        createEpisode.put("outline", "千金在订婚宴上被当众退婚，暗下决心复仇");

        MvcResult createEpisodeResult = mockMvc.perform(post("/api/projects/{id}/episodes", projectId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createEpisode)))
                .andExpect(status().isCreated())
                .andReturn();

        JsonNode episodeNode = objectMapper.readTree(createEpisodeResult.getResponse().getContentAsString());
        long episodeId = episodeNode.get("id").asLong();

        // 7) POST /api/episodes/{episodeId}/generate-script -> 200, sceneCount=4, scriptText 含 "第1场"
        mockMvc.perform(post("/api/episodes/{episodeId}/generate-script", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sceneCount").value(4))
                .andExpect(jsonPath("$.scriptText").value(org.hamcrest.Matchers.containsString("第1场")));

        // 8) GET /api/episodes/{episodeId}/scenes -> 200, length=4
        mockMvc.perform(get("/api/episodes/{episodeId}/scenes", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(4));

        // 9) POST /api/projects/{id}/characters -> 201; GET characters -> length=1
        Map<String, Object> createCharacter = new HashMap<>();
        createCharacter.put("name", "林晚晚");
        createCharacter.put("role", "LEAD");
        createCharacter.put("description", "女主");
        createCharacter.put("traits", "坚韧");

        mockMvc.perform(post("/api/projects/{id}/characters", projectId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createCharacter)))
                .andExpect(status().isCreated());

        mockMvc.perform(get("/api/projects/{id}/characters", projectId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1));

        // 10) POST /api/episodes/{episodeId}/scenes -> 201, 取 sceneId, GET scenes -> length=5, DELETE /api/scenes/{sceneId}
        Map<String, Object> createScene = new HashMap<>();
        createScene.put("sceneNo", 5);
        createScene.put("location", "天台");
        createScene.put("timeOfDay", "夜");
        createScene.put("description", "手动补场");
        createScene.put("dialogue", "……");
        createScene.put("prompt", "rooftop night, cinematic");

        MvcResult createSceneResult = mockMvc.perform(post("/api/episodes/{episodeId}/scenes", episodeId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(createScene)))
                .andExpect(status().isCreated())
                .andReturn();

        JsonNode sceneNode = objectMapper.readTree(createSceneResult.getResponse().getContentAsString());
        long sceneId = sceneNode.get("id").asLong();

        mockMvc.perform(get("/api/episodes/{episodeId}/scenes", episodeId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(5));

        mockMvc.perform(delete("/api/scenes/{sceneId}", sceneId))
                .andExpect(status().isNoContent());

        // 11) GET /api/stats -> projects=1, episodes=1
        mockMvc.perform(get("/api/stats"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projects").value(1))
                .andExpect(jsonPath("$.episodes").value(1));

        // 12) DELETE episode -> 204; DELETE project -> 204; GET project -> 404
        mockMvc.perform(delete("/api/episodes/{episodeId}", episodeId))
                .andExpect(status().isNoContent());

        mockMvc.perform(delete("/api/projects/{id}", projectId))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/projects/{id}", projectId))
                .andExpect(status().isNotFound());
    }
}
