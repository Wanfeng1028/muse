package com.dramafactory;

import com.dramafactory.dto.Records;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.greaterThanOrEqualTo;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PipelineControllerDeepTestR4 {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private Long createProject(String title) throws Exception {
        Records.ProjectRequest request = new Records.ProjectRequest(
                title, "drama", "synopsis for " + title, null, 12);
        MvcResult result = mockMvc.perform(post("/api/projects")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andReturn();
        Records.ProjectResponse response = objectMapper.readValue(
                result.getResponse().getContentAsString(), Records.ProjectResponse.class);
        return response.id();
    }

    private void createEpisode(Long projectId, int episodeNo, String title) throws Exception {
        Records.EpisodeRequest request = new Records.EpisodeRequest(
                episodeNo, title, "outline " + title, null, 300);
        mockMvc.perform(post("/api/projects/" + projectId + "/episodes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated());
    }

    @Test
    void getProjectPipeline_existingEmptyProject_returns200() throws Exception {
        String title = "empty-pipeline-" + System.nanoTime();
        Long projectId = createProject(title);

        mockMvc.perform(get("/api/projects/" + projectId + "/pipeline"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projectId").value(projectId.intValue()))
                .andExpect(jsonPath("$.title").value(title))
                .andExpect(jsonPath("$.episodes").isArray())
                .andExpect(jsonPath("$.episodes").isEmpty());
    }

    @Test
    void getProjectPipeline_withEpisodes_returnsEpisodes() throws Exception {
        String title = "with-episodes-" + System.nanoTime();
        Long projectId = createProject(title);
        createEpisode(projectId, 1, "ep-one-" + System.nanoTime());
        createEpisode(projectId, 2, "ep-two-" + System.nanoTime());

        mockMvc.perform(get("/api/projects/" + projectId + "/pipeline"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projectId").value(projectId.intValue()))
                .andExpect(jsonPath("$.episodes").isArray())
                .andExpect(jsonPath("$.episodes", hasSize(2)));
    }

    @Test
    void getProjectPipeline_unknownProject_returns404() throws Exception {
        mockMvc.perform(get("/api/projects/999999999/pipeline"))
                .andExpect(status().isNotFound());
    }

    @Test
    void getAllPipelines_returnsList() throws Exception {
        String title = "list-pipelines-" + System.nanoTime();
        createProject(title);

        mockMvc.perform(get("/api/pipelines"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$", hasSize(greaterThanOrEqualTo(1))));
    }

    @Test
    void getProductionStats_emptyProject_returnsZeros() throws Exception {
        String title = "stats-empty-" + System.nanoTime();
        Long projectId = createProject(title);

        mockMvc.perform(get("/api/projects/" + projectId + "/stats"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projectId").value(projectId.intValue()))
                .andExpect(jsonPath("$.shotCount").value(0))
                .andExpect(jsonPath("$.tasksDone").value(0));
    }

    @Test
    void getProductionStats_unknownProject_returns404() throws Exception {
        mockMvc.perform(get("/api/projects/999999999/stats"))
                .andExpect(status().isNotFound());
    }

    @Test
    void getProjectPipeline_responseHasProjectId() throws Exception {
        String title = "pid-match-" + System.nanoTime();
        Long projectId = createProject(title);

        mockMvc.perform(get("/api/projects/" + projectId + "/pipeline"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projectId").value(projectId.intValue()));
    }

    @Test
    void getAllPipelines_eachItemHasProjectId() throws Exception {
        createProject("each-pid-" + System.nanoTime());

        mockMvc.perform(get("/api/pipelines"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[*].projectId").exists());
    }

    @Test
    void getProjectPipeline_twice_returnsConsistent() throws Exception {
        String title = "consistent-" + System.nanoTime();
        Long projectId = createProject(title);

        String firstTitle = mockMvc.perform(get("/api/projects/" + projectId + "/pipeline"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        String secondTitle = mockMvc.perform(get("/api/projects/" + projectId + "/pipeline"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        Records.PipelineProjectView firstView = objectMapper.readValue(firstTitle, Records.PipelineProjectView.class);
        Records.PipelineProjectView secondView = objectMapper.readValue(secondTitle, Records.PipelineProjectView.class);

        org.junit.jupiter.api.Assertions.assertEquals(firstView.title(), secondView.title());
        org.junit.jupiter.api.Assertions.assertEquals(title, firstView.title());
    }

    @Test
    void getProductionStats_ratesAreNumbers() throws Exception {
        String title = "rates-numbers-" + System.nanoTime();
        Long projectId = createProject(title);

        mockMvc.perform(get("/api/projects/" + projectId + "/stats"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.shotCompletionRate").value(0))
                .andExpect(jsonPath("$.taskSuccessRate").value(0));
    }

    @Test
    void getProjectPipeline_nonNumericId_returns500DueToGlobalHandler() throws Exception {
        // 真实行为：路径变量类型转换失败抛 MethodArgumentTypeMismatchException，被
        // GlobalExceptionHandler 的 @ExceptionHandler(Exception.class) 捕获，转为 500（而非 400）
        mockMvc.perform(get("/api/projects/abc/pipeline"))
                .andExpect(status().isInternalServerError());
    }

    @Test
    void getAllPipelines_contentTypeJson() throws Exception {
        mockMvc.perform(get("/api/pipelines"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(content().string(containsString("[")));
    }
}