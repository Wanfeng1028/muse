package com.dramafactory.billing;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CostLedgerTrendControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void getTrend_default_returns14Points() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/trend"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(14))
                .andExpect(jsonPath("$[0].date").exists())
                .andExpect(jsonPath("$[0].estimatedUsd").exists())
                .andExpect(jsonPath("$[0].spentUsd").exists())
                .andExpect(jsonPath("$[0].entryCount").exists());
    }

    @Test
    void getTrend_days7_returns7Points() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/trend").param("days", "7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(7));
    }

    @Test
    void getTrend_invalidDays_returns400() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/trend").param("days", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").exists());
    }

    @Test
    void getTrend_days200_clampedByService() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/trend").param("days", "200"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(90));
    }

    @Test
    void getTrend_days0_clampedTo1() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/trend").param("days", "0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1));
    }
}
