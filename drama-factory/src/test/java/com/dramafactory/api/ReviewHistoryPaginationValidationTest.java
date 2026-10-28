package com.dramafactory.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
public class ReviewHistoryPaginationValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private Long createProject() throws Exception {
        String body = "{\"title\":\"T\",\"genre\":\"drama\",\"synopsis\":\"s\",\"targetEpisodes\":3}";
        String response = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        JsonNode node = objectMapper.readTree(response);
        return node.get("id").asLong();
    }

    private Long createEpisode(Long projectId) throws Exception {
        String body = "{\"episodeNo\":1,\"title\":\"E1\",\"outline\":\"o\",\"status\":null,\"durationSec\":null}";
        String response = mockMvc.perform(post("/api/projects/" + projectId + "/episodes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        JsonNode node = objectMapper.readTree(response);
        return node.get("id").asLong();
    }

    @Test
    void pageNegativeReturns400() throws Exception {
        Long projectId = createProject();
        Long episodeId = createEpisode(projectId);
        mockMvc.perform(get("/api/projects/" + projectId + "/episodes/" + episodeId + "/review/history")
                        .param("kind", "SCRIPT")
                        .param("page", "-1"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void sizeZeroReturns400() throws Exception {
        Long projectId = createProject();
        Long episodeId = createEpisode(projectId);
        mockMvc.perform(get("/api/projects/" + projectId + "/episodes/" + episodeId + "/review/history")
                        .param("kind", "SCRIPT")
                        .param("size", "0"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void sizeOver200Returns400() throws Exception {
        Long projectId = createProject();
        Long episodeId = createEpisode(projectId);
        mockMvc.perform(get("/api/projects/" + projectId + "/episodes/" + episodeId + "/review/history")
                        .param("kind", "SCRIPT")
                        .param("size", "201"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void size200Returns200() throws Exception {
        Long projectId = createProject();
        Long episodeId = createEpisode(projectId);
        mockMvc.perform(get("/api/projects/" + projectId + "/episodes/" + episodeId + "/review/history")
                        .param("kind", "SCRIPT")
                        .param("size", "200"))
                .andExpect(status().isOk());
    }

    @Test
    void size1Returns200() throws Exception {
        Long projectId = createProject();
        Long episodeId = createEpisode(projectId);
        mockMvc.perform(get("/api/projects/" + projectId + "/episodes/" + episodeId + "/review/history")
                        .param("kind", "SCRIPT")
                        .param("size", "1"))
                .andExpect(status().isOk());
    }

    @Test
    void defaultPageAndSizeReturns200() throws Exception {
        Long projectId = createProject();
        Long episodeId = createEpisode(projectId);
        mockMvc.perform(get("/api/projects/" + projectId + "/episodes/" + episodeId + "/review/history")
                        .param("kind", "SCRIPT"))
                .andExpect(status().isOk());
    }

    @Test
    void sizeNonNumericReturns400() throws Exception {
        Long projectId = createProject();
        Long episodeId = createEpisode(projectId);
        mockMvc.perform(get("/api/projects/" + projectId + "/episodes/" + episodeId + "/review/history")
                        .param("kind", "SCRIPT")
                        .param("size", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void pageNonNumericReturns400() throws Exception {
        Long projectId = createProject();
        Long episodeId = createEpisode(projectId);
        mockMvc.perform(get("/api/projects/" + projectId + "/episodes/" + episodeId + "/review/history")
                        .param("kind", "SCRIPT")
                        .param("page", "abc"))
                .andExpect(status().isBadRequest());
    }
}
