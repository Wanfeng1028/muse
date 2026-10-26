package com.dramafactory.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UsageRequestsValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void limitZeroReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/requests").param("limit", "0"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void limitNegativeReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/requests").param("limit", "-1"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void limitTooLargeReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/requests").param("limit", "501"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void limitNotANumberReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/requests").param("limit", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void daysNegativeReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/requests").param("days", "-1"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void daysTooLargeReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/requests").param("days", "366"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void daysNotANumberReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/requests").param("days", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void noParamsReturns200() throws Exception {
        mockMvc.perform(get("/api/usage/requests"))
                .andExpect(status().isOk());
    }

    @Test
    void limitOneAndDaysZeroReturns200() throws Exception {
        mockMvc.perform(get("/api/usage/requests").param("limit", "1").param("days", "0"))
                .andExpect(status().isOk());
    }

    @Test
    void limitMaxAndDaysMaxReturns200() throws Exception {
        mockMvc.perform(get("/api/usage/requests").param("limit", "500").param("days", "365"))
                .andExpect(status().isOk());
    }
}
