package com.dramafactory.controller;
import com.dramafactory.dto.canvas.*;

import com.dramafactory.config.JwtVerifier;
import com.dramafactory.exception.CanvasConflictException;
import com.dramafactory.service.CanvasEventService;
import com.dramafactory.service.CanvasJobService;
import com.dramafactory.service.CanvasProjectService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Collections;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CanvasProjectController.class)
class CanvasProjectControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private CanvasProjectService canvasProjectService;

    @MockBean
    private CanvasEventService canvasEventService;

    @MockBean
    private CanvasJobService canvasJobService;

    @MockBean
    private JwtVerifier jwtVerifier;

    private CanvasProjectV2 project(int version) {
        return new CanvasProjectV2(2, version, "editor", "2026-10-16T00:00:00+08:00",
                Collections.emptyList(), Collections.emptyList());
    }

    @Test
    void getProject_returnsProjectJson() throws Exception {
        when(canvasProjectService.loadV2()).thenReturn(project(6));

        mockMvc.perform(get("/api/canvas/project"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.schema_version").value(2))
                .andExpect(jsonPath("$.version").value(6))
                .andExpect(jsonPath("$.revision").value(6))
                .andExpect(jsonPath("$.nodes").isArray())
                .andExpect(jsonPath("$.edges").isArray());
    }

    @Test
    void putProject_validPayload_returns200() throws Exception {
        when(canvasProjectService.saveV2(any(), anyString())).thenReturn(project(2));

        String body = "{\"schema_version\":2,\"base_version\":1,\"nodes\":[],\"edges\":[]}";
        mockMvc.perform(put("/api/canvas/project")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value(2));
    }

    @Test
    void putProject_missingBaseVersion_returns400() throws Exception {
        when(canvasProjectService.saveV2(any(), anyString()))
                .thenThrow(new IllegalArgumentException("画布项目格式不对"));

        String body = "{\"schema_version\":2,\"nodes\":[],\"edges\":[]}";
        mockMvc.perform(put("/api/canvas/project")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest());
    }

    @Test
    void putProject_nodesNotArray_returns400() throws Exception {
        when(canvasProjectService.saveV2(any(), anyString()))
                .thenThrow(new IllegalArgumentException("画布项目格式不对"));

        String body = "{\"schema_version\":2,\"base_version\":1,\"nodes\":\"oops\",\"edges\":[]}";
        mockMvc.perform(put("/api/canvas/project")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest());
    }

    @Test
    void getMcpTools_returnsThreeTools() throws Exception {
        mockMvc.perform(get("/api/canvas/mcp/tools"))
                .andExpect(status().isOk());
    }

    @Test
    void putConflict_returns409WithVersionFields() throws Exception {
        when(canvasProjectService.saveV2(any(), anyString()))
                .thenThrow(new CanvasConflictException(3, "agent"));

        String body = "{\"schema_version\":2,\"base_version\":1,\"nodes\":[],\"edges\":[]}";
        mockMvc.perform(put("/api/canvas/project")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.current_version").value(3))
                .andExpect(jsonPath("$.updated_by").value("agent"));
    }
}
