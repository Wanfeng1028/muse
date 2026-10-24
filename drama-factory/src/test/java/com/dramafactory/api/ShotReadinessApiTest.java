package com.dramafactory.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@AutoConfigureMockMvc
class ShotReadinessApiTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private long createProject() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"准备度测试项目\",\"genre\":\"都市\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }

    private long createEpisode(long pid) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/projects/" + pid + "/episodes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"episodeNo\":1,\"title\":\"第一集\"}"))
                .andExpect(status().isCreated())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString()).get("id").asLong();
    }

    private long createShot(long episodeId, String body) throws Exception {
        MvcResult result = mockMvc.perform(post("/api/episodes/" + episodeId + "/shots")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn();
        JsonNode node = objectMapper.readTree(result.getResponse().getContentAsString());
        return node.get("id").asLong();
    }

    @Test
    void readyShot_reportsReadyThroughApi() throws Exception {
        long pid = createProject();
        long episodeId = createEpisode(pid);
        long shotId = createShot(episodeId,
                "{\"shotNo\":1,\"shotSize\":\"JIN_JING\",\"cameraMove\":\"TUI\","
                        + "\"description\":\"主角走进雨夜的巷子\",\"durationSeconds\":5,"
                        + "\"videoPrompt\":\"rainy alley, man walking, cinematic\"}");

        mockMvc.perform(get("/api/episodes/" + episodeId + "/shots/" + shotId + "/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shotId").value(shotId))
                .andExpect(jsonPath("$.ready").value(true))
                .andExpect(jsonPath("$.promptPreview").value("rainy alley, man walking, cinematic"))
                .andExpect(jsonPath("$.promptPreviewDerived").value(false));
    }

    @Test
    void missingPrompt_reportsNotReadyWithDerivedPreview() throws Exception {
        long pid = createProject();
        long episodeId = createEpisode(pid);
        long shotId = createShot(episodeId,
                "{\"shotNo\":1,\"description\":\"主角走进雨夜的巷子\",\"durationSeconds\":5}");

        mockMvc.perform(get("/api/episodes/" + episodeId + "/shots/" + shotId + "/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ready").value(false))
                .andExpect(jsonPath("$.promptPreviewDerived").value(true))
                .andExpect(jsonPath("$.promptPreview").value(org.hamcrest.Matchers.containsString("主角走进雨夜的巷子")));
    }

    @Test
    void episodeReadiness_listsAllShots() throws Exception {
        long pid = createProject();
        long episodeId = createEpisode(pid);
        createShot(episodeId,
                "{\"shotNo\":1,\"description\":\"第一镜\",\"durationSeconds\":5,"
                        + "\"videoPrompt\":\"prompt one\"}");
        createShot(episodeId,
                "{\"shotNo\":2,\"description\":\"第二镜\",\"durationSeconds\":4}");

        mockMvc.perform(get("/api/episodes/" + episodeId + "/shots-readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].ready").value(true))
                .andExpect(jsonPath("$[1].ready").value(false));
    }

    @Test
    void readinessOfShotFromOtherEpisode_returnsNotFound() throws Exception {
        long pid = createProject();
        long episodeId = createEpisode(pid);
        long otherEpisodeId = createEpisode(pid);
        long shotId = createShot(episodeId,
                "{\"shotNo\":1,\"description\":\"第一镜\",\"durationSeconds\":5,"
                        + "\"videoPrompt\":\"prompt one\"}");

        mockMvc.perform(get("/api/episodes/" + otherEpisodeId + "/shots/" + shotId + "/readiness"))
                .andExpect(status().isNotFound());
    }
}
