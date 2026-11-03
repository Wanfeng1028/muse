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
class UsageByRunValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void limitZeroReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/by-run").param("limit", "0"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void limitNegativeReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/by-run").param("limit", "-1"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void limitTooLargeReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/by-run").param("limit", "501"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void limitNotANumberReturns400() throws Exception {
        mockMvc.perform(get("/api/usage/by-run").param("limit", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void noParamsReturns200() throws Exception {
        mockMvc.perform(get("/api/usage/by-run"))
                .andExpect(status().isOk());
    }

    @Test
    void limitOneReturns200() throws Exception {
        mockMvc.perform(get("/api/usage/by-run").param("limit", "1"))
                .andExpect(status().isOk());
    }

    @Test
    void limitMaxReturns200() throws Exception {
        mockMvc.perform(get("/api/usage/by-run").param("limit", "500"))
                .andExpect(status().isOk());
    }
}
