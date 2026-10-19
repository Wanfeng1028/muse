package com.dramafactory.service;

import com.dramafactory.service.UsageService.UsageSummary;
import com.dramafactory.service.UsageService.ModelUsage;
import com.dramafactory.service.UsageService.DailyUsage;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

@SpringBootTest
class UsageServiceSummaryDeepTestR4 {

    @Autowired
    private UsageService usageService;

    @Test
    void filters_returnsSortedLists() {
        UsageService.FilterOptions options = usageService.filters();
        assertNotNull(options);
        List<String> providers = options.providers();
        List<String> models = options.models();
        assertNotNull(providers);
        assertNotNull(models);
        for (int i = 1; i < providers.size(); i++) {
            assertTrue(providers.get(i - 1).compareTo(providers.get(i)) <= 0,
                    "providers not sorted at index " + i);
        }
        for (int i = 1; i < models.size(); i++) {
            assertTrue(models.get(i - 1).compareTo(models.get(i)) <= 0,
                    "models not sorted at index " + i);
        }
    }

    @Test
    void filters_noDuplicates() {
        UsageService.FilterOptions options = usageService.filters();
        List<String> providers = options.providers();
        List<String> models = options.models();
        for (int i = 1; i < providers.size(); i++) {
            assertTrue(providers.get(i - 1).compareTo(providers.get(i)) < 0,
                    "providers contains duplicate at index " + i);
        }
        for (int i = 1; i < models.size(); i++) {
            assertTrue(models.get(i - 1).compareTo(models.get(i)) < 0,
                    "models contains duplicate at index " + i);
        }
    }

    @Test
    void summary_requestCountEqualsSum() {
        UsageSummary summary = usageService.summary();
        assertNotNull(summary);
        assertEquals(summary.taskCount() + summary.stepCount(), summary.requestCount());
    }

    @Test
    void summary_emptyCacheHitRate() {
        UsageSummary summary = usageService.summary();
        assertNotNull(summary);
        double rate = summary.cacheHitRate();
        assertTrue(rate >= 0.0 && rate <= 1.0, "cacheHitRate out of range: " + rate);
    }

    @Test
    void summary_countsNonNegative() {
        UsageSummary summary = usageService.summary();
        assertTrue(summary.taskCount() >= 0);
        assertTrue(summary.runCount() >= 0);
        assertTrue(summary.stepCount() >= 0);
        assertTrue(summary.requestCount() >= 0);
    }

    @Test
    void summary_tokensTotal_nullOrNonNegative() {
        UsageSummary summary = usageService.summary();
        Long tokensTotal = summary.tokensTotal();
        if (tokensTotal != null) {
            assertTrue(tokensTotal >= 0, "tokensTotal negative: " + tokensTotal);
        } else {
            assertNull(tokensTotal);
        }
    }

    @Test
    void byDay_oneDay_sizeAtMostOne_andDateNotNull() {
        List<DailyUsage> result = usageService.byDay(1);
        assertNotNull(result);
        assertTrue(result.size() <= 1, "byDay(1) returned more than 1 element: " + result.size());
        for (DailyUsage day : result) {
            assertNotNull(day.date(), "day.date() is null");
        }
    }

    @Test
    void byDay_negativeDays_doesNotThrow() {
        assertDoesNotThrow(() -> usageService.byDay(-3));
    }

    @Test
    void byModel_eachItemHasModel() {
        List<ModelUsage> result = usageService.byModel();
        assertNotNull(result);
        for (ModelUsage item : result) {
            assertNotNull(item.model(), "model is null");
        }
    }

    @Test
    void summary_twice_consistent() {
        UsageSummary first = usageService.summary();
        UsageSummary second = usageService.summary();
        assertNotNull(first);
        assertNotNull(second);
        assertEquals(first.taskCount(), second.taskCount());
        assertEquals(first.stepCount(), second.stepCount());
        assertEquals(first.runCount(), second.runCount());
    }

    @Test
    void filters_twice_consistent() {
        UsageService.FilterOptions first = usageService.filters();
        UsageService.FilterOptions second = usageService.filters();
        assertNotNull(first);
        assertNotNull(second);
        assertEquals(first.providers(), second.providers());
        assertEquals(first.models(), second.models());
    }

    @Test
    void byDay_largeDays_ok() {
        assertDoesNotThrow(() -> usageService.byDay(365));
    }
}