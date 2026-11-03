package com.dramafactory.controller;
import com.dramafactory.dto.canvas.*;

import com.dramafactory.config.JwtVerifier;
import com.dramafactory.exception.CanvasConflictException;
import com.dramafactory.exception.ResourceNotFoundException;
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
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Collections;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CanvasProjectController.class)
class CanvasSlice1ControllerTest {

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
    void getCanvas_returnsV2WithETag() throws Exception {
        when(canvasProjectService.loadV2()).thenReturn(project(6));

        mockMvc.perform(get("/api/canvas"))
                .andExpect(status().isOk())
                .andExpect(header().string("ETag", "\"6\""))
                .andExpect(jsonPath("$.schema_version").value(2))
                .andExpect(jsonPath("$.version").value(6));
    }

    @Test
    void getCanvas_ifNoneMatch_returns304() throws Exception {
        when(canvasProjectService.loadV2()).thenReturn(project(6));

        mockMvc.perform(get("/api/canvas").header("If-None-Match", "\"6\""))
                .andExpect(status().isNotModified());
    }

    @Test
    void getCanvasProject_returnsRevisionMirroringVersion() throws Exception {
        when(canvasProjectService.loadV2()).thenReturn(project(6));

        mockMvc.perform(get("/api/canvas/project"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.schema_version").value(2))
                .andExpect(jsonPath("$.version").value(6))
                .andExpect(jsonPath("$.revision").value(6));
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
    void putProject_conflict_returns409WithFields() throws Exception {
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

    @Test
    void putProject_invalidPayload_returns400() throws Exception {
        when(canvasProjectService.saveV2(any(), anyString()))
                .thenThrow(new IllegalArgumentException("画布项目格式不对"));

        String body = "{\"schema_version\":2,\"base_version\":1,\"nodes\":[],\"edges\":[]}";
        mockMvc.perform(put("/api/canvas/project")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest());
    }

    @Test
    void patchCanvas_valid_returns200() throws Exception {
        when(canvasProjectService.applyPatch(any(), any(), anyString())).thenReturn(project(3));

        String body = "{\"base_version\":2,\"ops\":[{\"op\":\"update_node\",\"node_id\":\"n1\",\"fields\":{\"status\":\"done\"}}]}";
        mockMvc.perform(patch("/api/canvas")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value(3));
    }

    @Test
    void patchCanvas_nodeNotFound_returns404() throws Exception {
        when(canvasProjectService.applyPatch(any(), any(), anyString()))
                .thenThrow(new ResourceNotFoundException("node", 0L));

        String body = "{\"base_version\":2,\"ops\":[{\"op\":\"update_node\",\"node_id\":\"nope\",\"fields\":{\"status\":\"done\"}}]}";
        mockMvc.perform(patch("/api/canvas")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isNotFound());
    }

    @Test
    void getCanvasEvents_startsAsyncAndPassesVersion() throws Exception {
        when(canvasProjectService.currentVersion()).thenReturn(6);
        when(canvasEventService.subscribe(eq(6))).thenReturn(new SseEmitter());

        mockMvc.perform(get("/api/canvas/events"))
                .andExpect(request().asyncStarted());

        verify(canvasEventService).subscribe(eq(6));
    }

    @Test
    void postProposal_returns202Pending() throws Exception {
        CanvasProposalV2 proposal = new CanvasProposalV2("p-1", 1, Collections.emptyList(),
                "pending", "2026-10-16T00:00:00+08:00", "editor", "");
        when(canvasProjectService.createProposal(any())).thenReturn(proposal);

        String body = "{\"base_version\":1,\"ops\":[]}";
        mockMvc.perform(post("/api/canvas/proposals")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("pending"))
                .andExpect(jsonPath("$.id").value("p-1"));
    }

    @Test
    void listProposals_returns200Array() throws Exception {
        CanvasProposalV2 proposal = new CanvasProposalV2("p-1", 1, Collections.emptyList(),
                "pending", "2026-10-16T00:00:00+08:00", "editor", "");
        when(canvasProjectService.listProposals()).thenReturn(List.of(proposal));

        mockMvc.perform(get("/api/canvas/proposals"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$[0].id").value("p-1"));
    }

    @Test
    void postJob_returns202Running() throws Exception {
        CanvasJobV2 job = new CanvasJobV2("j-1", "n1", "running", 2,
                "2026-10-16T00:00:00+08:00", "2026-10-16T00:00:00+08:00");
        when(canvasJobService.createJob(eq("n1"))).thenReturn(job);

        String body = "{\"node_id\":\"n1\"}";
        mockMvc.perform(post("/api/canvas/jobs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("running"))
                .andExpect(jsonPath("$.job_id").value("j-1"));
    }

    @Test
    void getJob_notFound_returns404() throws Exception {
        when(canvasJobService.getJob("nope")).thenThrow(new ResourceNotFoundException("job", 0L));

        mockMvc.perform(get("/api/canvas/jobs/nope"))
                .andExpect(status().isNotFound());
    }
}
