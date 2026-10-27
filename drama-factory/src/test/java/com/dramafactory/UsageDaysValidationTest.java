package com.dramafactory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class UsageDaysValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void summaryNegativeDaysReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/api/usage/summary").param("days", "-1"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void summaryOverMaxDaysReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/api/usage/summary").param("days", "366"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void summaryNonIntegerDaysReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/api/usage/summary").param("days", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void summaryZeroDaysReturnsOk() throws Exception {
        mockMvc.perform(get("/api/usage/summary").param("days", "0"))
                .andExpect(status().isOk());
    }

    @Test
    void summaryThirtyDaysReturnsOk() throws Exception {
        mockMvc.perform(get("/api/usage/summary").param("days", "30"))
                .andExpect(status().isOk());
    }

    @Test
    void byDayNegativeDaysReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/api/usage/by-day").param("days", "-1"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void byDayOverMaxDaysReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/api/usage/by-day").param("days", "366"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void byDayNonIntegerDaysReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/api/usage/by-day").param("days", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void byDayZeroDaysReturnsOk() throws Exception {
        mockMvc.perform(get("/api/usage/by-day").param("days", "0"))
                .andExpect(status().isOk());
    }

    @Test
    void byDayThirtyDaysReturnsOk() throws Exception {
        mockMvc.perform(get("/api/usage/by-day").param("days", "30"))
                .andExpect(status().isOk());
    }
}