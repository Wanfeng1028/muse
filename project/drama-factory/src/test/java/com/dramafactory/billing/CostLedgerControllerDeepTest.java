package com.dramafactory.billing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * CostLedgerController 深度测试，使用 MockMvc 校验汇总、列表及状态过滤。
 * 使用默认测试 H2 配置。
 */
@SpringBootTest
@AutoConfigureMockMvc
class CostLedgerControllerDeepTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void getSummary_returns200WithEntryCount() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/summary"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.entryCount").exists());
    }

    @Test
    void listEntries_returns200WithArray() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/entries"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    void listEntries_filteredByCompleted_returns200WithArray() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/entries").param("status", "COMPLETED"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray());
    }

    @Test
    void listEntries_invalidStatus_returns400() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/entries").param("status", "BOGUS"))
                .andExpect(status().isBadRequest());
    }
}
