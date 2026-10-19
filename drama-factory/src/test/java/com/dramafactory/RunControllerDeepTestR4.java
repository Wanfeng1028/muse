package com.dramafactory;

import com.dramafactory.controller.RunController;
import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Run;
import com.dramafactory.model.RunStatus;
import com.dramafactory.service.RunService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RunControllerDeepTestR4 {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private RunService runService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private Records.PlanPreview plan(String goal) {
        return new Records.PlanPreview(goal, List.of(), false);
    }

    private Run runEntity(Long id, String goal, RunStatus status) {
        Run run = new Run();
        run.setId(id);
        run.setGoal(goal);
        run.setStatus(status);
        run.setCreatedAt(LocalDateTime.now());
        return run;
    }

    @Test
    void preview_valid_returnsPlan() throws Exception {
        when(runService.planPreview("做三集短剧")).thenReturn(plan("做三集短剧"));

        Map<String, Object> body = new HashMap<>();
        body.put("goal", "做三集短剧");

        mockMvc.perform(post("/api/runs/preview")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.goal").value("做三集短剧"));
    }

    @Test
    void preview_blankGoal_returns400() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("goal", "");

        mockMvc.perform(post("/api/runs/preview")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void preview_missingBody_returns500DueToGlobalHandler() throws Exception {
        // 真实行为：缺失请求体抛 HttpMessageNotReadableException，被 GlobalExceptionHandler 的
        // @ExceptionHandler(Exception.class) 捕获，转为 500（而非 400）
        mockMvc.perform(post("/api/runs/preview")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isInternalServerError());
    }

    @Test
    void create_valid_returns201() throws Exception {
        when(runService.createRun(eq("做三集短剧"), any(Records.PlanPreview.class), eq(null), eq(null)))
                .thenReturn(99L);

        Map<String, Object> body = new HashMap<>();
        body.put("goal", "做三集短剧");
        body.put("plan", plan("做三集短剧"));
        body.put("scriptSkillId", null);
        body.put("boardSkillId", null);

        mockMvc.perform(post("/api/runs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.runId").value(99));
    }

    @Test
    void create_nullPlan_returns400() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("goal", "做三集短剧");
        body.put("plan", null);

        mockMvc.perform(post("/api/runs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void create_blankGoal_returns400() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("goal", "");
        body.put("plan", plan("做三集短剧"));

        mockMvc.perform(post("/api/runs")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void list_empty_returnsEmptyArray() throws Exception {
        when(runService.listRuns()).thenReturn(new ArrayList<>());

        mockMvc.perform(get("/api/runs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void list_twoRuns_returnsTwo() throws Exception {
        Run r1 = runEntity(1L, "第一个", RunStatus.RUNNING);
        Run r2 = runEntity(2L, "第二个", RunStatus.RUNNING);
        when(runService.listRuns()).thenReturn(List.of(r1, r2));

        mockMvc.perform(get("/api/runs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].goal").value("第一个"));
    }

    @Test
    void detail_unknownId_returns404() throws Exception {
        when(runService.getRun(999L)).thenThrow(new ResourceNotFoundException("Run", 999L));

        mockMvc.perform(get("/api/runs/999"))
                .andExpect(status().isNotFound());
    }

    @Test
    void pause_callsService_returns200() throws Exception {
        when(runService.getRun(1L)).thenReturn(null);

        mockMvc.perform(post("/api/runs/1/pause"))
                .andExpect(status().isOk());

        verify(runService, times(1)).pause(1L);
    }

    @Test
    void resume_callsService_returns200() throws Exception {
        when(runService.getRun(1L)).thenReturn(null);

        mockMvc.perform(post("/api/runs/1/resume"))
                .andExpect(status().isOk());

        verify(runService, times(1)).resume(1L);
    }

    @Test
    void cancel_callsService_returns200() throws Exception {
        when(runService.getRun(1L)).thenReturn(null);

        mockMvc.perform(post("/api/runs/1/cancel"))
                .andExpect(status().isOk());

        verify(runService, times(1)).cancel(1L);
    }

    @Test
    void retry_callsService_returns200() throws Exception {
        when(runService.getRun(1L)).thenReturn(null);

        mockMvc.perform(post("/api/runs/1/steps/5/retry"))
                .andExpect(status().isOk());

        verify(runService, times(1)).retryStep(1L, 5L);
    }

    @Test
    void approve_true_passesTrue() throws Exception {
        when(runService.getRun(1L)).thenReturn(null);

        Map<String, Object> body = new HashMap<>();
        body.put("approved", true);
        body.put("note", "ok");

        mockMvc.perform(post("/api/runs/1/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());

        ArgumentCaptor<Boolean> approvedCaptor = ArgumentCaptor.forClass(Boolean.class);
        ArgumentCaptor<String> noteCaptor = ArgumentCaptor.forClass(String.class);
        verify(runService, times(1)).approve(eq(1L), approvedCaptor.capture(), noteCaptor.capture());
        assertThat(approvedCaptor.getValue()).isTrue();
        assertThat(noteCaptor.getValue()).isEqualTo("ok");
    }

    @Test
    void approve_noBody_treatedAsReject() throws Exception {
        when(runService.getRun(1L)).thenReturn(null);

        mockMvc.perform(post("/api/runs/1/approve"))
                .andExpect(status().isOk());

        ArgumentCaptor<Boolean> approvedCaptor = ArgumentCaptor.forClass(Boolean.class);
        ArgumentCaptor<String> noteCaptor = ArgumentCaptor.forClass(String.class);
        verify(runService, times(1)).approve(eq(1L), approvedCaptor.capture(), noteCaptor.capture());
        assertThat(approvedCaptor.getValue()).isFalse();
        assertThat(noteCaptor.getValue()).isNull();
    }

    @Test
    void approve_nullApproved_treatedAsReject() throws Exception {
        when(runService.getRun(1L)).thenReturn(null);

        Map<String, Object> body = new HashMap<>();
        body.put("approved", null);

        mockMvc.perform(post("/api/runs/1/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());

        ArgumentCaptor<Boolean> approvedCaptor = ArgumentCaptor.forClass(Boolean.class);
        ArgumentCaptor<String> noteCaptor = ArgumentCaptor.forClass(String.class);
        verify(runService, times(1)).approve(eq(1L), approvedCaptor.capture(), noteCaptor.capture());
        assertThat(approvedCaptor.getValue()).isFalse();
        assertThat(noteCaptor.getValue()).isNull();
    }

    @Test
    void rerun_noBody_returns201() throws Exception {
        when(runService.rerun(1L, null)).thenReturn(55L);

        mockMvc.perform(post("/api/runs/1/rerun"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.runId").value(55));
    }

    @Test
    void rerun_withGoal_passesGoal() throws Exception {
        when(runService.rerun(1L, "新目标")).thenReturn(66L);

        Map<String, Object> body = new HashMap<>();
        body.put("goal", "新目标");

        mockMvc.perform(post("/api/runs/1/rerun")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isCreated());

        verify(runService, times(1)).rerun(1L, "新目标");
    }

    @Test
    void stats_returnsStats() throws Exception {
        when(runService.stats()).thenReturn(new Records.RunStatsResponse(10, 7, 2, 0.7, 1234));

        mockMvc.perform(get("/api/runs/stats"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalRuns").value(10));
    }

    @Test
    void logs_defaultOffset() throws Exception {
        when(runService.readStepLog(1L, 2L, 0L))
                .thenReturn(new Records.LogReadResponse("line1\n", 6, true));

        mockMvc.perform(get("/api/runs/1/steps/2/logs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").value("line1\n"));
    }
}