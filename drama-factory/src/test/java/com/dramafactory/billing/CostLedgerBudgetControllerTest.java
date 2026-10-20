package com.dramafactory.billing;

import static org.hamcrest.Matchers.closeTo;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CostLedgerBudgetControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void getBudget_returns200WithFields() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/budget"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.budgetTotalUsd").exists())
                .andExpect(jsonPath("$.spentUsd").exists())
                .andExpect(jsonPath("$.reservedUsd").exists())
                .andExpect(jsonPath("$.usableUsd").exists())
                .andExpect(jsonPath("$.utilizationPct").exists())
                .andExpect(jsonPath("$.mode").exists())
                .andExpect(jsonPath("$.enabled").exists())
                .andExpect(jsonPath("$.budgetTotalUsd").value(100.0))
                .andExpect(jsonPath("$.mode").value("WARN"))
                .andExpect(jsonPath("$.enabled").value(true));
    }

    @Test
    void getBudget_numbersAreConsistent() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/cost-ledger/budget"))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode node = objectMapper.readTree(result.getResponse().getContentAsString());
        double budgetTotalUsd = node.get("budgetTotalUsd").asDouble();
        double spentUsd = node.get("spentUsd").asDouble();
        double reservedUsd = node.get("reservedUsd").asDouble();
        double usableUsd = node.get("usableUsd").asDouble();

        double expectedUsable = budgetTotalUsd - spentUsd - reservedUsd - budgetTotalUsd * 0.1;

        org.hamcrest.MatcherAssert.assertThat(usableUsd, closeTo(expectedUsable, 1e-6));
    }
}
