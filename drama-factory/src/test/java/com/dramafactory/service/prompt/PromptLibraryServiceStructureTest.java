package com.dramafactory.service.prompt;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class PromptLibraryServiceStructureTest {

    @Test
    void allEntriesHaveNonEmptyUniqueIds() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        assertNotNull(summaries);
        Set<String> ids = new HashSet<>();
        for (PromptLibraryService.PromptSummary summary : summaries) {
            assertNotNull(summary.id());
            assertFalse(summary.id().isEmpty());
            ids.add(summary.id());
        }
        assertEquals(summaries.size(), ids.size());
    }

    @Test
    void allEntriesHaveNonNullFields() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        assertNotNull(summaries);
        for (PromptLibraryService.PromptSummary summary : summaries) {
            assertNotNull(summary.title());
            assertNotNull(summary.path());
            assertNotNull(summary.summary());
            assertTrue(summary.path().endsWith(".md"));
        }
    }

    @Test
    void entriesSortedByPath() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        assertNotNull(summaries);
        for (int i = 0; i < summaries.size(); i++) {
            PromptLibraryService.PromptSummary current = summaries.get(i);
            if (i > 0) {
                PromptLibraryService.PromptSummary previous = summaries.get(i - 1);
                assertTrue(previous.path().compareTo(current.path()) <= 0);
            }
            Optional<PromptLibraryService.PromptDetail> detailOpt = service.get(current.id());
            assertTrue(detailOpt.isPresent());
            assertEquals(current.path(), detailOpt.get().path());
        }
    }

    @Test
    void sourceDistributionContainsKnownSources() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        assertNotNull(summaries);
        Set<String> sources = new HashSet<>();
        Map<String, Integer> distribution = new HashMap<>();
        for (PromptLibraryService.PromptSummary summary : summaries) {
            sources.add(summary.source());
            distribution.merge(summary.source(), 1, Integer::sum);
        }
        assertTrue(sources.contains("根目录"));
        assertTrue(sources.contains("opus-video-prompts"));
        assertTrue(sources.contains("pdoom-video"));
        System.out.println("Source distribution: " + distribution);
    }

    @Test
    void everyEntryHasNonEmptyContent() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        assertNotNull(summaries);
        for (PromptLibraryService.PromptSummary summary : summaries) {
            Optional<PromptLibraryService.PromptDetail> detailOpt = service.get(summary.id());
            assertTrue(detailOpt.isPresent());
            PromptLibraryService.PromptDetail detail = detailOpt.get();
            assertNotNull(detail.content());
            assertFalse(detail.content().isEmpty());
        }
    }

    @Test
    void summaryLengthBound() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        assertNotNull(summaries);
        for (PromptLibraryService.PromptSummary summary : summaries) {
            assertNotNull(summary.summary());
            assertTrue(summary.summary().length() <= 200);
            assertNotNull(summary.title());
            assertFalse(summary.title().isEmpty());
        }
    }

    @Test
    void knownIdsExist() {
        PromptLibraryService service = new PromptLibraryService();
        List<PromptLibraryService.PromptSummary> summaries = service.list(null);
        assertNotNull(summaries);
        Set<String> ids = new HashSet<>();
        for (PromptLibraryService.PromptSummary summary : summaries) {
            ids.add(summary.id());
        }
        assertTrue(ids.contains("yuai-deepseek-prompt"));
        assertTrue(ids.contains("xiaozheng-mv-tutorial"));
        assertTrue(ids.contains("opus-video-prompts__prompts__01-inference-startup-launch"));
        assertTrue(ids.contains("pdoom-video__STORYBOARD"));
        assertTrue(ids.stream().anyMatch(id -> id.startsWith("pdoom-video__README")));
        assertTrue(ids.contains("opus-video-prompts__README"));
    }
}