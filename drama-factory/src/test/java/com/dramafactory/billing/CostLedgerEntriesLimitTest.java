package com.dramafactory.billing;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CostLedgerEntriesLimitTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private CostLedgerService costLedgerService;

    @Autowired
    private CostLedgerEntryRepository repository;

    @BeforeEach
    void setUp() {
        repository.deleteAll();
    }

    private void seedFiveEstimates() {
        costLedgerService.recordEstimate(1L, "p", "m", "op", 1.0, "n");
        costLedgerService.recordEstimate(1L, "p", "m", "op", 1.0, "n");
        costLedgerService.recordEstimate(1L, "p", "m", "op", 1.0, "n");
        costLedgerService.recordEstimate(1L, "p", "m", "op", 1.0, "n");
        costLedgerService.recordEstimate(1L, "p", "m", "op", 1.0, "n");
    }

    @Test
    void entries_defaultLimit_returnsAllWhenUnder100() throws Exception {
        seedFiveEstimates();
        mockMvc.perform(get("/api/cost-ledger/entries"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(5));
    }

    @Test
    void entries_limit2_returns2() throws Exception {
        seedFiveEstimates();
        mockMvc.perform(get("/api/cost-ledger/entries").param("limit", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2));
    }

    @Test
    void entries_limit0_returns400() throws Exception {
        seedFiveEstimates();
        mockMvc.perform(get("/api/cost-ledger/entries").param("limit", "0"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void entries_limitNegative_returns400() throws Exception {
        seedFiveEstimates();
        mockMvc.perform(get("/api/cost-ledger/entries").param("limit", "-3"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void entries_limitAbc_returns400() throws Exception {
        seedFiveEstimates();
        mockMvc.perform(get("/api/cost-ledger/entries").param("limit", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void entries_limit1000_clampedTo500() throws Exception {
        seedFiveEstimates();
        mockMvc.perform(get("/api/cost-ledger/entries").param("limit", "1000"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(5));
    }
}
