package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.AgentStep;
import com.dramafactory.model.AgentStepStatus;
import com.dramafactory.model.AgentType;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.service.RunService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * RunController Web 层测试（仅加载 MVC 切片，RunService 全部 Mock）。
 */
@WebMvcTest(controllers = RunController.class)
class RunControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private RunService runService;

    private Records.PlanPreview plan() {
        return new Records.PlanPreview("做一部 1 集短剧",
                List.of(new Records.PlanEpisode(1, "第 1 集", "大纲")), false);
    }

    private Records.RunDetailResponse detail(long id, RunStatus status) {
        Run run = new Run();
        run.setId(id);
        run.setGoal("做一部 1 集短剧");
        run.setStatus(status);
        run.setCreatedAt(LocalDateTime.now());
        run.setUpdatedAt(LocalDateTime.now());
        AgentStep step = new AgentStep();
        step.setId(10L);
        step.setSeqNo(1);
        step.setAgentType(AgentType.SCRIPT);
        step.setName("第 1 集 · 编剧");
        step.setStatus(AgentStepStatus.PENDING);
        return RunService.toDetailResponse(run, List.of(step));
    }

    @Test
    void previewShouldReturn200() throws Exception {
        when(runService.planPreview(anyString())).thenReturn(plan());

        mockMvc.perform(post("/api/runs/preview")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"goal\":\"做一部 1 集短剧\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.goal").value("做一部 1 集短剧"))
                .andExpect(jsonPath("$.episodes[0].title").value("第 1 集"));
    }

    @Test
    void previewShouldReturn400WhenGoalBlank() throws Exception {
        mockMvc.perform(post("/api/runs/preview")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"goal\":\"  \"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createShouldReturn201WithRunId() throws Exception {
        when(runService.createRun(anyString(), any(Records.PlanPreview.class))).thenReturn(5L);

        mockMvc.perform(post("/api/runs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"goal\":\"做一部 1 集短剧\","
                                + "\"plan\":{\"goal\":\"做一部 1 集短剧\","
                                + "\"episodes\":[{\"episodeNo\":1,\"title\":\"第 1 集\",\"outline\":\"大纲\"}],"
                                + "\"fallback\":false}}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.runId").value(5));
    }

    @Test
    void getShouldReturn200() throws Exception {
        when(runService.getRun(1L)).thenReturn(detail(1L, RunStatus.RUNNING));

        mockMvc.perform(get("/api/runs/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.id").value(1))
                .andExpect(jsonPath("$.steps[0].agentLabel").value("编剧"));
    }

    @Test
    void getShouldReturn404WhenNotFound() throws Exception {
        when(runService.getRun(999L)).thenThrow(new ResourceNotFoundException("Run", 999L));

        mockMvc.perform(get("/api/runs/999"))
                .andExpect(status().isNotFound());
    }

    @Test
    void pauseShouldReturn200() throws Exception {
        when(runService.getRun(1L)).thenReturn(detail(1L, RunStatus.PAUSED));

        mockMvc.perform(post("/api/runs/1/pause"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.run.status").value("PAUSED"));
    }

    @Test
    void pauseShouldReturn409OnIllegalTransition() throws Exception {
        when(runService.getRun(anyLong())).thenReturn(detail(1L, RunStatus.RUNNING));
        org.mockito.Mockito.doThrow(new IllegalStateException("只有 RUNNING 状态可暂停"))
                .when(runService).pause(1L);

        mockMvc.perform(post("/api/runs/1/pause"))
                .andExpect(status().isConflict());
    }

    @Test
    void approveShouldReturn200() throws Exception {
        when(runService.getRun(1L)).thenReturn(detail(1L, RunStatus.RUNNING));

        mockMvc.perform(post("/api/runs/1/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"approved\":true,\"note\":\"画面可以\"}"))
                .andExpect(status().isOk());
    }

    @Test
    void rerunShouldReturn201() throws Exception {
        when(runService.rerun(eq(1L), anyString())).thenReturn(6L);

        mockMvc.perform(post("/api/runs/1/rerun")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"goal\":\"换个题材重跑\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.runId").value(6));
    }

    @Test
    void statsShouldReturn200() throws Exception {
        when(runService.stats()).thenReturn(new Records.RunStatsResponse(4, 3, 1, 0.75, 12000));

        mockMvc.perform(get("/api/runs/stats"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.successRate").value(0.75));
    }

    @Test
    void logsShouldReturn200() throws Exception {
        when(runService.readStepLog(eq(1L), eq(10L), eq(0L)))
                .thenReturn(new Records.LogReadResponse("[12:00:01] 开始\n", 18, false));

        mockMvc.perform(get("/api/runs/1/steps/10/logs").param("offset", "0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nextOffset").value(18));
    }
}
