package com.dramafactory.billing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CostLedgerDailyDeepTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    CostLedgerService service;

    @Autowired
    CostLedgerEntryRepository repository;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private BudgetPolicy bigBudgetPolicy() {
        return new BudgetPolicy(BudgetMode.WARN, 100000d, 0.1);
    }

    private String uniqueProvider(String base) {
        return base + "-" + UUID.randomUUID().toString().replace("-", "").substring(0, 8);
    }

    private JsonNode getDailyArray(String queryDate) throws Exception {
        String url = queryDate == null
                ? "/api/cost-ledger/daily"
                : "/api/cost-ledger/daily?date=" + queryDate;
        MvcResult result = mockMvc.perform(get(url))
                .andExpect(status().isOk())
                .andReturn();
        String body = result.getResponse().getContentAsString();
        return objectMapper.readTree(body);
    }

    private JsonNode findByProvider(JsonNode array, String provider) {
        for (JsonNode node : array) {
            if (provider.equals(node.path("provider").asText())) {
                return node;
            }
        }
        return null;
    }

    @Test
    void emptyLedgerReturnsOkAndArray() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/cost-ledger/daily"))
                .andExpect(status().isOk())
                .andReturn();
        String body = result.getResponse().getContentAsString();
        JsonNode array = objectMapper.readTree(body);
        assertNotNull(array);
        assertTrue(array.isArray());
    }

    @Test
    void dailySummarizesByProviderWithSpentOnlyCompletedOrFailed() throws Exception {
        String agnesProvider = uniqueProvider("agnes");
        String minimaxProvider = uniqueProvider("minimax");

        Long agnesId = service.recordEstimate(
                null, agnesProvider, "agnes", "video-generate", 1.0, "t1");
        service.reserve(agnesId, bigBudgetPolicy());
        service.complete(agnesId, 0.8, 100L);

        Long minimaxId = service.recordEstimate(
                null, minimaxProvider, "minimax", "video-generate", 0.5, "t2");
        service.reserve(minimaxId, bigBudgetPolicy());

        String today = LocalDate.now().toString();
        JsonNode array = getDailyArray(today);

        JsonNode agnesNode = findByProvider(array, agnesProvider);
        JsonNode minimaxNode = findByProvider(array, minimaxProvider);
        assertNotNull(agnesNode);
        assertNotNull(minimaxNode);

        assertEquals(1.0, agnesNode.path("estimatedUsd").asDouble(), 1e-6);
        assertEquals(0.8, agnesNode.path("spentUsd").asDouble(), 1e-6);
        assertEquals(1, agnesNode.path("entryCount").asInt());

        assertEquals(0.5, minimaxNode.path("estimatedUsd").asDouble(), 1e-6);
        assertEquals(0.0, minimaxNode.path("spentUsd").asDouble(), 1e-6);
        assertEquals(1, minimaxNode.path("entryCount").asInt());
    }

    @Test
    void invalidDateReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/api/cost-ledger/daily?date=not-a-date"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingDateEquivalentToToday() throws Exception {
        String provider = uniqueProvider("default-date");
        Long id = service.recordEstimate(
                null, provider, provider, "video-generate", 1.0, "t3");
        service.reserve(id, bigBudgetPolicy());
        service.complete(id, 0.9, 50L);

        JsonNode noDate = getDailyArray(null);
        JsonNode todayArray = getDailyArray(LocalDate.now().toString());

        assertNotNull(findByProvider(noDate, provider));
        assertNotNull(findByProvider(todayArray, provider));
        assertEquals(noDate.size(), todayArray.size());
    }

    @Test
    void summarizeDailyWithNullDateDoesNotThrow() {
        List<CostLedgerService.ProviderDailyCost> result = service.summarizeDaily(null);
        assertNotNull(result);
    }
}
