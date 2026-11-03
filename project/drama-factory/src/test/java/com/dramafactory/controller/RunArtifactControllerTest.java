package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.FinalCutRepository;
import com.dramafactory.repository.SceneRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.RunService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import com.dramafactory.config.JwtVerifier;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * RunArtifactController 测试。
 */
@WebMvcTest(RunArtifactController.class)
class RunArtifactControllerTest {

    @MockBean
    private JwtVerifier jwtVerifier;

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private RunService runService;

    @MockBean
    private EpisodeRepository episodeRepository;

    @MockBean
    private SceneRepository sceneRepository;

    @MockBean
    private ShotRepository shotRepository;

    @MockBean
    private VideoTaskRepository videoTaskRepository;

    @MockBean
    private FinalCutRepository finalCutRepository;

    @Test
    void missingRunReturns404() throws Exception {
        when(runService.getRun(999L)).thenThrow(new ResourceNotFoundException("Run", 999L));

        mockMvc.perform(get("/api/runs/999/artifacts"))
                .andExpect(status().isNotFound());
    }
}
