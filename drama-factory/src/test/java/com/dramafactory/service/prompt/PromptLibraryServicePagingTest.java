package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PromptLibraryServicePagingTest {

    @Test
    void firstPageSize5() {
        PromptLibraryService service = new PromptLibraryService();
        long total = service.list(null, null, 0, 100).totalElements();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list(null, null, 0, 5);
        assertEquals(5, page.content().size());
        assertEquals(0, page.page());
        assertEquals(5, page.size());
        assertEquals(total, page.totalElements());
        assertEquals((int)((total + 5 - 1) / 5), page.totalPages());
    }

    @Test
    void outOfRangePageEmptyContent() {
        PromptLibraryService service = new PromptLibraryService();
        long total = service.list(null, null, 0, 100).totalElements();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list(null, null, 100, 5);
        assertTrue(page.content().isEmpty());
        assertEquals(total, page.totalElements());
    }

    @Test
    void negativePageBecomesZero() {
        PromptLibraryService service = new PromptLibraryService();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> negativePage = service.list(null, null, -1, 5);
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> zeroPage = service.list(null, null, 0, 5);
        List<String> negativeIds = negativePage.content().stream()
                .map(PromptLibraryService.PromptSummary::id)
                .collect(Collectors.toList());
        List<String> zeroIds = zeroPage.content().stream()
                .map(PromptLibraryService.PromptSummary::id)
                .collect(Collectors.toList());
        assertEquals(zeroIds, negativeIds);
        assertEquals(0, negativePage.page());
    }

    @Test
    void zeroSizeDefaultsTo20() {
        PromptLibraryService service = new PromptLibraryService();
        long total = service.list(null, null, 0, 100).totalElements();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list(null, null, 0, 0);
        assertEquals(20, page.size());
        assertEquals(20, page.content().size());
        assertEquals((int)((total + 20 - 1) / 20), page.totalPages());
    }

    @Test
    void oversizedSizeClampedTo100() {
        PromptLibraryService service = new PromptLibraryService();
        long total = service.list(null, null, 0, 100).totalElements();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list(null, null, 0, 1000);
        assertEquals(100, page.size());
        assertEquals((int)Math.min(100, total), page.content().size());
        assertEquals(total, page.totalElements());
        assertEquals((int)((total + 100 - 1) / 100), page.totalPages());
    }

    @Test
    void totalPagesComputation() {
        PromptLibraryService service = new PromptLibraryService();
        long total = service.list(null, null, 0, 100).totalElements();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page10 = service.list(null, null, 0, 10);
        assertEquals((int)((total + 10 - 1) / 10), page10.totalPages());
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page26 = service.list(null, null, 0, 26);
        assertEquals((int)((total + 26 - 1) / 26), page26.totalPages());
    }

    @Test
    void secondPageDistinct() {
        PromptLibraryService service = new PromptLibraryService();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> firstPage = service.list(null, null, 0, 5);
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> secondPage = service.list(null, null, 1, 5);
        Set<String> firstIds = firstPage.content().stream()
                .map(PromptLibraryService.PromptSummary::id)
                .collect(Collectors.toSet());
        Set<String> secondIds = secondPage.content().stream()
                .map(PromptLibraryService.PromptSummary::id)
                .collect(Collectors.toSet());
        Set<String> intersection = new HashSet<>(firstIds);
        intersection.retainAll(secondIds);
        assertTrue(intersection.isEmpty());
        assertEquals(1, secondPage.page());
    }

    @Test
    void qAndTagCombinedPaging() {
        PromptLibraryService service = new PromptLibraryService();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> page = service.list("雨爱", "根目录", 0, 5);
        assertEquals(page.content().size(), page.totalElements());
        assertFalse(page.content().isEmpty());
        for (PromptLibraryService.PromptSummary summary : page.content()) {
            assertEquals("根目录", summary.source());
            String title = summary.title() == null ? "" : summary.title().toLowerCase();
            String summaryText = summary.summary() == null ? "" : summary.summary().toLowerCase();
            assertTrue(title.contains("雨爱") || summaryText.contains("雨爱"));
        }
    }

    @Test
    void filteredPageOutOfRange() {
        PromptLibraryService service = new PromptLibraryService();
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> firstPage = service.list("雨爱", "根目录", 0, 5);
        PromptLibraryService.Page<PromptLibraryService.PromptSummary> outOfRange = service.list("雨爱", "根目录", 5, 5);
        assertTrue(outOfRange.content().isEmpty());
        assertEquals(firstPage.totalElements(), outOfRange.totalElements());
    }
}
