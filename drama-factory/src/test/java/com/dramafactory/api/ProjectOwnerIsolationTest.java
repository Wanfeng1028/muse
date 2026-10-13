package com.dramafactory.api;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.ProjectStatus;
import com.dramafactory.repository.DramaProjectRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ProjectOwnerIsolationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private DramaProjectRepository projectRepository;

    private String createBody(String title) {
        return "{\"title\":\"" + title + "\",\"genre\":\"drama\",\"synopsis\":\"s\",\"targetEpisodes\":3}";
    }

    @Test
    void ownerIsolationAcrossUsers() throws Exception {
        String createResp = mockMvc.perform(post("/api/projects")
                        .requestAttr("auth.userId", "user-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("A项目")))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.ownerId").value("user-a"))
                .andReturn().getResponse().getContentAsString();

        Long projectId = extractId(createResp);

        mockMvc.perform(get("/api/projects").requestAttr("auth.userId", "user-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)));

        mockMvc.perform(get("/api/projects").requestAttr("auth.userId", "user-b"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(0)));

        mockMvc.perform(get("/api/projects/" + projectId).requestAttr("auth.userId", "user-b"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("Forbidden"));
    }

    @Test
    void openModeDefaultsToLocal() throws Exception {
        String createResp = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("本地项目")))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.ownerId").value(CurrentUser.DEFAULT_OWNER_ID))
                .andReturn().getResponse().getContentAsString();

        Long projectId = extractId(createResp);

        mockMvc.perform(get("/api/projects"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.id==" + projectId + ")]", hasSize(1)));
    }

    @Test
    void ownerCannotTouchOthersProjectOnUpdateDelete() throws Exception {
        String createResp = mockMvc.perform(post("/api/projects")
                        .requestAttr("auth.userId", "user-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("A项目")))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();

        Long projectId = extractId(createResp);

        mockMvc.perform(put("/api/projects/" + projectId)
                        .requestAttr("auth.userId", "user-b")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"改标题\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("Forbidden"));

        mockMvc.perform(delete("/api/projects/" + projectId)
                        .requestAttr("auth.userId", "user-b"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("Forbidden"));

        mockMvc.perform(get("/api/projects/" + projectId).requestAttr("auth.userId", "user-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ownerId").value("user-a"));
    }

    private Long extractId(String json) {
        int idx = json.indexOf("\"id\":");
        if (idx < 0) {
            throw new IllegalStateException("no id in response: " + json);
        }
        int start = idx + 5;
        int end = start;
        while (end < json.length() && Character.isDigit(json.charAt(end))) {
            end++;
        }
        return Long.parseLong(json.substring(start, end));
    }
}
