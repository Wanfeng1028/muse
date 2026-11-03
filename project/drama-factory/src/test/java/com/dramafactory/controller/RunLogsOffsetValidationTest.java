package com.dramafactory.controller;

import com.dramafactory.config.JwtVerifier;
import com.dramafactory.dto.Records;
import com.dramafactory.service.RunService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = RunController.class)
class RunLogsOffsetValidationTest {

    @MockBean
    private JwtVerifier jwtVerifier;

    @MockBean
    private RunService runService;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void negativeOffsetReturns400() throws Exception {
        mockMvc.perform(get("/api/runs/1/steps/10/logs").param("offset", "-1"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void nonNumericOffsetReturns400() throws Exception {
        mockMvc.perform(get("/api/runs/1/steps/10/logs").param("offset", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void zeroOffsetReturns200() throws Exception {
        when(runService.readStepLog(eq(1L), eq(10L), eq(0L)))
                .thenReturn(new Records.LogReadResponse("[12:00:01] 开始\n", 18, false));

        mockMvc.perform(get("/api/runs/1/steps/10/logs").param("offset", "0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nextOffset").value(18));
    }

    @Test
    void missingOffsetDefaultsToZeroReturns200() throws Exception {
        when(runService.readStepLog(eq(1L), eq(10L), eq(0L)))
                .thenReturn(new Records.LogReadResponse("[12:00:01] 开始\n", 18, false));

        mockMvc.perform(get("/api/runs/1/steps/10/logs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nextOffset").value(18));
    }
}